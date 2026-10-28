"""Cross-instance layer drag & drop for QGIS 3.22+ / 4.x.

Intercepts QGIS layer-tree drops coming from ANOTHER QGIS process (onto the
Layers panel or onto the main window / map canvas) and rebuilds the layers so
that their original IDs are kept and memory-layer features are copied. Drops
within the same QGIS process are left to QGIS.

Experimental plugin, not a QGIS core patch. Uncommitted edits of persistent
layers and external data files are not copied, only their definitions.
"""

import os
import traceback

from qgis.PyQt.QtCore import QEvent, QObject, QPoint, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QApplication
from qgis.core import Qgis, QgsLayerTreeGroup, QgsMessageLog, QgsProject

from . import transfer
from .i18n import PLUGIN_NAME, tr

ICON_PATH = os.path.join(os.path.dirname(__file__), "icon.png")

ABOVE, BELOW, ON_ITEM, ON_VIEWPORT = range(4)


def _event_pos(event):
    """Event position as QPoint for both Qt5 and Qt6."""
    if hasattr(event, "position"):
        return event.position().toPoint()
    return event.pos()


class CrossInstanceDrag(QObject):
    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.iface = iface
        self.view = iface.layerTreeView()
        self.press_pos = None
        self.snapshot_done = False
        self.actions = []
        self._watched = []

    # ------------------------------------------------------------------ setup

    def initGui(self):
        self._watched = [self.view.viewport(), self.iface.mainWindow()]
        for widget in self._watched:
            widget.installEventFilter(self)

        icon = QIcon(ICON_PATH)
        prepare = QAction(icon, tr("menu_prepare"), self.iface.mainWindow())
        prepare.triggered.connect(self.prepare_selected)
        cleanup = QAction(tr("menu_cleanup"), self.iface.mainWindow())
        cleanup.triggered.connect(self.cleanup)
        for action in (prepare, cleanup):
            self.iface.addPluginToMenu(PLUGIN_NAME, action)
            self.actions.append(action)

        try:
            transfer.cleanup_snapshots()
        except OSError:
            pass

    def unload(self):
        for widget in self._watched:
            try:
                widget.removeEventFilter(self)
            except RuntimeError:  # widget already deleted
                pass
        self._watched = []
        for action in self.actions:
            self.iface.removePluginMenu(PLUGIN_NAME, action)
            action.deleteLater()
        self.actions = []
        # Snapshot files are kept on purpose: the receiving QGIS may still be
        # reading them. They expire by age.

    # ----------------------------------------------------------------- events

    def eventFilter(self, watched, event):
        try:
            kind = event.type()
        except RuntimeError:
            return False
        if watched is self.view.viewport():
            if kind == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    self.press_pos = _event_pos(event)
                    self.snapshot_done = False
            elif kind == QEvent.Type.MouseButtonRelease:
                self.press_pos = None
                self.snapshot_done = False
            elif kind == QEvent.Type.MouseMove:
                self._maybe_stage(event)
            elif kind == QEvent.Type.Drop:
                return self._handle_drop(event, on_tree=True)
        elif watched is self.iface.mainWindow() and kind == QEvent.Type.Drop:
            return self._handle_drop(event, on_tree=False)
        return False

    def _maybe_stage(self, event):
        # Same threshold as QAbstractItemView uses to start the drag, and the
        # filter runs before the view: the snapshot exists before QDrag starts.
        if (
            self.press_pos is None
            or self.snapshot_done
            or not (event.buttons() & Qt.MouseButton.LeftButton)
            or (_event_pos(event) - self.press_pos).manhattanLength() < QApplication.startDragDistance()
        ):
            return
        self.snapshot_done = True
        try:
            transfer.stage_memory_layers(
                self.view.selectedLayersRecursive(), QgsProject.instance().transformContext()
            )
        except Exception as exc:
            self._warn(tr("prepare_failed", error=exc))

    def _handle_drop(self, event, on_tree):
        mime = event.mimeData()
        origin_pid = transfer.foreign_origin_pid(mime)
        if origin_pid is None:
            return False  # not ours: same-process reorder, files, URIs...

        # Whatever happens, QGIS' default handler must not run afterwards: it
        # would add a second copy (with new IDs and empty memory layers).
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        try:
            if on_tree:
                group, index = self._tree_drop_target(_event_pos(event))
            else:
                group, index = self._default_insertion_point()
            xml = bytes(mime.data(transfer.FORMAT_QGIS_QLR)).decode("utf-8")
            result = transfer.import_layer_definition(
                xml, origin_pid, QgsProject.instance(), group, index
            )
        except Exception as exc:
            self._warn(tr("drop_failed", error=exc))
            return True

        self.iface.messageBar().pushMessage(
            PLUGIN_NAME,
            tr(
                "drop_result",
                count=result.count,
                kept=result.kept,
                collisions=result.collisions,
                features=result.features,
            ),
            Qgis.MessageLevel.Info,
            5,
        )
        if result.missing_snapshots:
            self._warn(tr("missing_snapshots", names=", ".join(result.missing_snapshots)), trace=False)
        return True

    # ------------------------------------------------------------ drop target

    def _drop_indicator(self, pos, index):
        """Re-implementation of QAbstractItemView's drop indicator logic;
        dropIndicatorPosition() is protected and cannot be called from Python
        on the view created by QGIS."""
        rect = self.view.visualRect(index)
        margin = max(2, min(12, round(rect.height() / 5.5)))
        if pos.y() - rect.top() < margin:
            return ABOVE
        if rect.bottom() - pos.y() < margin:
            return BELOW
        if rect.contains(pos, True):
            if self.view.model().flags(index) & Qt.ItemFlag.ItemIsDropEnabled:
                return ON_ITEM
            return ABOVE if pos.y() < rect.center().y() else BELOW
        return ON_VIEWPORT

    def _tree_drop_target(self, pos):
        root = QgsProject.instance().layerTreeRoot()
        index = self.view.indexAt(pos)
        if not index.isValid():
            return root, -1
        node = self.view.index2node(index)
        if node is None:
            return root, -1
        indicator = self._drop_indicator(pos, index)
        if isinstance(node, QgsLayerTreeGroup) and indicator == ON_ITEM:
            return node, 0
        parent = node.parent()
        if not isinstance(parent, QgsLayerTreeGroup):
            return root, -1
        position = parent.children().index(node)
        if indicator in (BELOW, ON_ITEM):
            position += 1
        return parent, position

    def _default_insertion_point(self):
        """Where QGIS would put a newly added layer (current group/layer)."""
        project = QgsProject.instance()
        try:
            point = project.layerTreeRegistryBridge().layerInsertionPoint()
            return point.group, point.position
        except AttributeError:
            return project.layerTreeRoot(), 0

    # ---------------------------------------------------------------- actions

    def prepare_selected(self):
        try:
            count = transfer.stage_memory_layers(
                self.view.selectedLayersRecursive(), QgsProject.instance().transformContext()
            )
            self.iface.messageBar().pushSuccess(PLUGIN_NAME, tr("prepared", count=count))
        except Exception as exc:
            self._warn(tr("prepare_failed", error=exc))

    def cleanup(self):
        try:
            count = transfer.cleanup_snapshots(max_age=0, own_only=True)
            self.iface.messageBar().pushSuccess(PLUGIN_NAME, tr("cleanup_done", count=count))
        except Exception as exc:
            self._warn(str(exc))

    def _warn(self, message, trace=True):
        self.iface.messageBar().pushWarning(PLUGIN_NAME, message)
        details = message
        if trace:
            details += "\n" + traceback.format_exc()
        QgsMessageLog.logMessage(details, PLUGIN_NAME, Qgis.MessageLevel.Warning)
