# FlightProfiles (Fusion 360 Add-in)

Fusion 360 add-in to import an airfoil profile CSV into a selected sketch or plane and create a closed profile.

## Install
1. Copy the folder `FlightProfiles` into your Fusion 360 AddIns directory.
2. In Fusion 360, open Add-Ins and enable "FlightProfiles".

## Use
1. Run "Import Airfoil CSV" from the Solid > Create panel.
2. Select a target sketch or plane for profile 1.
3. In the Profile 1 group, choose a CSV file, set the profile depth, and optional mirror.
4. In the Profile 2 group, choose a CSV file, set its profile depth, optional mirror, the offset distance, and the rotation angle.
5. Optional: enable "Create Solid (Loft)" to build a body between the two profiles (sketches are hidden after creation).
6. Click OK to create two closed profiles using splines and end-cap lines.

CSV format: each line should contain two numeric values (x, y). Extra columns are ignored.

CSV validation and correction:
- Expected order: start at trailing edge upper (x near max, y >= 0), move to the leading edge, then return along the lower surface to the trailing edge.
- If points alternate between upper/lower surfaces or the file ends with repeated trailing-edge rows, the add-in writes a corrected file with a `_sort` suffix and uses it automatically.
- The corrected file keeps the original delimiter/decimal format and writes Z=0 when the source CSV has three columns.

## Versioning
- Update `FlightProfiles/version.py` for the code version.
- Keep `FlightProfiles/FlightProfiles.manifest` and `version.md` in sync.
