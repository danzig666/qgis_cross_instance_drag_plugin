"""GUI-independent part of the cross-instance layer transfer.

Sending side: memory-provider layers are written to a GeoPackage snapshot in
a per-process temp directory, keyed by the layer ID.

Receiving side: the QLR XML that QGIS puts into the drag is loaded with
QgsLayerDefinition.loadLayerDefinitionLayers(), which, unlike
loadLayerDefinition(), keeps the original layer IDs. Only colliding IDs are
replaced, and every exact reference to them in the XML is rewritten too.
"""

import hashlib
import json
import os
import tempfile
import time
import uuid
from pathlib import Path

from qgis.PyQt.QtXml import QDomDocument
from qgis.core import (
    QgsFeature,
    QgsLayerDefinition,
    QgsLayerTreeGroup,
    QgsMapLayer,
    QgsReadWriteContext,
    QgsVectorFileWriter,
    QgsVectorLayer,
)

from .i18n import TransferError

FORMAT_QGIS_TREE = "application/qgis.layertreemodeldata"
FORMAT_QGIS_QLR = "application/qgis.layertree.layerdefinitions"
FORMAT_QGIS_PID = "application/qgis.application.pid"

SNAPSHOT_ROOT = Path(tempfile.gettempdir()) / "qgis_cross_instance_drag_v1"
SNAPSHOT_TTL = 10 * 60  # reject snapshots older than ten minutes
CLEANUP_AGE = 3 * SNAPSHOT_TTL  # delete leftover files after half an hour
SNAPSHOT_LAYER = "features"
# Dedicated FID column, so a user field called "fid" is copied as plain data.
SNAPSHOT_FID = "__xdrag_fid"
MAX_BATCH = 1000

try:
    WRITER_NO_ERROR = QgsVectorFileWriter.WriterError.NoError
except AttributeError:  # older sip enums
    WRITER_NO_ERROR = QgsVectorFileWriter.NoError


def is_memory_layer(layer):
    return isinstance(layer, QgsVectorLayer) and layer.providerType() == "memory"


