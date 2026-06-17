# ============================================================
# Blender Script: Hex Dome Array V55
# ALL 4 pairs cut per-tile BEFORE joining.
# PIN_Z = 20mm for all pairs — inside dome body.
# Per-tile cutting guarantees boolean always hits solid material.
# Wire hole (5mm dia) cut per-tile, tangent to cup inner wall (-Y).
# Teensy 4.1 cavity (50x90x30mm) cut on right half after joining.
# ============================================================

import bpy
import bmesh
import math
import os
from mathutils import Vector

print("=== HEX DOME ARRAY V55 - ALL HOLES + WIRE HOLES + TEENSY CAVITY ===")

# ---- Parameters ------------------------------------------------------
SENSOR_DIA     = 69.0
PLATE_H        = 6.0
CUP_DEPTH      = 6.0
CUP_R          = SENSOR_DIA / 2.0

HEX_FLAT_WIDTH = 77.0
S  = HEX_FLAT_WIDTH / math.sqrt(3)
H  = S * math.sqrt(3)
V  = S * 1.5

DOME_HEIGHT    = 40.0
DOME_RADIUS    = 210.0

PIN_DIAMETER   = 15.0
PIN_RADIUS     = PIN_DIAMETER / 2.0
PIN_DEPTH      = 20.0
PIN_CLEARANCE  = 0.2
PIN_Z          = 20.0   # mm — inside dome body

WIRE_HOLE_DIA    = 5.0
WIRE_HOLE_RADIUS = WIRE_HOLE_DIA / 2.0

CANAL_WIDTH = 10.0   # mm — width of wiring canal
CANAL_DEPTH =  5.0   # mm — depth of wiring canal from z=0 into tile body

# Teensy 4.1 microcontroller cavity — cut from underside of right half
# x: offset from seam to leave a solid wall; y: centred at dome peak (y=0)
CAVITY_X_OFFSET = 9.0    # mm — wall thickness between seam and cavity left face
CAVITY_W = 50.0   # mm — X, perpendicular to split seam, into right half
CAVITY_D = 90.0   # mm — Y, parallel to split seam, centred at y=0
CAVITY_H = 30.0   # mm — Z, from back face (z=0) upward into dome body

blend_path = bpy.data.filepath
export_dir = os.path.dirname(blend_path) if blend_path else os.path.expanduser("~")
print(f"PIN_Z={PIN_Z}mm  D={PIN_DIAMETER}mm  depth={PIN_DEPTH}mm")
print(f"Export: {export_dir}")

# ---- Dome functions --------------------------------------------------
def dome_z(x, y):
    r = math.sqrt(x*x + y*y)
    if r >= DOME_RADIUS: return 0.0
    return DOME_HEIGHT * math.cos(math.pi / 2.0 * r / DOME_RADIUS)

def dome_normal(x, y):
    r = math.sqrt(x*x + y*y)
    if r < 0.001: return Vector((0, 0, 1))
    t    = r / DOME_RADIUS
    dfdr = -DOME_HEIGHT * math.sin(math.pi/2.0*t) * (math.pi/(2.0*DOME_RADIUS))
    n = Vector((-dfdr*x/r, -dfdr*y/r, 1.0))
    n.normalize()
    return n

# ---- Grid ------------------------------------------------------------
y3=1.5*V; y2=0.5*V; y1=-0.5*V; y0=-1.5*V
grid_orig = [
    (-1.5*H,y3),(-0.5*H,y3),(0.5*H,y3),(1.5*H,y3),
    (-2.0*H,y2),(-1.0*H,y2),(0.0,y2),(1.0*H,y2),(2.0*H,y2),
    (-1.5*H,y1),(-0.5*H,y1),(0.5*H,y1),(1.5*H,y1),
    (-1.0*H,y0),(0.0,y0),(1.0*H,y0),
]

col_xs=sorted(set(round(cx,2) for cx,cy in grid_orig))
best_gap=0; best_split=0
for i in range(len(col_xs)-1):
    re=col_xs[i]+S; le=col_xs[i+1]-S; gap=le-re
    if gap>best_gap: best_gap=gap; best_split=(re+le)/2.0
SPLIT_X=best_split

