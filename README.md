# FusionFlightProfileCSVImporter

Fusion 360 add-in to import an airfoil profile CSV into a selected sketch and create a fitted spline.

## Install
1. Copy the folder `FusionFlightProfileCSVImporter` (inside this repo) into your Fusion 360 AddIns directory.
2. In Fusion 360, open Add-Ins and enable "FusionFlightProfileCSVImporter".

## Use
1. Open or create a sketch.
2. Run "Import Airfoil CSV" from the Sketch > Create panel.
3. Select a target sketch, browse for a CSV file, and click OK.

CSV format: each line should contain two numeric values (x, y). Extra columns are ignored.
