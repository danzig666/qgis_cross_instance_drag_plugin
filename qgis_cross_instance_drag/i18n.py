"""Minimal English/Hungarian message catalogue.

The language follows the QGIS user interface locale: Hungarian when QGIS runs
in Hungarian, English otherwise. A plain dictionary is used instead of Qt
.ts/.qm files so the plugin has no build step.
"""

from qgis.core import QgsApplication, QgsSettings

PLUGIN_NAME = "Cross-Instance Layer Drag"

MESSAGES = {
    "menu_prepare": {
        "en": "Prepare selected memory layers for dragging",
        "hu": "Kijelölt memóriarétegek előkészítése az áthúzáshoz",
    },
    "menu_cleanup": {
        "en": "Delete temporary snapshot files",
        "hu": "Ideiglenes pillanatkép-fájlok törlése",
    },
    "prepared": {
        "en": "Prepared {count} memory layer(s).",
        "hu": "Előkészítve: {count} memória-réteg.",
    },
    "prepare_failed": {
        "en": "Could not prepare memory layers: {error}",
        "hu": "Memóriarétegek előkészítése sikertelen: {error}",
    },
    "cleanup_done": {
        "en": "Deleted {count} temporary snapshot file(s).",
        "hu": "Törölve: {count} ideiglenes pillanatkép-fájl.",
    },
    "drop_result": {
        "en": "Dropped {count} layer(s); original ID kept: {kept}; "
              "ID collisions: {collisions}; memory features copied: {features}.",
        "hu": "Áthúzva: {count} réteg; eredeti ID megmaradt: {kept}; "
              "ID-ütközés: {collisions}; átmásolt memóriarekord: {features}.",
    },
    "drop_failed": {
        "en": "Drop aborted: {error}",
        "hu": "Az áthúzás megszakadt: {error}",
    },
    "missing_snapshots": {
        "en": "No data snapshot for memory layer(s): {names}. They were added "
              "empty. Enable this plugin in the SOURCE QGIS too.",
        "hu": "Nincs adatmásolat a következő memóriaréteg(ek)hez: {names}. "
              "Üresen kerültek át. A plugint a FORRÁS QGIS-ben is engedélyezd.",
    },
    "err_bad_xml": {
        "en": "The QGIS layer definition XML is invalid.",
        "hu": "A QGIS rétegdefiníció XML-je hibás.",
    },
    "err_bad_id": {
        "en": "Missing or duplicated original layer ID.",
        "hu": "Hiányzó vagy ismétlődő eredeti layer ID.",
    },
    "err_no_layers": {
        "en": "The dragged QGIS data contains no layers.",
        "hu": "Nincs áthúzható réteg a QGIS-adatban.",
    },
    "err_unsupported": {
        "en": "Some of the dragged layers could not be loaded ({loaded}/{total}).",
        "hu": "Az áthúzott rétegek egy része nem tölthető be ({loaded}/{total}).",
    },
    "err_id_mismatch": {
        "en": "Loaded layer ID does not match: {id}",
        "hu": "Nem egyezik a betöltött layer ID: {id}",
    },
    "err_not_memory": {
        "en": "Layer was not loaded as a memory layer: {id}",
        "hu": "Nem memória-rétegként töltődött be: {id}",
    },
    "err_id_collision": {
        "en": "Layer ID collision during import: {id}",
        "hu": "Layer ID ütközés import közben: {id}",
    },
    "err_tree": {
        "en": "Could not restore the layer tree.",
        "hu": "Nem sikerült a rétegfa visszaállítása.",
    },
    "err_bad_snapshot": {
        "en": "Invalid memory data snapshot: {id}",
        "hu": "Hibás memória-adatmásolat: {id}",
    },
    "err_snapshot_gpkg": {
        "en": "The snapshot GeoPackage is missing or cannot be opened: {id}",
        "hu": "A pillanatkép GeoPackage hiányzik vagy nem nyitható meg: {id}",
    },
    "err_export": {
        "en": "GeoPackage export failed: {error}",
        "hu": "GeoPackage exportálási hiba: {error}",
    },
    "err_fields": {
        "en": "Could not restore the fields of the memory layer.",
        "hu": "Nem lehet visszaállítani a memória-réteg mezőit.",
    },
    "err_add_features": {
        "en": "Could not copy features into the memory layer.",
        "hu": "Nem sikerült memóriarekordokat másolni.",
    },
    "err_count": {
        "en": "Feature count mismatch: {written} / {expected}",
        "hu": "Eltérő memóriarekord-szám: {written} / {expected}",
    },
}


def _detect_language():
    locale = ""
    try:
        locale = QgsApplication.locale() or ""
    except Exception:  # very old API or no application instance
        pass
    if not locale:
        settings = QgsSettings()
        if settings.value("locale/overrideFlag", False, type=bool):
            locale = settings.value("locale/userLocale", "", type=str)
    return "hu" if locale.lower().startswith("hu") else "en"


LANGUAGE = _detect_language()


def tr(key, **kwargs):
    entry = MESSAGES[key]
    text = entry.get(LANGUAGE) or entry["en"]
    return text.format(**kwargs) if kwargs else text


class TransferError(RuntimeError):
    """Error whose message is already translated."""

    def __init__(self, key, **kwargs):
        super().__init__(tr(key, **kwargs))