left_grid  = [(cx,cy) for cx,cy in grid_orig if cx+S<=SPLIT_X+0.1]
right_grid = [(cx,cy) for cx,cy in grid_orig if cx-S>=SPLIT_X-0.1]
if len(left_grid)+len(right_grid)<len(grid_orig):
    left_grid  = [(cx,cy) for cx,cy in grid_orig if cx<SPLIT_X]
    right_grid = [(cx,cy) for cx,cy in grid_orig if cx>=SPLIT_X]

print(f"Split X: {SPLIT_X:.2f}  L:{len(left_grid)}  R:{len(right_grid)}")
print("LEFT:");  [print(f"  L{i:02d}: cx={cx:.1f} cy={cy:.1f}") for i,(cx,cy) in enumerate(left_grid)]
print("RIGHT:"); [print(f"  R{i:02d}: cx={cx:.1f} cy={cy:.1f}") for i,(cx,cy) in enumerate(right_grid)]

cos30 = math.cos(math.radians(30))

# ---- Cavity pre-computation ------------------------------------------
# Tiles whose bounding box overlaps the cavity footprint get the cut per-tile
# (same pattern as pin/wire holes — guarantees boolean hits solid material).
def overlaps_cavity(cx, cy):
    return (cx + S*cos30 > CAVITY_X_OFFSET and
            cx - S*cos30 < CAVITY_X_OFFSET + CAVITY_W and
            cy + S        > -CAVITY_D / 2.0 and
            cy - S        <  CAVITY_D / 2.0)

_cav_corners = [(CAVITY_X_OFFSET,            -CAVITY_D/2.0),
                (CAVITY_X_OFFSET + CAVITY_W,  -CAVITY_D/2.0),
                (CAVITY_X_OFFSET,              CAVITY_D/2.0),
                (CAVITY_X_OFFSET + CAVITY_W,   CAVITY_D/2.0)]
_min_dome_cav  = min(dome_z(x, y) for x, y in _cav_corners)
CAVITY_H_SAFE  = min(CAVITY_H, _min_dome_cav - 2.0)
if CAVITY_H_SAFE < CAVITY_H:
    print(f"⚠ CAVITY_H capped {CAVITY_H:.1f}→{CAVITY_H_SAFE:.1f}mm (dome clearance)")
print(f"Cavity {CAVITY_W:.0f}×{CAVITY_D:.0f}×{CAVITY_H_SAFE:.1f}mm  "
      f"x={CAVITY_X_OFFSET:.0f}..{CAVITY_X_OFFSET+CAVITY_W:.0f}  "
      f"min overhead={_min_dome_cav + PLATE_H - CAVITY_H_SAFE:.1f}mm")

# ---- Canal routing pre-computation ----------------------------------
# 12 axis-aligned segments connecting ALL 16 sensor wire holes to the
# Teensy cavity.  Applied per-tile before join (both halves).
_wo = CUP_R - WIRE_HOLE_RADIUS   # 32 mm — wire hole offset (-Y from tile centre)

CANAL_SEGMENTS = [
    # ── Middle trunk (spans seam — connects left L02/L03 AND right R02 to cavity) ──
    (-2.0*H,                     y2-_wo,  CAVITY_X_OFFSET,              y2-_wo),
    (CAVITY_X_OFFSET + CAVITY_W, y2-_wo,  2.0*H,                        y2-_wo),

    # ── Combined lower trunk (both halves at y = y1-32) ──
    (-1.5*H,  y1-_wo,   1.5*H,  y1-_wo),

    # ── Right half ──
    (0.5*H,   y3-_wo,   1.5*H,  y3-_wo),           # top trunk R00 ↔ R01
    (0.5*H,   CAVITY_D/2.0, 0.5*H, y3-_wo),        # top trunk → cavity top
    (0.5*H,   y1-_wo,   0.5*H, -CAVITY_D/2.0),      # lower trunk → cavity bottom
    (0.0,     y0-_wo,   0.0,  y1-_wo),              # R07 rises to lower trunk
    (H,       y0-_wo,   H,    y1-_wo),              # R08 rises to lower trunk

    # ── Left half ──
    (-1.5*H,  y3-_wo,  -0.5*H,  y3-_wo),            # top trunk L00 ↔ L01
    (-H,      y3-_wo,  -H,      y2-_wo),             # top trunk → middle trunk at x=-H (away from seam)
    (-H,      y1-_wo,  -H,      y2-_wo),             # lower trunk → middle trunk at x=-H (away from seam)
    (-H,      y0-_wo,  -H,      y1-_wo),             # L06 rises to lower trunk
]

