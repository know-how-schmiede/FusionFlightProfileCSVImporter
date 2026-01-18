import adsk.core
import adsk.fusion
import math
import os
import re
import traceback
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
    points = []

    with open(file_path, "r", newline="") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            delimiter = ";" if ";" in line else ","
            if delimiter in line:
                parts = [part.strip() for part in line.split(delimiter) if part.strip()]
            else:
                parts = [part for part in re.split(r"\s+", line) if part]

            if len(parts) < 2:
                continue

            x_str = parts[0]
            y_str = parts[1]
            if delimiter == ";":
                x_str = x_str.replace(",", ".")
                y_str = y_str.replace(",", ".")

            try:
                x_val = float(x_str)
                y_val = float(y_str)
            except ValueError:
                continue

            points.append((x_val, y_val))

    return points


def _validate_profile_sequence(points):
    if len(points) < 3:
        return "Not enough points to validate profile order."

    x_vals = [x_val for x_val, _ in points]
    y_vals = [y_val for _, y_val in points]
    x_min = min(x_vals)
    x_max = max(x_vals)
    chord = x_max - x_min
    if chord <= 0:
        return "Invalid profile data: chord length is zero."

    max_abs_y = max(abs(y_val) for y_val in y_vals) if y_vals else 0.0
    x_tol = max(chord * 1e-6, 1e-9)
    y_tol = max(max_abs_y * 1e-4, chord * 1e-6, 1e-9)

    trailing_te = 0
    for x_val, y_val in reversed(points):
        if abs(x_val - x_max) <= x_tol and abs(y_val) <= y_tol:
            trailing_te += 1
        else:
            break
    if trailing_te > 1:
        return (
            "CSV ends with repeated trailing-edge points (x near max, y near 0). "
            "Remove duplicate rows to avoid zero-length errors."
        )

    first_x, first_y = points[0]
    if abs(first_x - x_max) > x_tol:
        return "Profile must start at the trailing edge (x near max)."
    if first_y < -y_tol:
        return "Profile must start on the upper surface (y >= 0)."

    last_x, last_y = points[-1]
    if abs(last_x - x_max) > x_tol:
        return "Profile must end at the trailing edge (x near max)."
    if last_y > y_tol:
        return "Profile must end on the lower surface (y <= 0)."

    signs = []
    for _, y_val in points:
        if y_val > y_tol:
            sign = 1
        elif y_val < -y_tol:
            sign = -1
        else:
            continue
        if not signs or sign != signs[-1]:
            signs.append(sign)

    if not signs:
        return "Profile points lie on the chord line; expected upper and lower surfaces."
    if signs[0] != 1:
        return "Profile must start on the upper surface with positive Y values."
    if len(signs) > 2 or (len(signs) == 2 and signs[1] != -1):
        return (
            "Profile points alternate between upper and lower surfaces. "
            "Expected all upper points first, then all lower points."
        )

    le_indices = [
        idx for idx, (x_val, _) in enumerate(points) if abs(x_val - x_min) <= x_tol
    ]
    if not le_indices:
        return "Leading edge (min X) not found in profile."
    if not any(abs(points[idx][1]) <= y_tol for idx in le_indices):
        return "Leading edge (min X) should be near y = 0."

    prev_x = points[0][0]
    for idx in range(1, le_indices[0] + 1):
        x_val = points[idx][0]
        if x_val > prev_x + x_tol:
            return "Upper surface must move toward the leading edge (x decreasing)."
        prev_x = x_val

    prev_x = points[le_indices[-1]][0]
    for idx in range(le_indices[-1] + 1, len(points)):
        x_val = points[idx][0]
        if x_val < prev_x - x_tol:
            return "Lower surface must move toward the trailing edge (x increasing)."
        prev_x = x_val

    for idx in range(0, le_indices[0] + 1):
        if points[idx][1] < -y_tol:
            return (
                "Upper surface contains negative Y values. "
                "Expected positive Y values up to the leading edge."
            )
    for idx in range(le_indices[-1], len(points)):
        if points[idx][1] > y_tol:
            return (
                "Lower surface contains positive Y values. "
                "Expected negative Y values after the leading edge."
            )

    return None


def _format_profile_error(message, label):
    if not label:
        return message
    return f"{label}: {message}"


def _load_profile_points(file_path, label=None):
    points = _parse_profile_points(file_path)
    if len(points) < 2:
        return None, _format_profile_error(
            "No valid point pairs found in the CSV file.", label
        )

    error = _validate_profile_sequence(points)
    if error:
        return None, _format_profile_error(error, label)

    return points, None


def _scale_points(points, target_depth):
    xs = [x_val for x_val, _ in points]
    min_x = min(xs)
    max_x = max(xs)
    chord = max_x - min_x
    if chord <= 0:
        raise ValueError("Invalid profile data: chord length is zero.")

    scale = target_depth / chord
    return [((x_val - min_x) * scale + min_x, y_val * scale) for x_val, y_val in points]


