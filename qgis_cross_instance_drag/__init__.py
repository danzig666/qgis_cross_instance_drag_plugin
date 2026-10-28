"""QGIS plugin entry point."""


def classFactory(iface):
    from .plugin import CrossInstanceDrag
    return CrossInstanceDrag(iface)
