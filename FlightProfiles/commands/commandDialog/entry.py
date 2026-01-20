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
CMD_DESCRIPTION = f'Import an airfoil profile CSV onto a selected plane. (v{config.VERSION})'

IS_PROMOTED = True

WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_ID = 'SolidCreatePanel'

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')
LOGO_IMAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', 'logo.png')

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


def _profile_tolerances(points):
    x_vals = [x_val for x_val, _ in points]
    y_vals = [y_val for _, y_val in points]
    x_min = min(x_vals)
    x_max = max(x_vals)
    chord = x_max - x_min
    if chord <= 0:
        return None

    max_abs_y = max(abs(y_val) for y_val in y_vals) if y_vals else 0.0
    x_tol = max(chord * 1e-6, 1e-9)
    y_tol = max(max_abs_y * 1e-4, chord * 1e-6, 1e-9)
    return x_min, x_max, chord, x_tol, y_tol


def _trailing_edge_duplicate_count(points, x_max, x_tol, y_tol):
    count = 0
    for x_val, y_val in reversed(points):
        if abs(x_val - x_max) <= x_tol and abs(y_val) <= y_tol:
            count += 1
        else:
            break
    return count


def _is_interleaved_profile(points, y_tol):
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
    return len(signs) > 2


def _median_dx(points):
    if len(points) < 3:
        return 0.0
    dxs = [
        points[idx + 1][0] - points[idx][0] for idx in range(len(points) - 1)
    ]
    dxs = [dx for dx in dxs if dx > 0]
    if not dxs:
        return 0.0
    dxs.sort()
    return dxs[len(dxs) // 2]


def _collapse_trailing_edge(points, x_max, window, pair_tol, keep_upper):
    if window <= 0 or pair_tol <= 0 or len(points) < 3:
        return points
    threshold = x_max - window
    collapsed = []
    for x_val, y_val in points:
        if x_val < threshold:
            collapsed.append((x_val, y_val))
            continue
        if collapsed and abs(x_val - collapsed[-1][0]) <= pair_tol:
            if keep_upper:
                if y_val > collapsed[-1][1]:
                    collapsed[-1] = (x_val, y_val)
            else:
                if y_val < collapsed[-1][1]:
                    collapsed[-1] = (x_val, y_val)
        else:
            collapsed.append((x_val, y_val))
    return collapsed


def _cleanup_trailing_edge(points, x_tol, y_tol):
    if len(points) < 6:
        return points, False

    min_idx = min(range(len(points)), key=lambda idx: points[idx][0])
    if min_idx == 0 or min_idx == len(points) - 1:
        return points, False

    upper = points[:min_idx + 1]
    lower = points[min_idx:]
    lower_sorted = sorted(lower, key=lambda p: p[0])

    x_vals = [x_val for x_val, _ in points]
    x_min = min(x_vals)
    x_max = max(x_vals)
    chord = x_max - x_min
    if chord <= 0:
        return points, False

    edge_window = chord * 0.02
    ys = [y_val for x_val, y_val in lower_sorted if x_val >= x_max - edge_window]
    if len(ys) < 4:
        return points, False

    signs = []
    for idx in range(1, len(ys)):
        dy = ys[idx] - ys[idx - 1]
        if abs(dy) <= y_tol:
            continue
        sign = 1 if dy > 0 else -1
        if not signs or sign != signs[-1]:
            signs.append(sign)

    if len(signs) < 2:
        return points, False

    median_dx = _median_dx(lower_sorted)
    pair_tol = max(x_tol, median_dx * 0.5) if median_dx > 0 else x_tol
    lower_clean = _collapse_trailing_edge(
        lower_sorted, x_max, edge_window, pair_tol, keep_upper=False
    )

    if lower_clean and upper and lower_clean[0] == upper[-1]:
        lower_clean = lower_clean[1:]

    return upper + lower_clean, True


def _alignment_angle_to_global_z(sketch):
    try:
        x_dir = sketch.xDirection
        y_dir = sketch.yDirection
    except AttributeError:
        return 0.0
    if x_dir.length == 0 or y_dir.length == 0:
        return 0.0
    x_dir.normalize()
    y_dir.normalize()

    normal = x_dir.crossProduct(y_dir)
    if normal.length == 0:
        return 0.0
    normal.normalize()

    global_z = adsk.core.Vector3D.create(0, 0, 1)
    dot = global_z.dotProduct(normal)
    proj = adsk.core.Vector3D.create(
        global_z.x - normal.x * dot,
        global_z.y - normal.y * dot,
        global_z.z - normal.z * dot,
    )
    if proj.length == 0:
        return 0.0
    proj.normalize()

    tx = proj.dotProduct(x_dir)
    ty = proj.dotProduct(y_dir)
    if abs(tx) < 1e-12 and abs(ty) < 1e-12:
        return 0.0

    return math.atan2(ty, tx) - (math.pi / 2.0)


def _rotate_point_2d(point, angle_rad):
    if abs(angle_rad) < 1e-12:
        return point
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    x_val, y_val = point
    return (x_val * cos_a - y_val * sin_a, x_val * sin_a + y_val * cos_a)


def _sort_interleaved_profile(points, x_tol, y_tol):
    if not points:
        return None

    x_vals = [x_val for x_val, _ in points]
    x_min = min(x_vals)
    x_max = max(x_vals)
    chord = x_max - x_min
    if chord <= 0:
        return None

    sorted_points = sorted(points, key=lambda p: p[0])
    groups = []
    current = [sorted_points[0]]

    for point in sorted_points[1:]:
        if abs(point[0] - current[-1][0]) <= x_tol:
            current.append(point)
        else:
            groups.append(current)
            current = [point]

    groups.append(current)

    upper_pts = []
    lower_pts = []
    for group in groups:
        x_val = sum(point[0] for point in group) / len(group)
        ys = [point[1] for point in group]
        max_y = max(ys)
        min_y = min(ys)
        has_pos = max_y > y_tol
        has_neg = min_y < -y_tol

        if has_pos and has_neg:
            upper_pts.append((x_val, max_y))
            lower_pts.append((x_val, min_y))
        elif has_pos:
            upper_pts.append((x_val, max_y))
        elif has_neg:
            lower_pts.append((x_val, min_y))
        else:
            upper_pts.append((x_val, max_y))
            lower_pts.append((x_val, min_y))

    upper_sorted = sorted(upper_pts, key=lambda p: p[0], reverse=True)
    lower_sorted = sorted(lower_pts, key=lambda p: p[0])

    edge_window = chord * 0.02
    upper_dx = _median_dx(sorted(upper_sorted, key=lambda p: p[0]))
    lower_dx = _median_dx(lower_sorted)
    upper_tol = max(x_tol, upper_dx * 0.5) if upper_dx > 0 else x_tol
    lower_tol = max(x_tol, lower_dx * 0.5) if lower_dx > 0 else x_tol
    upper_sorted = _collapse_trailing_edge(
        upper_sorted, x_max, edge_window, upper_tol, keep_upper=True
    )
    lower_sorted = _collapse_trailing_edge(
        lower_sorted, x_max, edge_window, lower_tol, keep_upper=False
    )

    if upper_sorted and lower_sorted:
        upper_le = upper_sorted[-1]
        lower_le = lower_sorted[0]
        if (
            abs(upper_le[0] - lower_le[0]) <= x_tol
            and abs(upper_le[1] - lower_le[1]) <= y_tol
        ):
            lower_sorted = lower_sorted[1:]

    return upper_sorted + lower_sorted


def _detect_profile_format(file_path):
    delimiter = ","
    decimal_sep = "."
    include_z = False
    with open(file_path, "r", newline="") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if ";" in line:
                delimiter = ";"
                decimal_sep = ","
            elif "," in line:
                delimiter = ","
                decimal_sep = "."
            else:
                delimiter = ","
                decimal_sep = "."
            parts = [part.strip() for part in line.split(delimiter) if part.strip()]
            include_z = len(parts) >= 3
            break
    return delimiter, decimal_sep, include_z


def _write_sorted_profile_file(file_path, points):
    directory = os.path.dirname(file_path)
    base_name = os.path.basename(file_path)
    name, ext = os.path.splitext(base_name)
    if name.endswith("_sort"):
        new_name = name
    else:
        new_name = f"{name}_sort"
    new_path = os.path.join(directory, f"{new_name}{ext}")

    delimiter, decimal_sep, include_z = _detect_profile_format(file_path)
    fmt = "{:.8f}"

    def format_value(value):
        text = fmt.format(value)
        if decimal_sep != ".":
            text = text.replace(".", decimal_sep)
        return text

    lines = []
    for x_val, y_val in points:
        x_text = format_value(x_val)
        y_text = format_value(y_val)
        if include_z:
            z_text = format_value(0.0)
            lines.append(f"{x_text}{delimiter}{y_text}{delimiter}{z_text}")
        else:
            lines.append(f"{x_text}{delimiter}{y_text}")

    with open(new_path, "w", newline="") as handle:
        handle.write("\n".join(lines))
        handle.write("\n")

    return new_path


def _validate_profile_sequence(points):
    if len(points) < 3:
        return "Not enough points to validate profile order."

    tolerances = _profile_tolerances(points)
    if not tolerances:
        return "Invalid profile data: chord length is zero."
    x_min, x_max, chord, x_tol, y_tol = tolerances

    trailing_te = _trailing_edge_duplicate_count(points, x_max, x_tol, y_tol)
    if trailing_te > 1:
        return (
            "CSV ends with repeated trailing-edge points (x near max, y near 0). "
            "Remove duplicate rows to avoid zero-length errors."
        )

    te_tol = max(x_tol, chord * 0.02)
    upper_candidates = [x_val for x_val, y_val in points if y_val >= -y_tol]
    lower_candidates = [x_val for x_val, y_val in points if y_val <= y_tol]
    x_max_upper = max(upper_candidates) if upper_candidates else x_max
    x_max_lower = max(lower_candidates) if lower_candidates else x_max

    first_x, first_y = points[0]
    if abs(first_x - x_max_upper) > te_tol:
        return "Profile must start at the trailing edge (x near max)."
    if first_y < -y_tol:
        return "Profile must start on the upper surface (y >= 0)."

    last_x, last_y = points[-1]
    if abs(last_x - x_max_lower) > te_tol:
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
        ), file_path, None

    tolerances = _profile_tolerances(points)
    if not tolerances:
        return None, _format_profile_error(
            "Invalid profile data: chord length is zero.", label
        ), file_path, None
    _, x_max, _, x_tol, y_tol = tolerances

    corrections = []
    trailing_te = _trailing_edge_duplicate_count(points, x_max, x_tol, y_tol)
    if trailing_te > 1:
        points = points[: -(trailing_te - 1)]
        corrections.append("Removed repeated trailing-edge rows.")

    if _is_interleaved_profile(points, y_tol):
        sorted_points = _sort_interleaved_profile(points, x_tol, y_tol)
        if not sorted_points:
            return None, _format_profile_error(
                "Unable to sort interleaved profile points.", label
            ), file_path, None
        points = sorted_points
        corrections.append("Interleaved points were sorted.")

    points, te_fixed = _cleanup_trailing_edge(points, x_tol, y_tol)
    if te_fixed:
        corrections.append("Collapsed trailing-edge oscillations.")

    error = _validate_profile_sequence(points)
    if error:
        return None, _format_profile_error(error, label), file_path, None

    if corrections:
        try:
            new_path = _write_sorted_profile_file(file_path, points)
        except OSError as exc:
            return None, _format_profile_error(
                f"Unable to write corrected CSV file: {exc}", label
            ), file_path, None
        return points, None, new_path, " ".join(corrections)

    return points, None, file_path, None


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


