# FlightProfiles (Fusion 360 Add-in)

Fusion 360 Add-in zum Import einer Tragflaechenprofil-CSV in eine ausgewaehlte Skizze oder Ebene und zum Erzeugen eines geschlossenen Profils.

## Installation
1. Kopiere den Ordner `FlightProfiles` in dein Fusion 360 AddIns-Verzeichnis.
2. In Fusion 360 das Add-in "FlightProfiles" in den Add-Ins aktivieren.

## Verwendung
1. "Import Airfoil CSV" im Volumenkoerper > Erstellen-Panel ausfuehren.
2. Zielskizze oder Ebene fuer Profil 1 waehlen.
3. CSV-Dateien fuer Profil 1 und Profil 2 auswaehlen.
4. Profiltiefe und den Abstand fuer Profil 2 angeben.
5. OK klicken, um zwei geschlossene Profile aus Linien zu erzeugen.

CSV-Format: Jede Zeile enthaelt zwei numerische Werte (x, y). Weitere Spalten werden ignoriert.

## Versionierung
- Version in `FlightProfiles/version.py` pflegen.
- `FlightProfiles/FlightProfiles.manifest` und `version.md` synchron halten.
