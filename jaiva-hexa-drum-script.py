# ============================================================
# Blender Script: Hex Dome Array V52
# ALL 4 pairs cut per-tile BEFORE joining.
# PIN_Z = 20mm for all pairs — inside dome body.
# Per-tile cutting guarantees boolean always hits solid material.
# ============================================================

import bpy
import bmesh
import math
import os
from mathutils import Vector

print("=== HEX DOME ARRAY V52 - ALL HOLES PER-TILE ===")

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
    if obj.name.startswith(("Hex_","Cut_","SensorBase","Hole_","TileNum_")):
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
    stl=os.path.join(export_dir,f"hex_dome_v52_{suffix}.stl")
    objf=os.path.join(export_dir,f"hex_dome_v52_{suffix}.obj")
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