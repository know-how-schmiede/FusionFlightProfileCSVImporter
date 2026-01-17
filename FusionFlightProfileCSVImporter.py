# Author: know-how-schmiede
# Description: Import flight profile data from CSV files and create 3D flight paths in Fusion 360.

import adsk.core, adsk.fusion, traceback
import csv
import os

# CONSTANTS
_CMD_ID = 'flight_profile_csv_importer_cmd'
_CMD_NAME = 'Import Flight Profile CSV'
_CMD_DESCRIPTION = 'Import flight profile data from CSV file and create a 3D spline'

_INSERT_PANEL_ID = 'InsertPanel'

# GLOBALS
_app = adsk.core.Application.cast(None)
_ui = adsk.core.UserInterface.cast(None)
_handlers = []

# CSV file to import
_csvFilename = ''

# Units available
UNIT_CONVERSION = {
    'mm': 0.1,      # mm to cm
    'cm': 1.0,      # cm to cm (base unit)
    'm': 100.0,     # meters to cm
    'in': 2.54,     # inches to cm
    'ft': 30.48     # feet to cm
}

def run(context):
    """Entry point for the add-in."""
    global _app, _ui
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface
        
        # Create the command definition
        cmdDefs = _ui.commandDefinitions
        
        # Check if command already exists
        cmdDef = cmdDefs.itemById(_CMD_ID)
        if cmdDef:
            cmdDef.deleteMe()
        
        # Create the new command definition
        cmdDef = cmdDefs.addButtonDefinition(
            _CMD_ID,
            _CMD_NAME,
            _CMD_DESCRIPTION
        )
        
        # Connect to the command created event
        onCommandCreated = CommandCreatedHandler()
        cmdDef.commandCreated.add(onCommandCreated)
        _handlers.append(onCommandCreated)
        
        # Get the Insert panel
        insertPanel = _ui.allToolbarPanels.itemById(_INSERT_PANEL_ID)
        if insertPanel:
            # Add the command to the panel
            insertPanel.controls.addCommand(cmdDef)
        
    except:
        if _ui:
            _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


def stop(context):
    """Clean up when the add-in is stopped."""
    global _ui
    try:
        # Get the command definition
        cmdDef = _ui.commandDefinitions.itemById(_CMD_ID)
        if cmdDef:
            cmdDef.deleteMe()
        
        # Remove the button from the Insert panel
        insertPanel = _ui.allToolbarPanels.itemById(_INSERT_PANEL_ID)
        if insertPanel:
            control = insertPanel.controls.itemById(_CMD_ID)
            if control:
                control.deleteMe()
    except:
        if _ui:
            _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


class CommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    """Handler for the command created event."""
    
    def __init__(self):
        super().__init__()
        
    def notify(self, args):
        try:
            global _handlers
            
            cmd = args.command
            
            # Connect to the execute event
            onExecute = CommandExecuteHandler()
            cmd.execute.add(onExecute)
            _handlers.append(onExecute)
            
            # Connect to the input changed event
            onInputChanged = CommandInputChangedHandler()
            cmd.inputChanged.add(onInputChanged)
            _handlers.append(onInputChanged)
            
            # Define the inputs
            inputs = cmd.commandInputs
            
            # Create dropdown for units
            unitDropdown = inputs.addDropDownCommandInput(
                'unitDropdown',
                'Units',
                adsk.core.DropDownStyles.TextListDropDownStyle
            )
            unitDropdown.listItems.add('Centimeters (cm)', True)
            unitDropdown.listItems.add('Millimeters (mm)', False)
            unitDropdown.listItems.add('Meters (m)', False)
            unitDropdown.listItems.add('Inches (in)', False)
            unitDropdown.listItems.add('Feet (ft)', False)
            
            # Create dropdown for style
            styleDropdown = inputs.addDropDownCommandInput(
                'styleDropdown',
                'Import Style',
                adsk.core.DropDownStyles.TextListDropDownStyle
            )
            styleDropdown.listItems.add('3D Spline (Flight Path)', True)
            styleDropdown.listItems.add('Points Only', False)
            styleDropdown.listItems.add('Connected Lines', False)
            
            # Create selection input for sketch (optional)
            sketchSelection = inputs.addSelectionInput(
                'sketchSelection',
                'Target Sketch (Optional)',
                'Select an existing sketch or leave empty to create a new one'
            )
            sketchSelection.addSelectionFilter('Sketches')
            sketchSelection.setSelectionLimits(0, 1)
            
            # Create dropdown for construction plane (used when no sketch selected)
            planeDropdown = inputs.addDropDownCommandInput(
                'planeDropdown',
                'Construction Plane',
                adsk.core.DropDownStyles.TextListDropDownStyle
            )
            planeDropdown.listItems.add('XY Plane', True)
            planeDropdown.listItems.add('XZ Plane', False)
            planeDropdown.listItems.add('YZ Plane', False)
            
        except:
            _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


class CommandInputChangedHandler(adsk.core.InputChangedEventHandler):
    """Handler for input changed events."""
    
    def __init__(self):
        super().__init__()
        
    def notify(self, args):
        try:
            # You can add logic here to update the UI based on user input
            pass
        except:
            _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