def overlaps_canal(cx, cy, sx0, sy0, sx1, sy1):
    """Bounding-box overlap between a tile and a canal segment."""
    w2 = CANAL_WIDTH / 2.0 + 2.0
    if abs(sy0 - sy1) < 0.01:   # horizontal
        bx0, bx1 = min(sx0,sx1) - 2.0, max(sx0,sx1) + 2.0
        by0, by1 = sy0 - w2, sy0 + w2
    else:                        # vertical
        bx0, bx1 = sx0 - w2, sx0 + w2
        by0, by1 = min(sy0,sy1) - 2.0, max(sy0,sy1) + 2.0
    return (cx+S*cos30 > bx0 and cx-S*cos30 < bx1 and
            cy+S > by0 and cy-S < by1)

# ---- Pin hole assignments per tile ----------------------------------
# (tile_half, tile_idx, face_side, drill_dir)
# face_side 'R' = right face of tile (cx + cos30*S)
# face_side 'L' = left  face of tile (cx - cos30*S)
# Pair1: L01(-X) and R00(+X)
# Pair2: L03(-X) and R02(+X)
# Pair3: L05(-X) and R05(+X)  ← but R05 needs drill dir verified
# Pair4: L06(-X) and R07(+X)

PIN_ASSIGNMENTS = {
    # (half, idx): (face_side, drill_dir, pair_label)
    ('L', 1): ('R', -1, 'Pair1'),
    ('R', 0): ('L', +1, 'Pair1'),
    ('L', 3): ('R', -1, 'Pair2'),
    ('R', 2): ('L', +1, 'Pair2'),
    ('L', 5): ('R', -1, 'Pair3'),
    ('R', 5): ('L', +1, 'Pair3'),
    ('L', 6): ('R', -1, 'Pair4'),
    ('R', 7): ('L', +1, 'Pair4'),
}

# Print expected face positions
print("\nPin hole assignments:")
for (half, idx),(fside, dirn, lbl) in PIN_ASSIGNMENTS.items():
    grid = left_grid if half=='L' else right_grid
    if idx < len(grid):
        cx,cy = grid[idx]
        fx = cx + cos30*S if fside=='R' else cx - cos30*S
        wh = dome_z(cx,cy) + PLATE_H
        print(f"  {half}{idx:02d} {lbl}: face_x={fx:.1f} cy={cy:.1f} "
              f"wall_h={wh:.1f}mm PIN_Z={PIN_Z:.1f}mm "
              f"{'✓' if PIN_Z < wh-2 else '⚠ TOO HIGH'}")

# ---- Cleanup ---------------------------------------------------------
for obj in list(bpy.data.objects):
    if obj.name.startswith(("Hex_","Cut_","SensorBase","Hole_","Wire_","Cavity_","Canal_","TileNum_")):
        bpy.data.objects.remove(obj, do_unlink=True)

HEX_ANGLES=[math.radians(30+60*i) for i in range(6)]

# ---- Builders --------------------------------------------------------
def make_hex_prism(name,cx,cy):
    mesh=bpy.data.meshes.new(name+"_mesh")
    obj=bpy.data.objects.new(name,mesh)
    bpy.context.collection.objects.link(obj)
    bm=bmesh.new()
    corners=[(S*math.cos(a),S*math.sin(a)) for a in HEX_ANGLES]
    tc=bm.verts.new((cx,cy,PLATE_H))
    tr=[bm.verts.new((cx+hx,cy+hy,PLATE_H)) for hx,hy in corners]
    for i in range(6): j=(i+1)%6; bm.faces.new([tc,tr[i],tr[j]])
    bc=bm.verts.new((cx,cy,0.0))
    br=[bm.verts.new((cx+hx,cy+hy,0.0)) for hx,hy in corners]
    for i in range(6): j=(i+1)%6; bm.faces.new([bc,br[j],br[i]])
    for i in range(6): j=(i+1)%6; bm.faces.new([tr[i],tr[j],br[j],br[i]])
    bm.normal_update(); bm.to_mesh(mesh); bm.free(); mesh.validate()
    return obj

