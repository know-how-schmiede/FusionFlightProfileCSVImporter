# Sample CSV Files

This directory contains sample CSV files to demonstrate the Fusion Flight Profile CSV Importer.

## Files

### simple_flight_path.csv
A basic flight path with X, Y, Z coordinates showing a simple ascending and curved trajectory.
- 9 points
- Includes headers
- All coordinates in the same unit

### flight_profile_with_headers.csv
A more realistic flight profile with labeled columns (Distance, Lateral, Altitude).
- 13 points
- Shows takeoff, climb, cruise, and landing phases
- Demonstrates header row handling

### curved_3d_path.csv
A smooth 3D curved path without headers.
- 11 points
- No header row (demonstrates auto-detection)
- Good for testing spline smoothness

### 2d_profile.csv
A 2D profile (X, Y only) - Z defaults to 0.
- 8 points
- Demonstrates 2D import capability
- Useful for side-view profiles

## Usage

1. Load the add-in in Fusion 360
2. Click "Insert" → "Import Flight Profile CSV"
3. Configure your settings
4. Select one of these sample files
5. Click "Open" to import

## Tips

- Try different import styles (Spline, Points, Lines) with the same file
- Experiment with different units to see the scaling
- Use these as templates for your own flight profile data
