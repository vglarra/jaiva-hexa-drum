# CLAUDE.md — Jaiva Hexa Drum

## What this project is

A parametric hexagonal drum pad modeled in Blender via a Python script. The output is two 3D-printable halves that clip together with dowel pins. Each tile has a circular recess for a piezo sensor and a wire passage to the back face.

## Files

| File | Purpose |
|---|---|
| `jaiva-hexa-drum-script.py` | Main Blender Python script — generates all geometry |
| `jaiva-drum-hexa-cut-e-dowels.blend` | Blender project file (open this, then run the script) |
| `jaiva-hexa-drumpad-2026-06-15_21-08.png` | Reference render from Blender |

## How to run

1. Open `jaiva-drum-hexa-cut-e-dowels.blend` in Blender (3.x+)
2. Go to the **Scripting** workspace
3. Open `jaiva-hexa-drum-script.py`
4. Click **Run Script**

The script clears previous geometry, rebuilds everything, and exports STL/OBJ files next to the `.blend` file.

## Current version: V79

Script versioning is tracked in the header comment and `print()` statement at the top of the script. Bump the version number (`V53` → `V54` etc.) whenever a meaningful geometry change is made.

## Key parameters (all in mm)

```
SENSOR_DIA      = 69.0     # piezo sensor cup diameter
PLATE_H         = 6.0      # tile thickness
CUP_DEPTH       = 6.0      # depth of sensor recess
HEX_FLAT_WIDTH  = 77.0     # flat-to-flat hex width
DOME_HEIGHT     = 40.0     # dome peak height above flat base
DOME_RADIUS     = 210.0    # dome profile radius
PIN_DIAMETER    = 15.0     # dowel pin diameter
PIN_CLEARANCE   = 0.2      # clearance added to pin holes
PIN_Z           = 20.0     # height of pin hole center inside dome body
WIRE_HOLE_DIA   = 5.0      # wiring passage hole diameter
```

## Geometry overview

### Tile grid (16 tiles, flat-top hexagons)

```
Row y3 (top):  L00 L01 L02 L03          — 4 tiles
Row y2:        L02 L03  |  R00 R01 R02  — spans split (5 tiles)
Row y1:        L04 L05  |  R03 R04 R05  — spans split (6 tiles)
Row y0 (bot):  L06      |  R06 R07 R08  — spans split (4 tiles)
```

The vertical split is computed automatically as the largest gap between tile columns. The grid is divided into `left_grid` and `right_grid` lists at runtime.

### What is cut on each tile (per-tile, before joining)

1. **Hex prism** — flat-bottom hexagonal solid
2. **Dome displacement** — top vertices lifted by `dome_z(x, y) = DOME_HEIGHT * cos(π/2 * r / DOME_RADIUS)`
3. **Cup recess** — cylindrical recess (Ø69mm, 6mm deep) aligned to dome normal at tile center
4. **Wire hole** — 5mm vertical cylinder, center offset `CUP_R − WIRE_HOLE_RADIUS = 32mm` in the **−Y direction** from the cup center; outer edge is tangent to cup inner wall; pierces from z=−2 to dome top +2, giving a wiring passage to the flat back face
5. **Pin holes** (8 tiles only) — 15mm horizontal cylinders drilled through the side face at the split seam (see Pin holes section)

### Pin hole pairs (dowel alignment across the split)

| Pair | Left tile | Face | Right tile | Face |
|---|---|---|---|---|
| Pair 1 | L01 | right (+X) | R00 | left (−X) |
| Pair 2 | L03 | right (+X) | R02 | left (−X) |
| Pair 3 | L05 | right (+X) | R05 | left (−X) |
| Pair 4 | L06 | right (+X) | R07 | left (−X) |

`PIN_Z = 20mm` — verified to sit inside the dome body for all assigned tiles.

### Output meshes

After all tiles are built and cut, each half is joined into a single mesh:
- `SensorBase_L` — left half
- `SensorBase_R` — right half

Exported as `hex_dome_v53_L.stl` / `hex_dome_v53_R.stl` (and `.obj` fallback).

## Script structure

```
Parameters
Dome functions: dome_z(), dome_normal()
Grid layout + split computation
PIN_ASSIGNMENTS dict
Cleanup (removes Hex_, Cut_, Wire_, Hole_, SensorBase, TileNum_ objects)
Builders:
  make_hex_prism()
  make_cup_cutter()       — tilted cylinder aligned to dome normal
  make_hole_cutter()      — horizontal cylinder for dowel pins
  make_wire_hole_cutter() — vertical cylinder for sensor wiring
  apply_transforms()
  do_diff()               — boolean DIFFERENCE via FLOAT solver
  build_tile()            — orchestrates steps 1–4 per tile
  join_and_clean()
  add_tile_label()
Build loop (left tiles, then right tiles)
Join → SensorBase_L / SensorBase_R
Finalise (normals)
Export STL/OBJ
```

## Design decisions to remember

- **Per-tile booleans before joining**: guarantees cutters always intersect solid material. Do not move booleans to post-join.
- **FLOAT solver** for all booleans: more robust than EXACT for this geometry.
- **Wire hole direction is −Y** for all tiles: consistent, keeps the hole away from the split seam where pin holes live.
- **Wire hole tangency**: hole center at `CUP_R − WIRE_HOLE_RADIUS = 32mm` from cup center so the hole edge just touches the cup inner wall — maximises wall clearance while keeping the hole fully inside the cup footprint.
- **Dome normal alignment on cups**: the cup cutter is rotated to match `dome_normal(cx, cy)` so the recess is perpendicular to the playing surface, not to the Z axis.
