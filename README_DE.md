# FlightProfiles (Fusion 360 Add-in)

Fusion 360 Add-in zum Import einer Tragflaechenprofil-CSV in eine ausgewaehlte Skizze oder Ebene und zum Erzeugen eines geschlossenen Profils.

## Installation
1. Kopiere den Ordner `FlightProfiles` in dein Fusion 360 AddIns-Verzeichnis.
2. In Fusion 360 das Add-in "FlightProfiles" in den Add-Ins aktivieren.

## Verwendung
1. "Import Airfoil CSV" im Volumenkoerper > Erstellen-Panel ausfuehren.
2. Zielskizze oder Ebene fuer Profil 1 waehlen.
3. In der Gruppe "Profile 1" CSV-Datei waehlen, Profiltiefe setzen und optional spiegeln.
4. In der Gruppe "Profile 2" CSV-Datei waehlen, Profiltiefe setzen, optional spiegeln, den Abstand und den Drehwinkel angeben.
5. Optional "Create Solid (Loft)" aktivieren, um einen Koerper zwischen den Profilen zu erzeugen (Skizzen werden danach ausgeblendet).
6. OK klicken, um zwei geschlossene Profile aus Splines und Abschlusslinien zu erzeugen.

CSV-Format: Jede Zeile enthaelt zwei numerische Werte (x, y). Weitere Spalten werden ignoriert.

CSV-Pruefung und Korrektur:
- Erwartete Reihenfolge: Start an der Hinterkante oben (x nahe max, y >= 0), zur Nase, dann an der Unterseite zur Hinterkante zurueck.
- Wenn Punkte zwischen Ober- und Unterseite springen oder die Datei mit mehrfachen Hinterkanten-Zeilen endet, schreibt das Add-in eine korrigierte Datei mit dem Suffix `_sort` und verwendet diese automatisch.
- Die korrigierte Datei behaelt Trennzeichen/Dezimalformat bei und schreibt Z=0, wenn die Quelle drei Spalten enthaelt.

## Versionierung
- Version in `FlightProfiles/version.py` pflegen.
- `FlightProfiles/FlightProfiles.manifest` und `version.md` synchron halten.
