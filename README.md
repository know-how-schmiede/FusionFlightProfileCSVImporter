# Fusion Flight Profile CSV Importer

A Fusion 360 add-in for importing flight profile data from CSV files and creating 3D flight paths using splines, lines, or points.

## Features

- Import X, Y, Z coordinates from CSV files
- Multiple import styles:
  - **3D Spline (Flight Path)**: Creates a smooth spline through all points
  - **Points Only**: Creates individual sketch points
  - **Connected Lines**: Creates straight lines connecting points
- Support for multiple units: cm, mm, m, inches, feet
- Option to import into existing sketch or create new sketch
- Choose construction plane (XY, XZ, YZ) for new sketches

## Installation

### Automatic Installation (Recommended)

1. Download the ZIP file from GitHub (Click "Code" → "Download ZIP")
2. Extract the ZIP file
3. Copy the entire `FusionFlightProfileCSVImporter` folder to your Fusion 360 Add-Ins directory:
   - **Windows**: `C:\Users\%USERNAME%\AppData\Roaming\Autodesk\Autodesk Fusion 360\API\AddIns`
   - **Mac**: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/`
4. Restart Fusion 360
5. Click "Scripts and Add-Ins" in the toolbar
6. Select the "Add-Ins" tab
7. Select "FusionFlightProfileCSVImporter" and click "Run"

### Manual Installation

If the add-in doesn't appear automatically:

1. Open Fusion 360
2. Click "Scripts and Add-Ins" in the toolbar (or press Shift+S)
3. Click the "+" button next to "My Add-Ins"
4. Navigate to the folder containing the add-in files
5. Click "Select Folder"
6. The add-in should now appear in the list
7. Click "Run" to start the add-in

## Usage

1. **Prepare your CSV file**
   - Format: `X,Y,Z` (one point per line)
   - Z coordinate is optional
   - Header rows are automatically skipped
   - Example:
     ```
     X,Y,Z
     0,0,0
     10,5,2
     20,8,5
     30,10,8
     ```

2. **Run the add-in**
   - In Fusion 360, go to the "Insert" menu
   - Click "Import Flight Profile CSV"

3. **Configure import settings**
   - **Units**: Select the units used in your CSV file (cm, mm, m, inches, feet)
   - **Import Style**: Choose how to represent the data:
     - 3D Spline: Smooth curve (best for flight paths)
     - Points Only: Individual points
     - Connected Lines: Straight segments
   - **Target Sketch**: (Optional) Select an existing sketch or leave empty for new sketch
   - **Construction Plane**: Choose XY, XZ, or YZ plane (used for new sketches)

4. **Select CSV file**
   - Click "OK" to open file dialog
   - Select your CSV file
   - Click "Open"

5. **View results**
   - The flight path will be created in the sketch
   - A confirmation message shows the number of points imported

## CSV File Format

### Basic Format
```csv
X,Y,Z
0,0,0
10,5,100
20,8,200
30,10,300
```

### 2D Format (Z defaults to 0)
```csv
X,Y
0,0
10,5
20,8
30,10
```

### Without Headers
```csv
0,0,0
10,5,100
20,8,200
30,10,300
```

### Notes
- Blank lines are ignored
- Non-numeric rows (headers) are automatically skipped
- The add-in auto-detects the CSV delimiter (comma, tab, etc.)
- Values are converted to Fusion 360's internal unit (cm) based on your selection

## Examples

### Flight Path Data
A typical flight profile might include altitude over time:
```csv
Distance,Lateral,Altitude
0,0,0
1000,50,100
2000,80,500
3000,100,1000
4000,110,1200
5000,100,1000
6000,50,500
7000,0,100
8000,0,0
```

### 3D Trajectory
Complex 3D paths with all coordinates:
```csv
X,Y,Z
0.0,0.0,0.0
1.5,2.3,0.5
3.2,4.1,1.2
5.0,5.5,2.0
6.8,6.2,2.5
8.5,6.0,2.8
10.0,5.0,3.0
```

## Troubleshooting

### Add-in doesn't appear in the list
- Make sure the folder is in the correct Add-Ins directory
- Check that both `.py` and `.manifest` files are present
- Restart Fusion 360

### Import fails
- Check CSV file format (should be comma-separated values)
- Verify that data rows contain numeric values
- Try a simple test file with a few points first

### Spline doesn't look smooth
- Increase the number of points in your CSV file
- Try using "3D Spline" style instead of "Connected Lines"

### Units seem wrong
- Double-check the units selected match your CSV data
- Remember that Fusion 360 uses centimeters internally

## Development

This add-in is written in Python using the Fusion 360 API.

### Files
- `FusionFlightProfileCSVImporter.py`: Main Python script
- `FusionFlightProfileCSVImporter.manifest`: Add-in metadata

### Contributing
Contributions are welcome! Please feel free to submit issues or pull requests.

## License

See LICENSE file for details.

## Credits

Developed by know-how-schmiede

Inspired by existing Fusion 360 CSV import tools and the community's need for specialized flight profile import capabilities.