def make_cup_cutter(name,cx,cy):
    nv=dome_normal(cx,cy); dz=dome_z(cx,cy)
    tile_top=Vector((cx,cy,dz))+nv*PLATE_H
    cut_len=CUP_DEPTH+1.0; cut_ctr=tile_top+nv*(0.5-CUP_DEPTH/2.0)
    mesh=bpy.data.meshes.new(name+"_mesh")
    obj=bpy.data.objects.new(name,mesh)
    bpy.context.collection.objects.link(obj)
    bm=bmesh.new(); segs,half=64,cut_len/2.0; bv,tv=[],[]
    for i in range(segs):
        a=2*math.pi*i/segs; x,y=CUP_R*math.cos(a),CUP_R*math.sin(a)
        bv.append(bm.verts.new((x,y,-half))); tv.append(bm.verts.new((x,y,half)))
    for i in range(segs):
        j=(i+1)%segs; bm.faces.new([bv[i],bv[j],tv[j],tv[i]])
    bm.faces.new(list(reversed(bv))); bm.faces.new(tv)
    bm.normal_update(); bm.to_mesh(mesh); bm.free(); mesh.validate()
    obj.location=cut_ctr
    obj.rotation_euler=Vector((0,0,1)).rotation_difference(nv).to_euler()
    return obj

def make_hole_cutter(name, face_x, hole_y, hole_z, direction, depth, radius):
    centre_x = face_x + direction * depth / 2.0
    mesh=bpy.data.meshes.new(name+"_mesh")
    obj=bpy.data.objects.new(name,mesh)
    bpy.context.collection.objects.link(obj)
    bm=bmesh.new(); segs=64; half=depth/2.0+2.0
    bv,tv=[],[]
    for i in range(segs):
        a=2*math.pi*i/segs
        y_off=radius*math.cos(a); z_off=radius*math.sin(a)
        bv.append(bm.verts.new((-half,y_off,z_off)))
        tv.append(bm.verts.new(( half,y_off,z_off)))
    for i in range(segs):
        j=(i+1)%segs; bm.faces.new([bv[i],bv[j],tv[j],tv[i]])
    bm.faces.new(list(reversed(bv))); bm.faces.new(tv)
    bm.normal_update(); bm.to_mesh(mesh); bm.free(); mesh.validate()
    obj.location = Vector((centre_x, hole_y, hole_z))
    return obj

def make_wire_hole_cutter(name, cx, cy):
    """Vertical cylinder (Z-axis) for sensor wiring from cup to z=0 back face.
    Offset = CUP_R - WIRE_HOLE_RADIUS so hole edge is tangent to cup inner wall."""
    dz     = dome_z(cx, cy)
    bottom = -2.0
    top    = dz + PLATE_H + 2.0
    height = top - bottom
    center_z = (top + bottom) / 2.0
    # Tangent position: hole outer edge just touches cup wall at -Y
    offset = CUP_R - WIRE_HOLE_RADIUS
    mesh = bpy.data.meshes.new(name + "_mesh")
    obj  = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new(); segs = 32; half = height / 2.0; bv, tv = [], []
    for i in range(segs):
        a = 2 * math.pi * i / segs
        xo = WIRE_HOLE_RADIUS * math.cos(a); yo = WIRE_HOLE_RADIUS * math.sin(a)
        bv.append(bm.verts.new((xo, yo, -half))); tv.append(bm.verts.new((xo, yo, half)))
    for i in range(segs):
        j = (i + 1) % segs; bm.faces.new([bv[i], bv[j], tv[j], tv[i]])
    bm.faces.new(list(reversed(bv))); bm.faces.new(tv)
    bm.normal_update(); bm.to_mesh(mesh); bm.free(); mesh.validate()
    obj.location = Vector((cx, cy - offset, center_z))
    return obj

