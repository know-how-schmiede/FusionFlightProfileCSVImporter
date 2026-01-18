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

## Twist (Washout)
If the outer wing profile has a different angle of attack than the inner one, you apply twist (washout). The angle is always measured between the two chord lines (leading edge to trailing edge).

Where to rotate:
- Leading edge (x=0): simplest; the leading edge stays straight, the trailing edge moves up for negative twist.
- Spar line (often 25% or 30% chord): keeps the spar straight and avoids torsion in the structure.
- Mid-chord: geometrically valid, but rarely used in practice because both edges curve.

Negative twist is common so the inner wing stalls first and the outer wing keeps aileron control longer.

## Sweep
Sweep is the angle the wing is swept back (or forward) relative to the transverse axis, usually measured along the leading edge or the 25% chord line.

Why sweep:
- At high speeds, sweep reduces the effective Mach number seen by the airfoil and delays drag rise.
- In subsonic model use, sweep is often chosen for CG placement, stability in flying wings, or aesthetics.

Pros/cons:
- Pros: higher cruise speed, delayed compressibility effects, slight yaw stability.
- Cons: worse low-speed handling, higher stall speed, outboard stall tendency (tip stall).

## Airfoil blending (Profilstrak)
A "profilstrak" is a smooth transition between two or more airfoils along the span (root to tip).

Why use it:
- Aerodynamics: distribute lift and delay stall at the tip.
- Structure: thicker root airfoil for spar strength, thinner tip for lower drag.

Types:
- Geometric: scale or twist the same airfoil family (taper, twist).
- Aerodynamic: change the airfoil shape (camber or thickness) along the span.

## Versioning
- Update `FlightProfiles/version.py` for the code version.
- Keep `FlightProfiles/FlightProfiles.manifest` and `version.md` in sync.
