# FlightProfiles (Fusion 360 Add-in)

Fusion 360 add-in to import an airfoil profile CSV into a selected sketch or plane and create a closed profile.

## Install
1. Copy the folder `FlightProfiles` into your Fusion 360 AddIns directory.
2. In Fusion 360, open Add-Ins and enable "FlightProfiles".

## Use
1. Run "Import Airfoil CSV" from the Solid > Create panel.
2. Select a target sketch or plane for profile 1.
3. Choose CSV files for profile 1 and profile 2.
4. Set the profile depth and the offset distance for profile 2.
5. Click OK to create two closed profiles using lines.

CSV format: each line should contain two numeric values (x, y). Extra columns are ignored.

## Versioning
- Update `FlightProfiles/version.py` for the code version.
- Keep `FlightProfiles/FlightProfiles.manifest` and `version.md` in sync.