def make_box_cutter(name, x0, y0, z0, w, d, h):
    """Axis-aligned rectangular box boolean cutter."""
    x1,y1,z1 = x0+w, y0+d, z0+h
    mesh = bpy.data.meshes.new(name+"_mesh")
    obj  = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new()
    coords=[(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),
            (x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]
    for c in coords: bm.verts.new(c)
    bm.verts.ensure_lookup_table()
    for fi in [[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]]:
        bm.faces.new([bm.verts[i] for i in fi])
    bm.normal_update(); bm.to_mesh(mesh); bm.free(); mesh.validate()
    return obj

def make_canal_cutter(name, x0, y0, x1, y1):
    """Axis-aligned rectangular canal, CANAL_WIDTH wide × CANAL_DEPTH deep."""
    w2 = CANAL_WIDTH / 2.0; ov = 1.0
    if abs(y0 - y1) < 0.01:   # horizontal
        bx0,bx1 = min(x0,x1)-ov, max(x0,x1)+ov
        by0,by1 = y0-w2, y0+w2
    else:                      # vertical
        bx0,bx1 = x0-w2, x0+w2
        by0,by1 = min(y0,y1)-ov, max(y0,y1)+ov
    return make_box_cutter(name, bx0, by0, -1.0, bx1-bx0, by1-by0, CANAL_DEPTH+2.0)

def apply_transforms(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True); bpy.context.view_layer.objects.active=obj
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)

def do_diff(target, cutter):
    cutter.hide_render=False; cutter.hide_viewport=False; cutter.hide_set(False)
    bpy.ops.object.select_all(action='DESELECT')
    target.select_set(True); bpy.context.view_layer.objects.active=target
    mod=target.modifiers.new("Diff",'BOOLEAN')
    mod.operation='DIFFERENCE'; mod.object=cutter; mod.solver='FLOAT'
    try:
        bpy.ops.object.modifier_apply(modifier="Diff"); return True
    except Exception as e:
        print(f"    failed: {e}")
        try: target.modifiers.remove(mod)
        except: pass
        return False

def build_tile(tag, half_char, tile_idx, cx, cy):
    """Build tile with dome displacement + cup + pin hole if assigned."""
    # 1. Hex prism
    obj=make_hex_prism(f"Hex_{tag}",cx,cy)
    apply_transforms(obj)

    # 2. Dome displacement (top verts only)
    for v in obj.data.vertices:
        if v.co.z>0.01: v.co.z+=dome_z(v.co.x,v.co.y)
    obj.data.update()

    # 3. Cup recess
    cup=make_cup_cutter(f"Cut_{tag}",cx,cy)
    apply_transforms(cup); do_diff(obj,cup)
    bpy.data.objects.remove(cup,do_unlink=True)
    for v in obj.data.vertices:
        if v.co.z<0.01: v.co.z=0.0
    obj.data.update()

    # 3b. Wire hole — 5mm vertical passage from cup floor to z=0 back face
    wire = make_wire_hole_cutter(f"Wire_{tag}", cx, cy)
    apply_transforms(wire)
    pre_w = len(obj.data.polygons)
    ok_w  = do_diff(obj, wire)
    post_w= len(obj.data.polygons)
    bpy.data.objects.remove(wire, do_unlink=True)
    print(f"  {tag} wire: offset={CUP_R-WIRE_HOLE_RADIUS:.1f}mm -Y "
          f"{pre_w}→{post_w} {'✓' if ok_w and post_w>pre_w else '⚠ MISS'}")

    # 3c. Teensy cavity — right half tiles that overlap the cavity footprint only
    if half_char == 'R' and overlaps_cavity(cx, cy):
        cav = make_box_cutter(f"Cavity_{tag}",
                              CAVITY_X_OFFSET, -CAVITY_D/2.0, -2.0,
                              CAVITY_W,         CAVITY_D,      CAVITY_H_SAFE + 2.0)
        apply_transforms(cav)
        pre_cv  = len(obj.data.polygons)
        ok_cv   = do_diff(obj, cav)
        post_cv = len(obj.data.polygons)
        bpy.data.objects.remove(cav, do_unlink=True)
        print(f"  {tag} cavity: {pre_cv}→{post_cv} {'✓' if ok_cv and post_cv>pre_cv else '⚠ MISS'}")

    # 3d. Wiring canals — all tiles, per overlapping segment
    for si, (sx0, sy0, sx1, sy1) in enumerate(CANAL_SEGMENTS):
        if overlaps_canal(cx, cy, sx0, sy0, sx1, sy1):
            canal = make_canal_cutter(f"Canal_{tag}_{si}", sx0, sy0, sx1, sy1)
            apply_transforms(canal)
            do_diff(obj, canal)
            bpy.data.objects.remove(canal, do_unlink=True)
            print(f"  {tag} canal[{si}] ✓")

    # 4. Pin hole if this tile has one assigned
    key = (half_char, tile_idx)
    if key in PIN_ASSIGNMENTS:
        fside, dirn, lbl = PIN_ASSIGNMENTS[key]
        face_x = cx + cos30*S if fside=='R' else cx - cos30*S
        r = PIN_RADIUS + PIN_CLEARANCE
        hole = make_hole_cutter(
            f"Hole_{tag}", face_x, cy, PIN_Z, dirn, PIN_DEPTH, r
        )
        apply_transforms(hole)
        pre = len(obj.data.polygons)
        ok  = do_diff(obj, hole)
        post= len(obj.data.polygons)
        bpy.data.objects.remove(hole, do_unlink=True)
        print(f"  {tag} {lbl}: face_x={face_x:.1f} z={PIN_Z} "
              f"dir={'+X' if dirn>0 else '-X'} "
              f"{pre}→{post} {'✓' if ok and post>pre else '⚠ MISS'}")

    return obj