def foreign_origin_pid(mime):
    """Return the sending process ID for a QGIS layer-tree drag that comes
    from ANOTHER QGIS process, None otherwise."""
    if mime is None or not (mime.hasFormat(FORMAT_QGIS_TREE) and mime.hasFormat(FORMAT_QGIS_QLR)):
        return None
    try:
        pid = int(bytes(mime.data(FORMAT_QGIS_PID)).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return None if pid == os.getpid() else pid


# --------------------------------------------------------------------------
# Snapshots (sending side)
# --------------------------------------------------------------------------

def _snapshot_dir(pid):
    return SNAPSHOT_ROOT / str(pid)


def _meta_path(pid, layer_id):
    key = hashlib.sha256(layer_id.encode("utf-8")).hexdigest()
    return _snapshot_dir(pid) / (key + ".json")


def _remove(path):
    try:
        Path(path).unlink()
        return True
    except OSError:
        return False


def stage_memory_layers(layers, transform_context):
    """Snapshot each distinct memory layer of `layers`. Returns the count."""
    seen = set()
    for layer in layers:
        if is_memory_layer(layer) and layer.id() not in seen:
            seen.add(layer.id())
            stage_memory_layer(layer, transform_context)
    return len(seen)


def stage_memory_layer(layer, transform_context):
    directory = _snapshot_dir(os.getpid())
    directory.mkdir(parents=True, exist_ok=True)
    meta_path = _meta_path(os.getpid(), layer.id())

    # The previous snapshot of this layer is superseded; delete its data file
    # (may fail on Windows while the receiver still reads it, that's fine).
    if meta_path.is_file():
        try:
            with meta_path.open("r", encoding="utf-8") as f:
                old_gpkg = json.load(f).get("gpkg")
            if old_gpkg:
                _remove(old_gpkg)
        except (OSError, ValueError):
            pass

    # featureCount() includes the edit buffer of a layer in editing mode, just
    # like the writer below does.
    count = layer.featureCount()
    gpkg_path = None
    if count > 0:
        # Unique file name: never overwrite a database the other QGIS process
        # might still have open.
        gpkg_path = directory / (uuid.uuid4().hex + ".gpkg")
        opts = QgsVectorFileWriter.SaveVectorOptions()
        opts.driverName = "GPKG"
        opts.layerName = SNAPSHOT_LAYER
        opts.fileEncoding = "UTF-8"
        opts.layerOptions = ["FID=" + SNAPSHOT_FID, "SPATIAL_INDEX=NO"]
        try:
            result = QgsVectorFileWriter.writeAsVectorFormatV3(
                layer, str(gpkg_path), transform_context, opts
            )
            if result[0] != WRITER_NO_ERROR:
                raise TransferError("err_export", error=result[1])
        except Exception:
            _remove(gpkg_path)
            raise

    info = {
        "pid": os.getpid(),
        "id": layer.id(),
        "name": layer.name(),
        "created": time.time(),
        "count": count,
        "gpkg": str(gpkg_path) if gpkg_path else None,
    }
    temp_meta = directory / (uuid.uuid4().hex + ".tmp")
    try:
        with temp_meta.open("w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False)
        os.replace(str(temp_meta), str(meta_path))
    finally:
        if temp_meta.exists():
            _remove(temp_meta)


def cleanup_snapshots(max_age=CLEANUP_AGE, own_only=False):
    """Delete snapshot files older than `max_age` seconds. Returns the count."""
    if not SNAPSHOT_ROOT.is_dir():
        return 0
    now = time.time()
    removed = 0
    dirs = [_snapshot_dir(os.getpid())] if own_only else [p for p in SNAPSHOT_ROOT.iterdir() if p.is_dir()]
    for directory in dirs:
        if not directory.is_dir():
            continue
        for path in directory.iterdir():
            try:
                old = now - path.stat().st_mtime > max_age
            except OSError:
                continue
            if old and _remove(path):
                removed += 1
        try:
            directory.rmdir()  # only succeeds when empty
        except OSError:
            pass
    return removed


def read_snapshot(pid, layer_id):
    """Return snapshot metadata, None when there is no usable snapshot."""
    meta_path = _meta_path(pid, layer_id)
    if not meta_path.is_file():
        return None
    try:
        with meta_path.open("r", encoding="utf-8") as f:
            info = json.load(f)
    except (OSError, ValueError):
        raise TransferError("err_bad_snapshot", id=layer_id)
    if info.get("pid") != pid or info.get("id") != layer_id:
        raise TransferError("err_bad_snapshot", id=layer_id)
    if time.time() - float(info.get("created", 0)) > SNAPSHOT_TTL:
        return None
    if int(info.get("count", 0)) > 0 and not Path(info.get("gpkg") or "").is_file():
        raise TransferError("err_snapshot_gpkg", id=layer_id)
    return info


# --------------------------------------------------------------------------
# Import (receiving side)
# --------------------------------------------------------------------------

class ImportResult:
    def __init__(self):
        self.count = 0
        self.kept = 0
        self.collisions = 0
        self.features = 0
        self.missing_snapshots = []  # names of memory layers that came empty


def _parse_document(xml):
    doc = QDomDocument("qgis-layer-definition")
    ok = doc.setContent(xml)
    if isinstance(ok, tuple):
        ok = ok[0]
    if not ok:
        raise TransferError("err_bad_xml")
    return doc


def import_layer_definition(xml, origin_pid, project, target_group, index=-1):
    """Load the dragged QLR `xml` into `project` under `target_group`."""
    result = ImportResult()
    doc = _parse_document(xml)

    order = []
    originals = {}  # original ID -> (provider, name)
    maplayers = doc.elementsByTagName("maplayer")
    for i in range(maplayers.count()):
        el = maplayers.item(i).toElement()
        original_id = el.firstChildElement("id").text()
        if not original_id or original_id in originals:
            raise TransferError("err_bad_id")
        originals[original_id] = (
            el.firstChildElement("provider").text(),
            el.firstChildElement("layername").text(),
        )
        order.append(original_id)
    if not order:
        raise TransferError("err_no_layers")

    # Validate every snapshot BEFORE touching the project.
    snapshots = {}
    for layer_id, (provider, name) in originals.items():
        if provider == "memory":
            info = read_snapshot(origin_pid, layer_id)
            if info is None:
                result.missing_snapshots.append(name or layer_id)
            else:
                snapshots[layer_id] = info

    occupied = set(project.mapLayers().keys())
    mapping = {}
    for original_id in order:
        if original_id in occupied:
            new_id = QgsMapLayer.generateId(originals[original_id][1])
            while new_id in occupied:
                new_id = QgsMapLayer.generateId(originals[original_id][1])
            mapping[original_id] = new_id
            occupied.add(new_id)
            result.collisions += 1
        else:
            occupied.add(original_id)
            result.kept += 1

    # Tree IDs, joins, relations, dependencies, editor widgets... all exact
    # references to a colliding ID are rewritten together.
    _rewrite_xml_ids(doc, mapping)

    context = QgsReadWriteContext()
    context.setTransformContext(project.transformContext())
    layers = QgsLayerDefinition.loadLayerDefinitionLayers(doc, context)
    if len(layers) != len(order):
        raise TransferError("err_unsupported", loaded=len(layers), total=len(order))

    by_id = {layer.id(): layer for layer in layers}
    for original_id in order:
        layer_id = mapping.get(original_id, original_id)
        layer = by_id.get(layer_id)
        if layer is None:
            raise TransferError("err_id_mismatch", id=layer_id)
        if original_id in snapshots:
            if not is_memory_layer(layer):
                raise TransferError("err_not_memory", id=original_id)
            result.features += fill_memory_layer(layer, snapshots[original_id])

    registered = []
    try:
        for layer in layers:
            if project.mapLayer(layer.id()) is not None:
                raise TransferError("err_id_collision", id=layer.id())
            project.addMapLayer(layer, False)
            registered.append(layer.id())
        for layer in layers:
            layer.resolveReferences(project)

        tree_el = doc.documentElement().firstChildElement("layer-tree-group")
        if not tree_el.isNull():
            tree = QgsLayerTreeGroup.readXml(tree_el, project, context)
            if tree is None:
                raise TransferError("err_tree")
            # abandonChildren() is not available from Python, so the nodes are
            # cloned; the temporary tree is then freed together with its
            # original children.
            nodes = [child.clone() for child in tree.children()]
            target_group.insertChildNodes(index, nodes)
        else:
            for offset, layer in enumerate(layers):
                target_group.insertLayer(index + offset if index >= 0 else -1, layer)
    except Exception:
        for layer_id in registered:
            if project.mapLayer(layer_id) is not None:
                project.removeMapLayer(layer_id)
        raise

    result.count = len(layers)
    return result


def _rewrite_xml_ids(doc, substitutions):
    if not substitutions:
        return
    # QDom has no "*" wildcard for elementsByTagName(), so walk the tree.
    stack = [doc.documentElement()]
    while stack:
        node = stack.pop()
        if node.isElement():
            attrs = node.attributes()
            for j in range(attrs.count()):
                attr = attrs.item(j)
                if attr.nodeValue() in substitutions:
                    attr.setNodeValue(substitutions[attr.nodeValue()])
        elif node.isText() or node.isCDATASection():
            if node.nodeValue() in substitutions:
                node.setNodeValue(substitutions[node.nodeValue()])
            continue
        child = node.firstChild()
        while not child.isNull():
            stack.append(child)
            child = child.nextSibling()


def _convert(field, value):
    try:
        return field.convertCompatible(value)
    except (ValueError, TypeError):
        return value


def fill_memory_layer(destination, snapshot):
    expected = int(snapshot.get("count", 0))
    if expected <= 0:
        return 0
    if destination.featureCount() > 0:
        # Already restored from the definition itself (nothing to add).
        return 0
    reader = QgsVectorLayer(
        "{}|layername={}".format(snapshot["gpkg"], SNAPSHOT_LAYER), "snapshot", "ogr"
    )
    if not reader.isValid():
        raise TransferError("err_snapshot_gpkg", id=snapshot.get("id", ""))

    dp = destination.dataProvider()
    existing = {field.name() for field in destination.fields()}
    missing = [
        field for field in reader.fields()
        if field.name() not in existing and field.name() != SNAPSHOT_FID
    ]
    if missing:
        if not dp.addAttributes(missing):
            raise TransferError("err_fields")
        destination.updateFields()

    dst_fields = destination.fields()
    src_names = {f.name() for f in reader.fields()}
    copy_plan = [
        (index, dst_fields.at(index))
        for index in range(dst_fields.count())
        if dst_fields.at(index).name() in src_names
    ]

    written = 0
    batch = []

    def flush():
        ok = dp.addFeatures(batch)
        if not (ok[0] if isinstance(ok, tuple) else ok):
            raise TransferError("err_add_features")
        return len(batch)

    for source_feature in reader.getFeatures():
        new_feature = QgsFeature(dst_fields)
        if source_feature.hasGeometry():
            new_feature.setGeometry(source_feature.geometry())
        values = [None] * dst_fields.count()
        for index, field in copy_plan:
            values[index] = _convert(field, source_feature[field.name()])
        new_feature.setAttributes(values)
        batch.append(new_feature)
        if len(batch) >= MAX_BATCH:
            written += flush()
            batch = []
    if batch:
        written += flush()
    del reader  # release the GeoPackage file handle (Windows)

    destination.updateExtents()
    destination.triggerRepaint()
    if written != expected:
        raise TransferError("err_count", written=written, expected=expected)
    return written
