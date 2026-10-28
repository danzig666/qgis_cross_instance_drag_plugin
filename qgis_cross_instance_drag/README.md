# Cross-Instance Layer Drag – v0.2.0

*Magyarul: [README_HU.md](README_HU.md)*

## Purpose

When dragging layers between two **separate QGIS processes**:

- keep the original layer ID (`layer.id()`) when it is free in the target project;
- on a collision only the colliding layer gets a new ID, and references inside the layer definition (layer tree, joins, dependencies, editor widgets) are rewritten;
- copy the features (geometry + attributes, including unsaved edits) of `memory` provider layers;
- transfer the layer tree (groups), style and layer settings through QGIS' own QLR data.

The user interface is Hungarian when QGIS runs in Hungarian, English otherwise.

## Installation

1. QGIS → **Plugins → Manage and Install Plugins → Install from ZIP**.
2. Select `qgis_cross_instance_drag.zip`.
3. Enable the plugin in **both QGIS instances**.
4. Drag a layer (or group) from the **Layers** panel of the source QGIS onto the **Layers** panel or map canvas of the other QGIS.
5. The message bar of the receiving QGIS shows the result (kept IDs, collisions, copied features).

Supports QGIS 3.22 – 3.x and QGIS 4.x (Qt6).

**Important:** preserving IDs only needs the plugin in the receiving instance, but copying memory-layer data needs it in the *source* too. Without a snapshot the memory layer arrives empty and the plugin warns you. If the snapshot is not created automatically for some reason, select the layers in the source and use **Plugins → Cross-Instance Layer Drag → Prepare selected memory layers for dragging** right before dragging.

## How it works

- **Source side:** when a drag starts in the Layers panel, the plugin writes a GeoPackage snapshot of the selected memory layers (also inside selected groups) into the system temp folder (`qgis_cross_instance_drag_v1/<PID>/`), with a small JSON metadata file.
- **Receiving side:** if an incoming QGIS layer drag comes from *another* QGIS process, the plugin loads the QLR XML sent by QGIS with `QgsLayerDefinition.loadLayerDefinitionLayers()`, which, unlike the regular loader, does not replace the IDs. Memory layers are refilled from the snapshot. Reordering within one instance is not affected.
- A snapshot is valid for 10 minutes; files older than 30 minutes are deleted when the plugin starts. Your own files can be deleted immediately with **Delete temporary snapshot files**.

## Limitations

- **Experimental.** Verified with headless tests on QGIS 3.44 and 4.2 (snapshot, ID preservation, ID collision, groups, drop position), but not with a real mouse drag between two instances. Back up your projects and try it with test layers first.
- For file, database, WMS, raster etc. layers only the **layer definition and data source reference** are transferred, not the data. The data source must be reachable from the target instance.
- **Unsaved edits** of disk-based layers are not transferred; those of memory layers are.
- Because data goes through a GeoPackage, some special field types (list, map, binary) may be converted.
- Feature order and internal feature IDs may differ from the source.
- An ID that already exists in the target project is never overwritten.
- Relations and expressions referring to other project layers cannot always be reconstructed; exact XML IDs are rewritten.
- With large memory layers starting a drag can be noticeably slower (a fresh snapshot is taken on every drag so stale data is never transferred).
- The temporary GeoPackages live in the user's temp folder; use the delete menu item for sensitive data.

## Check

In the Python console of the source QGIS:

```python
layer = iface.activeLayer()
print(layer.id(), layer.providerType(), layer.featureCount())
```

Run the same in the receiving instance after the drop. Without an ID collision the ID must match; for memory layers the feature count too.

## License

GNU General Public License v2.0 or later.
