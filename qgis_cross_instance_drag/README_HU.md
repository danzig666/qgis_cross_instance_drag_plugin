# Rétegáthúzás QGIS-példányok között (Cross-Instance Layer Drag) – v0.2.0

*English: [README.md](README.md)*

## Cél

Két **külön QGIS-folyamat** közötti rétegáthúzásnál:

- az eredeti rétegazonosító (`layer.id()`) megőrzése, ha szabad a fogadó projektben;
- ütközéskor csak az ütköző réteg kap új ID-t, a rétegdefiníció belső hivatkozásai (rétegfa, joinok, függőségek, szerkesztő widgetek) átíródnak;
- memória-providerrel (`memory`) létrehozott vektorrétegek objektumainak (geometria + attribútumok, a nem mentett szerkesztésekkel együtt) átvitele;
- rétegfa (csoportok), stílus és rétegbeállítások átvitele a QGIS saját QLR adatán keresztül.

A plugin felülete magyar, ha a QGIS magyar nyelven fut, egyébként angol.

## Telepítés

1. QGIS → **Bővítmények → Bővítmények kezelése és telepítése → Telepítés ZIP-ből**.
2. Válaszd ki a `qgis_cross_instance_drag.zip` fájlt.
3. Engedélyezd a plugint **mindkét QGIS-példányban**.
4. Húzz át réteget (vagy csoportot) a forrás QGIS **Rétegek** paneljéből a másik QGIS **Rétegek** paneljébe vagy térképvásznára.
5. A fogadó QGIS üzenetsora mutatja az eredményt (megtartott ID-k, ütközések, átmásolt rekordok).

QGIS 3.22 – 3.x és QGIS 4.x (Qt6) is támogatott.

**Fontos:** az ID-k megőrzéséhez elég, ha a fogadó példányban fut a plugin, a memóriaadatok átviteléhez viszont a *forrásban is* futnia kell. Ha a forrásban nincs pillanatkép, a memóriaréteg üresen kerül át, és a plugin figyelmeztet. Ha a pillanatkép valamiért nem készülne el automatikusan, a forrásban jelöld ki a rétegeket, és közvetlenül az áthúzás előtt válaszd a **Bővítmények → Cross-Instance Layer Drag → Kijelölt memóriarétegek előkészítése az áthúzáshoz** menüpontot.

## Működés

- **Forrásoldal:** amikor a Rétegek panelen elindul a húzás, a plugin a kijelölt (csoportokon belüli) memóriarétegekről GeoPackage-pillanatképet ír a rendszer ideiglenes mappájába (`qgis_cross_instance_drag_v1/<PID>/`), egy rövid JSON-metaadatfájllal.
- **Fogadóoldal:** ha a beérkező QGIS-húzás egy *másik* QGIS-folyamatból jön, a plugin a QGIS által küldött QLR XML-t a `QgsLayerDefinition.loadLayerDefinitionLayers()` függvénnyel tölti be, amely – a szokásos betöltéssel ellentétben – nem cseréli le az ID-kat. A memóriarétegekbe a pillanatképből visszamásolja a rekordokat. Az egy példányon belüli átrendezést nem érinti.
- A pillanatkép 10 percig érvényes; a 30 percnél régebbi fájlokat a plugin indításkor törli. A saját fájlok azonnal törölhetők a **Ideiglenes pillanatkép-fájlok törlése** menüponttal.

## Korlátok

- **Kísérleti plugin.** Fej nélküli (headless) teszttel ellenőrizve QGIS 3.44 és 4.2 alatt (pillanatkép, ID-megőrzés, ID-ütközés, csoportok, ejtési pozíció), de valódi két példány közötti egérhúzással nem. Készíts biztonsági másolatot, és először próbarétegekkel próbáld ki.
- A fájlos, adatbázisos, WMS-, raszter- stb. rétegeknél csak a **rétegdefiníció és az adatforrás-hivatkozás** kerül át, az adat nem. Az adatforrásnak a célpéldányból is elérhetőnek kell lennie.
- A lemezhez kötött rétegek **nem mentett szerkesztései** nem kerülnek át; a memóriarétegeké igen.
- A GeoPackage-on keresztüli másolás miatt egyes speciális mezőtípusok (lista, map, bináris) átalakulhatnak.
- A rekordok sorrendje és a belső feature ID-k eltérhetnek a forrásétól.
- A célprojektben már létező layer ID-t a plugin soha nem írja felül.
- A más projektrétegekre hivatkozó relációk, kifejezések nem minden esetben rekonstruálhatók; a pontos XML-azonosítókat átírja.
- Nagy memóriarétegeknél a húzás indítása érezhetően lassabb lehet (minden húzáskor friss pillanatkép készül, hogy ne kerüljön át elavult adat).
- Az ideiglenes GeoPackage-ok a felhasználó temp-könyvtárában vannak; érzékeny adatoknál használd a törlés menüpontot.

## Ellenőrzés

A forrás QGIS Python-konzoljában:

```python
layer = iface.activeLayer()
print(layer.id(), layer.providerType(), layer.featureCount())
```

Áthúzás után a fogadó példányban ugyanez. Ha nem volt ID-ütközés, az ID-nak egyeznie kell; memóriarétegnél a rekordok számának is.
