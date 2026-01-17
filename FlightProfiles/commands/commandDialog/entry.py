import adsk.core
import adsk.fusion
import os
import re
from ...lib import fusionAddInUtils as futil
from ... import config

app = adsk.core.Application.get()
ui = app.userInterface

CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_importAirfoilCsv'
CMD_NAME = 'Import Airfoil CSV'
CMD_DESCRIPTION = f'Import an airfoil profile CSV into a selected sketch. (v{config.VERSION})'

IS_PROMOTED = True

WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_ID = 'SolidCreatePanel'

ICON_FOLDER = ''

local_handlers = []


def _parse_profile_points(file_path):
    pattern = r"[-+]?(?:\d+(?:[.,]\d+)?|[.,]\d+)(?:[eE][-+]?\d+)?"
    points = []

    with open(file_path, "r", newline="") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            matches = re.findall(pattern, line)
            if len(matches) < 2:
                continue

            x_val = float(matches[0].replace(",", "."))
            y_val = float(matches[1].replace(",", "."))
            points.append((x_val, y_val))

    return points


def _split_profile(points, x_tol=1e-9):
    lower_pts = []
    upper_pts = []
    current_x = None
    current_ys = []

    def flush_group():
        if current_x is None or not current_ys:
            return
        lower_y = min(current_ys)
        upper_y = max(current_ys)
        lower_pts.append(adsk.core.Point3D.create(current_x, lower_y, 0))
        upper_pts.append(adsk.core.Point3D.create(current_x, upper_y, 0))

    for x_val, y_val in points:
        if current_x is None or abs(x_val - current_x) <= x_tol:
            current_x = x_val if current_x is None else current_x
            current_ys.append(y_val)
        else:
            flush_group()
            current_x = x_val
            current_ys = [y_val]

    flush_group()
    return lower_pts, upper_pts


def _add_polyline(sketch_lines, points):
    for idx in range(len(points) - 1):
        sketch_lines.addByTwoPoints(points[idx], points[idx + 1])


def start():
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_DESCRIPTION, ICON_FOLDER
    )

    futil.add_handler(cmd_def.commandCreated, command_created)

    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    control = panel.controls.addCommand(cmd_def)
    control.isPromoted = IS_PROMOTED


def stop():
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    command_control = panel.controls.itemById(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)

    if command_control:
        command_control.deleteMe()

    if command_definition:
        command_definition.deleteMe()


def command_created(args: adsk.core.CommandCreatedEventArgs):
    futil.log(f'{CMD_NAME} Command Created Event')

    inputs = args.command.commandInputs

    sketch_input = inputs.addSelectionInput(
        "targetSketch",
        "Target Sketch or Plane",
        "Select a sketch, construction plane, or planar face to receive the profile.",
    )
    sketch_input.addSelectionFilter("Sketches")
    sketch_input.addSelectionFilter("ConstructionPlanes")
    sketch_input.addSelectionFilter("PlanarFaces")
    sketch_input.setSelectionLimits(1, 1)

    active_sketch = adsk.fusion.Sketch.cast(app.activeEditObject)
    if active_sketch:
        sketch_input.addSelection(active_sketch)

    inputs.addStringValueInput("csvPath", "CSV File", "")
    inputs.addBoolValueInput("browseCsv", "Browse...", False, "", False)

    default_units = app.activeProduct.unitsManager.defaultLengthUnits
    default_depth = adsk.core.ValueInput.createByString("1")
    inputs.addValueInput("profileDepth", "Profile Depth", default_units, default_depth)

    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(args.command.inputChanged, command_input_changed, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)


def command_execute(args: adsk.core.CommandEventArgs):
    futil.log(f'{CMD_NAME} Command Execute Event')

    inputs = args.command.commandInputs
    sketch_input = inputs.itemById("targetSketch")
    path_input = inputs.itemById("csvPath")

    if sketch_input.selectionCount < 1:
        ui.messageBox("Select a sketch or plane to receive the profile.")
        return

    file_path = path_input.value
    if not file_path or not os.path.isfile(file_path):
        ui.messageBox("Select a valid CSV file.")
        return

    points = _parse_profile_points(file_path)
    if len(points) < 2:
        ui.messageBox("No valid point pairs found in the CSV file.")
        return

    depth_input = inputs.itemById("profileDepth")
    target_depth = depth_input.value
    if target_depth <= 0:
        ui.messageBox("Profile depth must be greater than zero.")
        return

    xs = [x_val for x_val, _ in points]
    min_x = min(xs)
    max_x = max(xs)
    chord = max_x - min_x
    if chord <= 0:
        ui.messageBox("Invalid profile data: chord length is zero.")
        return

    scale = target_depth / chord
    points = [((x_val - min_x) * scale + min_x, y_val * scale) for x_val, y_val in points]

    selection_entity = sketch_input.selection(0).entity
    sketch = adsk.fusion.Sketch.cast(selection_entity)
    if not sketch:
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            ui.messageBox("No active design found.")
            return
        component = design.activeComponent
        sketch = component.sketches.add(selection_entity)

    lower_pts, upper_pts = _split_profile(points)
    if len(lower_pts) < 2 or len(upper_pts) < 2:
        ui.messageBox("Not enough points to build upper and lower curves.")
        return

    sketch_lines = sketch.sketchCurves.sketchLines
    _add_polyline(sketch_lines, lower_pts)
    _add_polyline(sketch_lines, upper_pts)

    if lower_pts[0].distanceTo(upper_pts[0]) > 1e-6:
        sketch_lines.addByTwoPoints(lower_pts[0], upper_pts[0])
    if lower_pts[-1].distanceTo(upper_pts[-1]) > 1e-6:
        sketch_lines.addByTwoPoints(lower_pts[-1], upper_pts[-1])


def command_input_changed(args: adsk.core.InputChangedEventArgs):
    changed_input = args.input
    if changed_input.id != "browseCsv":
        return

    file_dialog = ui.createFileDialog()
    file_dialog.title = "Select CSV airfoil profile"
    file_dialog.filter = "CSV Files (*.csv)"
    file_dialog.filterIndex = 0

    if file_dialog.showOpen() != adsk.core.DialogResults.DialogOK:
        return

    path_input = args.inputs.itemById("csvPath")
    if path_input:
        path_input.value = file_dialog.filename

    changed_input.value = False


def command_destroy(args: adsk.core.CommandEventArgs):
    futil.log(f'{CMD_NAME} Command Destroy Event')

    global local_handlers
    local_handlers = []