class CommandExecuteHandler(adsk.core.CommandEventHandler):
    """Handler for the execute event."""
    
    def __init__(self):
        super().__init__()
        
    def notify(self, args):
        try:
            global _app, _ui
            
            # Get the inputs
            inputs = args.command.commandInputs
            unitDropdown = inputs.itemById('unitDropdown')
            styleDropdown = inputs.itemById('styleDropdown')
            sketchSelection = inputs.itemById('sketchSelection')
            planeDropdown = inputs.itemById('planeDropdown')
            
            # Get selected values
            unitText = unitDropdown.selectedItem.name
            styleIndex = styleDropdown.selectedItem.index
            
            # Extract unit key
            unitKey = 'cm'  # default
            if 'mm' in unitText:
                unitKey = 'mm'
            elif 'm)' in unitText:
                unitKey = 'm'
            elif 'in' in unitText:
                unitKey = 'in'
            elif 'ft' in unitText:
                unitKey = 'ft'
            
            # Show file dialog
            fileDialog = _ui.createFileDialog()
            fileDialog.isMultiSelectEnabled = False
            fileDialog.title = 'Select CSV File'
            fileDialog.filter = 'CSV Files (*.csv);;All Files (*.*)'
            
            dialogResult = fileDialog.showOpen()
            if dialogResult != adsk.core.DialogResults.DialogOK:
                return
            
            csvFilename = fileDialog.filename
            
            # Read and process the CSV file
            points = readCSVFile(csvFilename, unitKey)
            
            if not points or len(points) == 0:
                _ui.messageBox('No valid points found in CSV file.')
                return
            
            # Get or create sketch
            sketch = None
            if sketchSelection.selectionCount > 0:
                sketch = sketchSelection.selection(0).entity
            else:
                # Create a new sketch on the selected construction plane
                design = adsk.fusion.Design.cast(_app.activeProduct)
                rootComp = design.rootComponent
                
                # Get the selected construction plane
                planeIndex = planeDropdown.selectedItem.index
                selectedPlane = None
                if planeIndex == 0:  # XY Plane
                    selectedPlane = rootComp.xYConstructionPlane
                elif planeIndex == 1:  # XZ Plane
                    selectedPlane = rootComp.xZConstructionPlane
                else:  # YZ Plane
                    selectedPlane = rootComp.yZConstructionPlane
                
                # Create sketch on the selected plane
                sketches = rootComp.sketches
                sketch = sketches.add(selectedPlane)
            
            # Create entities based on style
            if styleIndex == 0:  # 3D Spline
                createSpline(sketch, points)
            elif styleIndex == 1:  # Points Only
                createPoints(sketch, points)
            else:  # Connected Lines
                createLines(sketch, points)
            
            _ui.messageBox('Flight profile imported successfully!\n{} points processed.'.format(len(points)))
            
        except:
            _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


def readCSVFile(filename, unitKey):
    """Read points from CSV file and convert to cm."""
    points = []
    conversion = UNIT_CONVERSION.get(unitKey, 1.0)
    
    try:
        with open(filename, 'r') as csvfile:
            # Try to detect the CSV format
            sample = csvfile.read(1024)
            csvfile.seek(0)
            
            # Use csv.Sniffer to detect the delimiter
            try:
                dialect = csv.Sniffer().sniff(sample)
                reader = csv.reader(csvfile, dialect)
            except:
                # Fall back to comma delimiter
                reader = csv.reader(csvfile)
            
            for row in reader:
                # Skip empty rows
                if not row or len(row) == 0:
                    continue
                
                # Try to parse as numeric data
                try:
                    # Expect at least X, Y values, Z is optional
                    x = float(row[0]) * conversion
                    y = float(row[1]) * conversion if len(row) > 1 else 0.0
                    z = float(row[2]) * conversion if len(row) > 2 else 0.0
                    
                    # Create point (Fusion 360 uses cm as internal unit)
                    point = adsk.core.Point3D.create(x, y, z)
                    points.append(point)
                    
                except (ValueError, IndexError):
                    # Skip invalid rows (headers or non-numeric data)
                    continue
    
    except Exception as e:
        _ui.messageBox('Error reading CSV file:\n{}'.format(str(e)))
    
    return points


def createSpline(sketch, points):
    """Create a fitted spline through the points."""
    if len(points) < 2:
        _ui.messageBox('At least 2 points are required to create a spline.')
        return
    
    # Create spline
    splines = sketch.sketchCurves.sketchFittedSplines
    splines.add(points)


def createPoints(sketch, points):
    """Create sketch points."""
    sketchPoints = sketch.sketchPoints
    for point in points:
        sketchPoints.add(point)


def createLines(sketch, points):
    """Create connected lines between points."""
    if len(points) < 2:
        _ui.messageBox('At least 2 points are required to create lines.')
        return
    
    lines = sketch.sketchCurves.sketchLines
    for i in range(len(points) - 1):
        lines.addByTwoPoints(points[i], points[i + 1])