def _draw_profile(sketch, points, rotation_rad=0.0, pivot=None, align_angle=0.0):
    lower_pts, upper_pts = _split_profile(points)
    if len(lower_pts) < 2 or len(upper_pts) < 2:
        raise ValueError("Not enough points to build upper and lower curves.")

    if abs(align_angle) > 1e-12:
        lower_pts = _rotate_points(lower_pts, align_angle, (0.0, 0.0))
        upper_pts = _rotate_points(upper_pts, align_angle, (0.0, 0.0))

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

        if os.path.isfile(LOGO_IMAGE):
            try:
                logo_input = inputs.addImageCommandInput("logoImage", "", LOGO_IMAGE)
                if hasattr(logo_input, "isFullWidth"):
                    logo_input.isFullWidth = True
            except AttributeError:
                file_url = LOGO_IMAGE.replace("\\", "/")
                if not file_url.lower().startswith("file:///"):
                    file_url = f"file:///{file_url}"
                html = (
                    f'<img src="{file_url}" alt="Logo" '
                    'style="max-width:100%; height:auto;" />'
                )
                inputs.addTextBoxCommandInput("logoImage", "", html, 3, True)

        plane_input = inputs.addSelectionInput(
            "targetPlane",
            "Target Plane",
            "Select a construction plane or planar face for the first profile.",
        )
        plane_input.addSelectionFilter("ConstructionPlanes")
        plane_input.addSelectionFilter("PlanarFaces")
        plane_input.setSelectionLimits(1, 1)

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
    plane_input = inputs.itemById("targetPlane")
    path_input = inputs.itemById("csvPath")

    if plane_input.selectionCount < 1:
        ui.messageBox("Select a construction plane or planar face to receive the profile.")
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

    points, error, effective_path, correction_note = _load_profile_points(
        file_path, "Profile 1"
    )
    if error:
        ui.messageBox(error)
        return
    if correction_note:
        file_path = effective_path
        path_input.value = effective_path
        ui.messageBox(f"Profile 1: {correction_note}\nSaved to:\n{effective_path}")
    try:
        points = _scale_points(points, target_depth)
    except ValueError as exc:
        ui.messageBox(str(exc))
        return
    if mirror_profile:
        points = [(x_val, -y_val) for x_val, y_val in points]
    lead_edge = None

    points2 = None
    if has_second:
        points2, error, effective_path2, correction_note2 = _load_profile_points(
            file_path2, "Profile 2"
        )
        if error:
            ui.messageBox(error)
            return
        if correction_note2:
            file_path2 = effective_path2
            path_input2.value = effective_path2
            ui.messageBox(
                f"Profile 2: {correction_note2}\nSaved to:\n{effective_path2}"
            )
        try:
            points2 = _scale_points(points2, target_depth2)
        except ValueError as exc:
            ui.messageBox(str(exc))
            return
        if mirror_profile2:
            points2 = [(x_val, -y_val) for x_val, y_val in points2]

    selection_entity = plane_input.selection(0).entity
    if not adsk.fusion.ConstructionPlane.cast(selection_entity) and not adsk.fusion.BRepFace.cast(
        selection_entity
    ):
        ui.messageBox("Select a construction plane or planar face to receive the profile.")
        return

    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        ui.messageBox("No active design found.")
        return
    component = design.activeComponent

    sketch = component.sketches.add(selection_entity)
    align_angle = _alignment_angle_to_global_z(sketch)
    lead_edge = _compute_leading_edge(points)

    sketch.name = _profile_name_from_path(file_path)

    try:
        _draw_profile(sketch, points, align_angle=align_angle)
    except ValueError as exc:
        ui.messageBox(str(exc))
        return

    if has_second:
        base_plane = _resolve_plane(selection_entity)
        offset_plane = _create_offset_plane(component, base_plane, offset_value)
        sketch2 = component.sketches.add(offset_plane)
        sketch2.name = _profile_name_from_path(file_path2)
        align_angle2 = _alignment_angle_to_global_z(sketch2)
        pivot = _rotate_point_2d(lead_edge, align_angle2)
        try:
            _draw_profile(
                sketch2,
                points2,
                rotation_rad=-angle_value2,
                pivot=pivot,
                align_angle=align_angle2,
            )
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
        _, error, effective_path, correction_note = _load_profile_points(
            file_dialog.filename, label
        )
        if error:
            ui.messageBox(error)
            path_input.value = ""
            changed_input.value = False
            return
        path_input.value = effective_path
        if correction_note:
            ui.messageBox(f"{label}: {correction_note}\nSaved to:\n{effective_path}")

    changed_input.value = False


def command_destroy(args: adsk.core.CommandEventArgs):
    futil.log(f'{CMD_NAME} Command Destroy Event')

    global local_handlers
    local_handlers = []