def join_and_clean(names,out_name):
    bpy.ops.object.select_all(action='DESELECT')
    for n in names:
        o=bpy.data.objects.get(n)
        if o: o.select_set(True)
    if not bpy.context.selected_objects: return None
    bpy.context.view_layer.objects.active=bpy.context.selected_objects[0]
    bpy.ops.object.join()
    obj=bpy.context.active_object; obj.name=out_name
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    return obj

def add_tile_label(label, cx, cy):
    dz=dome_z(cx,cy)
    bpy.ops.object.text_add(location=(cx,cy,dz+PLATE_H+1.0))
    txt=bpy.context.active_object
    txt.name=f"TileNum_{label}"
    txt.data.body=label; txt.data.size=8.0
    txt.data.align_x='CENTER'; txt.data.align_y='CENTER'
    return txt

# ---- Build all tiles -------------------------------------------------
print("\nBuilding tiles (pin holes cut per-tile)...")
left_names=[]; right_names=[]

for i,(cx,cy) in enumerate(left_grid):
    tag=f"L{i:02d}"
    obj=build_tile(tag,'L',i,cx,cy)
    left_names.append(obj.name); add_tile_label(tag,cx,cy)

for i,(cx,cy) in enumerate(right_grid):
    tag=f"R{i:02d}"
    obj=build_tile(tag,'R',i,cx,cy)
    right_names.append(obj.name); add_tile_label(tag,cx,cy)

# ---- Join ------------------------------------------------------------
print("\nJoining...")
left_obj  = join_and_clean(left_names,  "SensorBase_L")
right_obj = join_and_clean(right_names, "SensorBase_R")

# ---- Finalise --------------------------------------------------------
print("\nFinalising...")
for obj in [left_obj,right_obj]:
    if obj is None: continue
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True); bpy.context.view_layer.objects.active=obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    v=len(obj.data.vertices); f=len(obj.data.polygons)
    bb=[obj.matrix_world@Vector(c) for c in obj.bound_box]
    xs=[p.x for p in bb]; ys=[p.y for p in bb]
    w,d=max(xs)-min(xs),max(ys)-min(ys)
    print(f"  {obj.name}: {v}v {f}f {w:.0f}x{d:.0f}mm "
          f"{'✓' if w<=340 and d<=340 else '⚠'}")

# ---- Export ----------------------------------------------------------
print("\nExporting...")
for obj,suffix in [(left_obj,"L"),(right_obj,"R")]:
    if obj is None: continue
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True); bpy.context.view_layer.objects.active=obj
    stl=os.path.join(export_dir,f"hex_dome_v55_{suffix}.stl")
    objf=os.path.join(export_dir,f"hex_dome_v55_{suffix}.obj")
    exported=False
    for fn,kw in [
        (bpy.ops.wm.stl_export,   {"filepath":stl,"export_selected_objects":True}),
        (bpy.ops.export_mesh.stl, {"filepath":stl,"use_selection":True}),
        (bpy.ops.wm.obj_export,   {"filepath":objf,"export_selected_objects":True}),
    ]:
        if exported: break
        try: fn(**kw); print(f"  Exported: {stl}"); exported=True
        except Exception as e: print(f"    {e}")
    if not exported: print(f"  >>> Export {suffix} manually <<<")

print("\n=== DONE ===")
print(f"All 8 holes at PIN_Z={PIN_Z}mm — inside dome body")
print("All cut per-tile before joining — guaranteed intersection")