def _profile_name_from_path(file_path):
    base_name = os.path.basename(file_path)
    name, _ = os.path.splitext(base_name)
    return name or "Profile"


def _compute_leading_edge(points, x_tol=1e-6):
    min_x = min(point[0] for point in points)
    near_le = [point[1] for point in points if abs(point[0] - min_x) <= x_tol]
    if not near_le:
        return min_x, 0.0
    avg_y = sum(near_le) / len(near_le)
    return min_x, avg_y


def _rotate_points(points, angle_rad, pivot):
    if abs(angle_rad) < 1e-12:
        return points

    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    px, py = pivot
    rotated = []
    for x_val, y_val in points:
        dx = x_val - px
        dy = y_val - py
        rx = px + dx * cos_a - dy * sin_a
        ry = py + dx * sin_a + dy * cos_a
        rotated.append((rx, ry))
    return rotated

def _group_by_x(points):
    sorted_points = sorted(points, key=lambda p: p[0])
    if len(sorted_points) < 3:
        return None

    dxs = [
        sorted_points[idx + 1][0] - sorted_points[idx][0]
        for idx in range(len(sorted_points) - 1)
    ]
    dxs = [dx for dx in dxs if dx > 0]
    if len(dxs) < 2:
        return None

    dxs_sorted = sorted(dxs)
    small_idx = max(0, int(len(dxs_sorted) * 0.2) - 1)
    small_dx = dxs_sorted[small_idx]
    median_dx = dxs_sorted[len(dxs_sorted) // 2]
    if median_dx <= 0 or small_dx > median_dx * 0.25:
        return None

    tol = small_dx * 1.5 if small_dx > 0 else median_dx * 0.1
    groups = []
    current = [sorted_points[0]]

    for point in sorted_points[1:]:
        if abs(point[0] - current[-1][0]) <= tol:
            current.append(point)
        else:
            groups.append(current)
            current = [point]

    groups.append(current)

    paired_groups = [group for group in groups if len(group) >= 2]
    if len(paired_groups) < 2:
        return None

    lower_pts = []
    upper_pts = []
    for group in groups:
        low_pt = min(group, key=lambda p: p[1])
        up_pt = max(group, key=lambda p: p[1])
        lower_pts.append((low_pt[0], low_pt[1]))
        upper_pts.append((up_pt[0], up_pt[1]))

    return lower_pts, upper_pts


def _split_profile(points):
    grouped = _group_by_x(points)
    if grouped:
        return grouped

    sorted_points = sorted(points, key=lambda p: p[0])
    groups = []
    current = [sorted_points[0]]

    for x_val, y_val in sorted_points[1:]:
        if abs(x_val - current[-1][0]) <= 1e-6:
            current.append((x_val, y_val))
        else:
            groups.append(current)
            current = [(x_val, y_val)]

    groups.append(current)

    paired_count = sum(1 for group in groups if len(group) >= 2)
    if paired_count >= max(3, len(groups) // 4):
        lower_pts = []
        upper_pts = []
        for group in groups:
            ys = [point[1] for point in group]
            x_val = group[0][0]
            lower_pts.append((x_val, min(ys)))
            upper_pts.append((x_val, max(ys)))
        return lower_pts, upper_pts

    min_idx = min(range(len(points)), key=lambda idx: points[idx][0])
    upper_pts = points[:min_idx + 1]
    lower_pts = points[min_idx:]
    upper_pts = sorted(upper_pts, key=lambda p: p[0])
    lower_pts = sorted(lower_pts, key=lambda p: p[0])
    return lower_pts, upper_pts


def _add_spline(sketch_curves, points):
    obj_collection = adsk.core.ObjectCollection.create()
    for point in points:
        obj_collection.add(point)
    sketch_curves.sketchFittedSplines.add(obj_collection)


def _resolve_plane(selection_entity):
    sketch = adsk.fusion.Sketch.cast(selection_entity)
    if sketch:
        plane = None
        try:
            plane = sketch.referencePlane
        except AttributeError:
            plane = None
        if not plane:
            try:
                plane = sketch.planarEntity
            except AttributeError:
                plane = None
        if plane:
            return plane
    return selection_entity


def _create_offset_plane(component, base_plane, offset_value):
    planes = component.constructionPlanes
    plane_input = planes.createInput()
    plane_input.setByOffset(base_plane, adsk.core.ValueInput.createByReal(offset_value))
    return planes.add(plane_input)


def _draw_profile(sketch, points, rotation_rad=0.0, pivot=None):
    lower_pts, upper_pts = _split_profile(points)
    if len(lower_pts) < 2 or len(upper_pts) < 2:
        raise ValueError("Not enough points to build upper and lower curves.")

    if pivot is not None and abs(rotation_rad) > 1e-12:
        lower_pts = _rotate_points(lower_pts, rotation_rad, pivot)
        upper_pts = _rotate_points(upper_pts, rotation_rad, pivot)

    lower_3d = [adsk.core.Point3D.create(x_val, y_val, 0) for x_val, y_val in lower_pts]
    upper_3d = [adsk.core.Point3D.create(x_val, y_val, 0) for x_val, y_val in upper_pts]

    sketch_curves = sketch.sketchCurves
    sketch_lines = sketch_curves.sketchLines
    _add_spline(sketch_curves, lower_3d)
    _add_spline(sketch_curves, upper_3d)

    lower_le = min(lower_pts, key=lambda p: p[0])
    upper_le = min(upper_pts, key=lambda p: p[0])
    lower_te = max(lower_pts, key=lambda p: p[0])
    upper_te = max(upper_pts, key=lambda p: p[0])

    le_lower_pt = adsk.core.Point3D.create(lower_le[0], lower_le[1], 0)
    le_upper_pt = adsk.core.Point3D.create(upper_le[0], upper_le[1], 0)
    te_lower_pt = adsk.core.Point3D.create(lower_te[0], lower_te[1], 0)
    te_upper_pt = adsk.core.Point3D.create(upper_te[0], upper_te[1], 0)

    if le_lower_pt.distanceTo(le_upper_pt) > 1e-6:
        sketch_lines.addByTwoPoints(le_lower_pt, le_upper_pt)
    if te_lower_pt.distanceTo(te_upper_pt) > 1e-6:
        sketch_lines.addByTwoPoints(te_lower_pt, te_upper_pt)


def _get_primary_profile(sketch):
    if sketch.profiles.count == 0:
        return None

    primary = None
    max_area = -1.0
    for profile in sketch.profiles:
        try:
            area = abs(
                profile.areaProperties(
                    adsk.fusion.CalculationAccuracy.MediumCalculationAccuracy
                ).area
            )
        except Exception:
            area = 0.0
        if area > max_area:
            max_area = area
            primary = profile

    return primary


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

    try:
        inputs = args.command.commandInputs

        sketch_input = inputs.addSelectionInput(
            "targetSketch",
            "Target Sketch or Plane",
            "Select a sketch, construction plane, or planar face for the first profile.",
        )
        sketch_input.addSelectionFilter("Sketches")
        sketch_input.addSelectionFilter("ConstructionPlanes")
        sketch_input.addSelectionFilter("PlanarFaces")
        sketch_input.setSelectionLimits(1, 1)

        active_sketch = adsk.fusion.Sketch.cast(app.activeEditObject)
        if active_sketch:
            sketch_input.addSelection(active_sketch)

        units_manager = app.activeProduct.unitsManager if app.activeProduct else None
        default_units = units_manager.defaultLengthUnits if units_manager else "cm"
        default_angle_units = (
            getattr(units_manager, "defaultAngleUnits", "deg") if units_manager else "deg"
        )
        default_depth = adsk.core.ValueInput.createByString("1")
        default_offset = adsk.core.ValueInput.createByString("0")
        default_angle = adsk.core.ValueInput.createByString("0")

        profile1_group = inputs.addGroupCommandInput("profile1Group", "Profile 1")
        profile1_group.isExpanded = True
        profile1_inputs = profile1_group.children
        profile1_inputs.addBoolValueInput("browseCsv", "Browse...", False, "", False)
        profile1_inputs.addStringValueInput("csvPath", "CSV File", "")
        profile1_inputs.addValueInput("profileDepth", "Profile Depth", default_units, default_depth)
        profile1_inputs.addBoolValueInput("mirrorProfile", "Mirror", True, "", False)

        profile2_group = inputs.addGroupCommandInput("profile2Group", "Profile 2")
        profile2_group.isExpanded = True
        profile2_inputs = profile2_group.children
        profile2_inputs.addBoolValueInput("browseCsv2", "Browse...", False, "", False)
        profile2_inputs.addStringValueInput("csvPath2", "CSV File", "")
        profile2_inputs.addValueInput("profileDepth2", "Profile Depth", default_units, default_depth)
        profile2_inputs.addBoolValueInput("mirrorProfile2", "Mirror", True, "", False)
        profile2_inputs.addValueInput("profileOffset", "Second Profile Offset", default_units, default_offset)
        profile2_inputs.addValueInput("profileAngle2", "Profile 2 Rotation", default_angle_units, default_angle)
        profile2_inputs.addBoolValueInput("createSolid", "Create Solid (Loft)", True, "", False)

        futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
        futil.add_handler(args.command.inputChanged, command_input_changed, local_handlers=local_handlers)
        futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)
    except Exception:
        ui.messageBox("Command creation failed:\n{}".format(traceback.format_exc()))


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
        ui.messageBox("Select a valid CSV file for profile 1.")
        return

    depth_input = inputs.itemById("profileDepth")
    target_depth = depth_input.value
    if target_depth <= 0:
        ui.messageBox("Profile depth (profile 1) must be greater than zero.")
        return

    depth_input2 = inputs.itemById("profileDepth2")
    target_depth2 = depth_input2.value
    if target_depth2 <= 0:
        ui.messageBox("Profile depth (profile 2) must be greater than zero.")
        return

    offset_input = inputs.itemById("profileOffset")
    offset_value = offset_input.value

    mirror_input = inputs.itemById("mirrorProfile")
    mirror_profile = mirror_input.value
    mirror_input2 = inputs.itemById("mirrorProfile2")
    mirror_profile2 = mirror_input2.value
    angle_input2 = inputs.itemById("profileAngle2")
    angle_value2 = angle_input2.value
    create_solid_input = inputs.itemById("createSolid")
    create_solid = create_solid_input.value

    path_input2 = inputs.itemById("csvPath2")
    file_path2 = path_input2.value.strip()
    has_second = bool(file_path2)
    if has_second and not os.path.isfile(file_path2):
        ui.messageBox("Select a valid CSV file for profile 2.")
        return
    if not has_second and abs(offset_value) > 1e-9:
        ui.messageBox("Second profile CSV is required when a non-zero offset is specified.")
        return

    points, error = _load_profile_points(file_path, "Profile 1")
    if error:
        ui.messageBox(error)
        return
    try:
        points = _scale_points(points, target_depth)
    except ValueError as exc:
        ui.messageBox(str(exc))
        return
    if mirror_profile:
        points = [(x_val, -y_val) for x_val, y_val in points]
    lead_edge = _compute_leading_edge(points)

    points2 = None
    if has_second:
        points2, error = _load_profile_points(file_path2, "Profile 2")
        if error:
            ui.messageBox(error)
            return
        try:
            points2 = _scale_points(points2, target_depth2)
        except ValueError as exc:
            ui.messageBox(str(exc))
            return
        if mirror_profile2:
            points2 = [(x_val, -y_val) for x_val, y_val in points2]

    selection_entity = sketch_input.selection(0).entity
    sketch = adsk.fusion.Sketch.cast(selection_entity)

    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        ui.messageBox("No active design found.")
        return
    component = design.activeComponent

    if not sketch:
        sketch = component.sketches.add(selection_entity)

    sketch.name = _profile_name_from_path(file_path)

    try:
        _draw_profile(sketch, points)
    except ValueError as exc:
        ui.messageBox(str(exc))
        return

    if has_second:
        base_plane = _resolve_plane(selection_entity)
        offset_plane = _create_offset_plane(component, base_plane, offset_value)
        sketch2 = component.sketches.add(offset_plane)
        sketch2.name = _profile_name_from_path(file_path2)
        try:
            _draw_profile(sketch2, points2, rotation_rad=-angle_value2, pivot=lead_edge)
        except ValueError as exc:
            ui.messageBox(str(exc))
            return

        if create_solid:
            profile1 = _get_primary_profile(sketch)
            profile2 = _get_primary_profile(sketch2)
            if not profile1 or not profile2:
                ui.messageBox("Unable to create loft: missing closed profile.")
                return

            loft_features = component.features.loftFeatures
            loft_input = loft_features.createInput(
                adsk.fusion.FeatureOperations.NewBodyFeatureOperation
            )
            loft_input.isSolid = True
            loft_input.loftSections.add(profile1)
            loft_input.loftSections.add(profile2)
            loft_features.add(loft_input)
            sketch.isVisible = False
            sketch2.isVisible = False


def command_input_changed(args: adsk.core.InputChangedEventArgs):
    changed_input = args.input
    if changed_input.id not in {"browseCsv", "browseCsv2"}:
        return

    file_dialog = ui.createFileDialog()
    file_dialog.title = "Select CSV airfoil profile"
    file_dialog.filter = "CSV Files (*.csv)"
    file_dialog.filterIndex = 0

    if file_dialog.showOpen() != adsk.core.DialogResults.DialogOK:
        return

    path_id = "csvPath" if changed_input.id == "browseCsv" else "csvPath2"
    path_input = args.inputs.itemById(path_id)
    if path_input:
        path_input.value = file_dialog.filename
        label = "Profile 1" if changed_input.id == "browseCsv" else "Profile 2"
        _, error = _load_profile_points(file_dialog.filename, label)
        if error:
            ui.messageBox(error)
            path_input.value = ""
            changed_input.value = False
            return

    changed_input.value = False


def command_destroy(args: adsk.core.CommandEventArgs):
    futil.log(f'{CMD_NAME} Command Destroy Event')

    global local_handlers
    local_handlers = []
