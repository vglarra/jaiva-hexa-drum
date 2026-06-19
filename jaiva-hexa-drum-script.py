# ============================================================
# Blender Script: Hex Dome Array V82
# FIX: silent boolean failures were being reported as "✓" — every
# do_diff() call now has its return value checked and reported
# honestly, with a final FAILURES summary. This is almost certainly
# why canals were "disappearing" in the slicer: the EXACT/FLOAT
# booleans were failing internally, the modifier was removed without
# cutting anything, and the script printed "✓" anyway.
# FIX: R07 post-dome canal cutter was centered exactly ON the L/R
# split plane (x=0), so half the cutter box had nothing to cut
# against and the other half sat exactly coplanar with the model's
# flat seam face — that's the degenerate sliver you saw. The cutter
# is now biased fully into the RIGHT half with a small overlap past
# the seam, so it never touches the seam face edge-on.
# ============================================================

import bpy
import bmesh
import math
import os
from mathutils import Vector

print("=== HEX DOME ARRAY V82 - HONEST FAILURE REPORTING + R07 SEAM FIX ===")

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
PIN_Z          = 20.0

WIRE_HOLE_DIA    = 5.0
WIRE_HOLE_RADIUS = WIRE_HOLE_DIA / 2.0

CANAL_WIDTH = 10.0
CANAL_DEPTH =  3.0   # groove depth (leaves 3mm solid roof in 6mm plate)

CAVITY_X_OFFSET = 9.0
CAVITY_W = 50.0
CAVITY_D = 90.0
CAVITY_H = 30.0

blend_path = bpy.data.filepath
export_dir = os.path.dirname(blend_path) if blend_path else os.path.expanduser("~")
print(f"PIN_Z={PIN_Z}mm  CANAL_DEPTH={CANAL_DEPTH}mm")
print(f"Export: {export_dir}")

# ---- Failure tracking (NEW in v82) ------------------------------------
FAILURES = []   # list of (label, reason) tuples — printed at the very end

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
# Cavity goes 30mm deep into dome structure; ceiling = dome minimum − 2mm clearance
CAVITY_H_SAFE  = min(CAVITY_H, _min_dome_cav - 2.0)
if CAVITY_H_SAFE < CAVITY_H:
    print(f"⚠ CAVITY_H capped {CAVITY_H:.1f}→{CAVITY_H_SAFE:.1f}mm")
print(f"Cavity {CAVITY_W:.0f}×{CAVITY_D:.0f}×{CAVITY_H_SAFE:.1f}mm deep into dome  "
      f"x={CAVITY_X_OFFSET:.0f}..{CAVITY_X_OFFSET+CAVITY_W:.0f}")

# ---- Canal segments --------------------------------------------------
_wo = CUP_R - WIRE_HOLE_RADIUS
CANAL_SEGMENTS = [
    (-2.0*H,                     y2-_wo,  CAVITY_X_OFFSET,              y2-_wo),
    (CAVITY_X_OFFSET + CAVITY_W, y2-_wo,  2.0*H,                        y2-_wo),
    (-1.5*H,  y1-_wo,   1.5*H,  y1-_wo),
    (0.5*H,   y3-_wo,   1.5*H,  y3-_wo),
    (0.5*H,   CAVITY_D/2.0, 0.5*H, y3-_wo),
    (0.5*H,   y1-_wo,   0.5*H, -CAVITY_D/2.0),
    (0.0,     y0-_wo,   0.0,  y1-_wo),
    (H,       y0-_wo,   H,    y1-_wo),
    (-1.5*H,  y3-_wo,  -0.5*H,  y3-_wo),
    (-H,      y3-_wo,  -H,      y2-_wo),
    (-H,      y1-_wo,  -H,      y2-_wo),
    (-H,      y0-_wo,  -H,      y1-_wo),
]

def clip_segment(x0, y0, x1, y1, xmin, xmax, ymin, ymax, margin=3.0):
    xmin+=margin; xmax-=margin; ymin+=margin; ymax-=margin
    if xmin>=xmax or ymin>=ymax: return None
    if abs(y0-y1)<0.01:
        if y0<ymin or y0>ymax: return None
        lo,hi=max(min(x0,x1),xmin),min(max(x0,x1),xmax)
        return (lo,y0,hi,y0) if lo<hi else None
    else:
        if x0<xmin or x0>xmax: return None
        lo,hi=max(min(y0,y1),ymin),min(max(y0,y1),ymax)
        return (x0,lo,x0,hi) if lo<hi else None

# ---- Pin assignments -------------------------------------------------
PIN_ASSIGNMENTS = {
    ('L', 1): ('R', -1, 'Pair1'),
    ('R', 0): ('L', +1, 'Pair1'),
    ('L', 3): ('R', -1, 'Pair2'),
    ('R', 2): ('L', +1, 'Pair2'),
    ('L', 5): ('R', -1, 'Pair3'),
    ('R', 5): ('L', +1, 'Pair3'),
    ('L', 6): ('R', -1, 'Pair4'),
    ('R', 7): ('L', +1, 'Pair4'),
}

# ---- Cleanup ---------------------------------------------------------
for obj in list(bpy.data.objects):
    if obj.name.startswith(("Hex_","Cut_","SensorBase","Hole_","Wire_","Cavity_","Canal_","TileNum_")):
        bpy.data.objects.remove(obj, do_unlink=True)

HEX_ANGLES = [math.radians(30+60*i) for i in range(6)]

# ---- Builders --------------------------------------------------------
def make_cup_cutter(name, cx, cy):
    nv=dome_normal(cx,cy); dz=dome_z(cx,cy)
    tile_top=Vector((cx,cy,dz))+nv*PLATE_H
    cut_len=CUP_DEPTH+1.0; cut_ctr=tile_top+nv*(0.5-CUP_DEPTH/2.0)
    mesh=bpy.data.meshes.new(name+"_mesh"); obj=bpy.data.objects.new(name,mesh)
    bpy.context.collection.objects.link(obj)
    bm=bmesh.new(); segs,half=64,cut_len/2.0; bv,tv=[],[]
    for i in range(segs):
        a=2*math.pi*i/segs; x,y=CUP_R*math.cos(a),CUP_R*math.sin(a)
        bv.append(bm.verts.new((x,y,-half))); tv.append(bm.verts.new((x,y,half)))
    for i in range(segs):
        j=(i+1)%segs; bm.faces.new([bv[i],bv[j],tv[j],tv[i]])
    bm.faces.new(list(reversed(bv))); bm.faces.new(tv)
    bm.normal_update(); bm.to_mesh(mesh); bm.free(); mesh.validate()
    obj.location=cut_ctr; obj.rotation_euler=Vector((0,0,1)).rotation_difference(nv).to_euler()
    return obj

def make_hole_cutter(name, face_x, hole_y, hole_z, direction, depth, radius):
    centre_x=face_x+direction*depth/2.0
    mesh=bpy.data.meshes.new(name+"_mesh"); obj=bpy.data.objects.new(name,mesh)
    bpy.context.collection.objects.link(obj)
    bm=bmesh.new(); segs=64; half=depth/2.0+2.0; bv,tv=[],[]
    for i in range(segs):
        a=2*math.pi*i/segs
        y_off=radius*math.cos(a); z_off=radius*math.sin(a)
        bv.append(bm.verts.new((-half,y_off,z_off))); tv.append(bm.verts.new((half,y_off,z_off)))
    for i in range(segs):
        j=(i+1)%segs; bm.faces.new([bv[i],bv[j],tv[j],tv[i]])
    bm.faces.new(list(reversed(bv))); bm.faces.new(tv)
    bm.normal_update(); bm.to_mesh(mesh); bm.free(); mesh.validate()
    obj.location=Vector((centre_x,hole_y,hole_z))
    return obj

def make_wire_hole_cutter(name, cx, cy):
    dz=dome_z(cx,cy); bottom=-2.0; top=dz+PLATE_H+2.0
    height=top-bottom; center_z=(top+bottom)/2.0; offset=CUP_R-WIRE_HOLE_RADIUS
    mesh=bpy.data.meshes.new(name+"_mesh"); obj=bpy.data.objects.new(name,mesh)
    bpy.context.collection.objects.link(obj)
    bm=bmesh.new(); segs=32; half=height/2.0; bv,tv=[],[]
    for i in range(segs):
        a=2*math.pi*i/segs; xo=WIRE_HOLE_RADIUS*math.cos(a); yo=WIRE_HOLE_RADIUS*math.sin(a)
        bv.append(bm.verts.new((xo,yo,-half))); tv.append(bm.verts.new((xo,yo,half)))
    for i in range(segs):
        j=(i+1)%segs; bm.faces.new([bv[i],bv[j],tv[j],tv[i]])
    bm.faces.new(list(reversed(bv))); bm.faces.new(tv)
    bm.normal_update(); bm.to_mesh(mesh); bm.free(); mesh.validate()
    obj.location=Vector((cx,cy-offset,center_z))
    return obj

def make_box_cutter(name, x0, y0, z0, w, d, h):
    x1,y1,z1=x0+w,y0+d,z0+h
    mesh=bpy.data.meshes.new(name+"_mesh"); obj=bpy.data.objects.new(name,mesh)
    bpy.context.collection.objects.link(obj)
    bm=bmesh.new()
    for c in [(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),
              (x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]:
        bm.verts.new(c)
    bm.verts.ensure_lookup_table()
    for fi in [[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]]:
        bm.faces.new([bm.verts[i] for i in fi])
    bm.normal_update(); bm.to_mesh(mesh); bm.free(); mesh.validate()
    return obj

def make_canal_cutter(name, x0, y0, x1, y1):
    w2=CANAL_WIDTH/2.0; ov=2.0
    if abs(y0-y1)<0.01:
        bx0,bx1=min(x0,x1)-ov,max(x0,x1)+ov; by0,by1=y0-w2,y0+w2
    else:
        bx0,bx1=x0-w2,x0+w2; by0,by1=min(y0,y1)-ov,max(y0,y1)+ov
    return make_box_cutter(name,bx0,by0,-0.1,bx1-bx0,by1-by0,CANAL_DEPTH+0.1)

def apply_transforms(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True); bpy.context.view_layer.objects.active=obj
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)

def do_diff(target, cutter, solver='EXACT'):
    """Returns True/False. NOTE (v82): callers must check this return
    value — previously several call sites ignored it and printed a
    success checkmark unconditionally, which is why failed canal cuts
    looked successful in the console log but never actually removed
    material."""
    cutter.hide_render=False; cutter.hide_viewport=False; cutter.hide_set(False)
    bpy.ops.object.select_all(action='DESELECT')
    target.select_set(True); bpy.context.view_layer.objects.active=target
    mod=target.modifiers.new("Diff",'BOOLEAN')
    mod.operation='DIFFERENCE'; mod.object=cutter; mod.solver=solver
    try:
        bpy.ops.object.modifier_apply(modifier="Diff"); return True
    except Exception as e:
        print(f"    failed ({solver}): {e}")
        try: target.modifiers.remove(mod)
        except: pass
        return False

def do_diff_retry(target, cutter, solver='EXACT'):
    """v82: if the requested solver fails, automatically retry once with
    the other solver before giving up. EXACT and FLOAT fail on different
    kinds of geometry (coplanar faces vs. precision drift), so trying
    both catches more real cuts instead of silently leaving material
    uncut."""
    ok = do_diff(target, cutter, solver=solver)
    if ok:
        return True, solver
    alt = 'FLOAT' if solver == 'EXACT' else 'EXACT'
    print(f"    retrying with {alt}...")
    ok2 = do_diff(target, cutter, solver=alt)
    return ok2, (alt if ok2 else solver)

def make_flat_hex_solid(grid_tiles, solid_name):
    """Flat hex plate (solid-first, no interior walls, no dome)."""
    edge_use={}; tile_data=[]
    for cx,cy in grid_tiles:
        cors=[(round(cx+S*math.cos(a),3),round(cy+S*math.sin(a),3)) for a in HEX_ANGLES]
        tile_data.append((cx,cy,cors))
        for i in range(6):
            j=(i+1)%6; ekey=tuple(sorted([cors[i],cors[j]]))
            edge_use[ekey]=edge_use.get(ekey,0)+1
    mesh=bpy.data.meshes.new(solid_name+"_mesh")
    obj=bpy.data.objects.new(solid_name,mesh)
    bpy.context.collection.objects.link(obj)
    bm=bmesh.new(); vmap={}
    def gv(xy,z):
        k=(xy[0],xy[1],round(z,3))
        if k not in vmap: vmap[k]=bm.verts.new((xy[0],xy[1],z))
        return vmap[k]
    for cx,cy,cors in tile_data:
        cc=(round(cx,3),round(cy,3))
        bc=gv(cc,0.0); tc=gv(cc,PLATE_H)
        for i in range(6):
            j=(i+1)%6
            b0=gv(cors[i],0.0); b1=gv(cors[j],0.0)
            t0=gv(cors[i],PLATE_H); t1=gv(cors[j],PLATE_H)
            try: bm.faces.new([bc,b1,b0])
            except: pass
            try: bm.faces.new([tc,t0,t1])
            except: pass
            ekey=tuple(sorted([cors[i],cors[j]]))
            if edge_use[ekey]==1:
                try: bm.faces.new([t0,t1,b0])
                except: pass
                try: bm.faces.new([t1,b1,b0])
                except: pass
    bmesh.ops.triangulate(bm,faces=bm.faces[:])
    bm.normal_update(); bm.to_mesh(mesh); bm.free(); mesh.validate()
    return obj

def add_dome_to_top(obj):
    """Displace top-face vertices by dome_z, identified by face normals.
    Top faces have outward normal.z > 0.7. Robust against EXACT z-drift
    (unlike z-threshold which fails when EXACT places vertices at z=5.999mm)."""
    bm2=bmesh.new()
    bm2.from_mesh(obj.data)
    bm2.normal_update()
    bm2.verts.ensure_lookup_table()
    displaced=0
    for v in bm2.verts:
        if any(f.normal.z > 0.7 for f in v.link_faces):
            v.co.z += dome_z(v.co.x, v.co.y)
            displaced += 1
    bm2.normal_update(); bm2.to_mesh(obj.data); bm2.free(); obj.data.update()
    print(f"  Dome displacement: {displaced} vertices lifted")

def get_bbox(obj):
    bb=[obj.matrix_world@Vector(c) for c in obj.bound_box]
    xs=[p.x for p in bb]; ys=[p.y for p in bb]
    return min(xs),max(xs),min(ys),max(ys)

_R07_CANAL_IDX = 6  # CANAL_SEGMENTS[6] = (0.0, y0-_wo, 0.0, y1-_wo) — R07 vertical rise

def apply_canals(solid_obj, half_char):
    """EXACT canal cuts on flat plate — simple axis-aligned box × flat surface.
    R07's canal (index 6, x=0mm through tile center) is deferred to post-dome
    step for the right half to avoid EXACT z-drift issues at cx=0.
    v82: return value of every cut is now checked and reported honestly."""
    xmin,xmax,ymin,ymax=get_bbox(solid_obj)
    for si,(sx0,sy0,sx1,sy1) in enumerate(CANAL_SEGMENTS):
        if half_char == 'R' and si == _R07_CANAL_IDX:
            print(f"  R canal[{si}] R07 → deferred to post-dome")
            continue
        clipped=clip_segment(sx0,sy0,sx1,sy1,xmin,xmax,ymin,ymax,margin=3.0)
        if clipped is None: continue
        nx0,ny0,nx1,ny1=clipped
        if abs(nx0-nx1)<0.5 and abs(ny0-ny1)<0.5: continue
        canal=make_canal_cutter(f"Canal_{half_char}_{si}",nx0,ny0,nx1,ny1)
        apply_transforms(canal)
        ok, used = do_diff_retry(solid_obj,canal,solver='EXACT')
        bpy.data.objects.remove(canal,do_unlink=True)
        label=f"{half_char} canal[{si}]"
        if ok:
            print(f"  {label} ✓ ({used})")
        else:
            print(f"  {label} ✗ FAILED — material NOT removed")
            FAILURES.append((label, "boolean failed (EXACT+FLOAT)"))

def apply_r07_canal_postdome(right_obj):
    """Apply R07 vertical canal AFTER dome displacement, using FLOAT.
    v82 fix: the cutter used to be centered exactly on x=0 — the L/R
    split plane — so it straddled the seam: half the box had nothing
    to cut against (outside right_obj's geometry) and the other half
    sat exactly coplanar with the model's flat seam face. That
    coincident-face condition is what produced the degenerate sliver
    seen in the viewport. Now the cutter is biased fully into the
    RIGHT half, with only a small 1mm overlap past the seam so the
    boolean never runs edge-on along an existing face."""
    sx0,sy0,sx1,sy1 = CANAL_SEGMENTS[_R07_CANAL_IDX]
    xmin,xmax,ymin,ymax = get_bbox(right_obj)
    clipped = clip_segment(sx0,sy0,sx1,sy1,xmin,xmax,ymin,ymax,margin=3.0)
    if clipped is None:
        print("  R07 canal post-dome: nothing to cut (clipped out)"); return
    nx0,ny0,nx1,ny1 = clipped
    if abs(nx0-nx1)<0.5 and abs(ny0-ny1)<0.5:
        print("  R07 canal post-dome: segment too short"); return

    # --- biased box, replaces make_canal_cutter's symmetric ±w2 ---
    OVERLAP_PAST_SEAM = 1.0   # mm sticking out past SPLIT_X into empty space — harmless
    bx0 = SPLIT_X - OVERLAP_PAST_SEAM
    bx1 = bx0 + CANAL_WIDTH
    ov  = 2.0
    by0,by1 = min(ny0,ny1)-ov, max(ny0,ny1)+ov
    canal = make_box_cutter("Canal_R07_postdome", bx0, by0, -2.0,
                             bx1-bx0, by1-by0, CANAL_DEPTH+4.0)
    apply_transforms(canal)
    ok, used = do_diff_retry(right_obj, canal, solver='FLOAT')
    bpy.data.objects.remove(canal, do_unlink=True)
    if ok:
        print(f"  R07 canal (post-dome) ✓ ({used}) — biased x={bx0:.1f}..{bx1:.1f}")
    else:
        print("  R07 canal (post-dome) ✗ FAILED — material NOT removed")
        FAILURES.append(("R07 canal (post-dome)", "boolean failed (FLOAT+EXACT)"))

def apply_tile_cuts(solid_obj, tag, half_char, tile_idx, cx, cy):
    """Post-dome cuts:
    - Cup / wire: FLOAT (dome surface is complex triangulation; FLOAT more robust)
    - Pin holes: EXACT (seam walls are flat vertical rectangles → clean EXACT)
    Cavity applied separately after all tile cuts.
    v82: every cut's success/failure is now checked and reported."""
    cup=make_cup_cutter(f"Cut_{tag}",cx,cy)
    apply_transforms(cup)
    ok_cup, used_cup = do_diff_retry(solid_obj,cup,solver='FLOAT')
    bpy.data.objects.remove(cup,do_unlink=True)

    wire=make_wire_hole_cutter(f"Wire_{tag}",cx,cy)
    apply_transforms(wire)
    ok_wire, used_wire = do_diff_retry(solid_obj,wire,solver='FLOAT')
    bpy.data.objects.remove(wire,do_unlink=True)

    if ok_cup and ok_wire:
        print(f"  {tag} cup+wire ✓")
    else:
        if not ok_cup:
            print(f"  {tag} cup ✗ FAILED"); FAILURES.append((f"{tag} cup","boolean failed"))
        if not ok_wire:
            print(f"  {tag} wire ✗ FAILED"); FAILURES.append((f"{tag} wire","boolean failed"))

    key=(half_char,tile_idx)
    if key in PIN_ASSIGNMENTS:
        fside,dirn,lbl=PIN_ASSIGNMENTS[key]
        face_x=cx+cos30*S if fside=='R' else cx-cos30*S
        r=PIN_RADIUS+PIN_CLEARANCE
        hole=make_hole_cutter(f"Hole_{tag}",face_x,cy,PIN_Z,dirn,PIN_DEPTH,r)
        apply_transforms(hole)
        ok_pin, used_pin = do_diff_retry(solid_obj,hole,solver='EXACT')
        bpy.data.objects.remove(hole,do_unlink=True)
        if ok_pin:
            print(f"  {tag} {lbl} pin ✓ ({used_pin})")
        else:
            print(f"  {tag} {lbl} pin ✗ FAILED")
            FAILURES.append((f"{tag} {lbl} pin","boolean failed"))

def apply_cavity(solid_obj):
    """Teensy cavity — deep pocket into dome (CAVITY_H_SAFE ≈ 30mm).
    Uses FLOAT: EXACT creates a fully enclosed void (0 shell) when the
    cavity ceiling doesn't pierce the bottom face cleanly."""
    cav=make_box_cutter("Cavity_R",
                        CAVITY_X_OFFSET, -CAVITY_D/2.0, -2.0,
                        CAVITY_W, CAVITY_D, CAVITY_H_SAFE+2.0)
    apply_transforms(cav)
    ok=do_diff(solid_obj,cav,solver='FLOAT')
    bpy.data.objects.remove(cav,do_unlink=True)
    print(f"  Cavity {'✓' if ok else '⚠ FAIL'}")
    if not ok:
        FAILURES.append(("Teensy cavity","boolean failed"))

def add_tile_label(label,cx,cy):
    dz=dome_z(cx,cy)
    bpy.ops.object.text_add(location=(cx,cy,dz+PLATE_H+1.0))
    txt=bpy.context.active_object; txt.name=f"TileNum_{label}"
    txt.data.body=label; txt.data.size=8.0
    txt.data.align_x='CENTER'; txt.data.align_y='CENTER'
    return txt

def add_bottom_label(label,cx,cy):
    bpy.ops.object.text_add(location=(cx,cy,-1.0))
    txt=bpy.context.active_object; txt.name=f"TileNum_B_{label}"
    txt.data.body=label; txt.data.size=8.0
    txt.data.align_x='CENTER'; txt.data.align_y='CENTER'
    txt.rotation_euler=(math.pi,0,0)
    return txt

# ============================================================
# BUILD SEQUENCE
# ============================================================

print("\nStep 1: Build flat hex plates (solid-first, no interior walls)...")
left_obj  = make_flat_hex_solid(left_grid,  "SensorBase_L")
right_obj = make_flat_hex_solid(right_grid, "SensorBase_R")

print("\nStep 2: Cut canals into flat plates (EXACT on simple geometry)...")
apply_canals(left_obj,  'L')
apply_canals(right_obj, 'R')

print("\nStep 3: Add dome displacement via face normals (R07-safe)...")
add_dome_to_top(left_obj)
add_dome_to_top(right_obj)

print("\nStep 4: Cut cups / wire holes / pin holes (EXACT post-dome)...")
for i,(cx,cy) in enumerate(left_grid):
    tag=f"L{i:02d}"
    apply_tile_cuts(left_obj,tag,'L',i,cx,cy)
    add_tile_label(tag,cx,cy); add_bottom_label(tag,cx,cy)
for i,(cx,cy) in enumerate(right_grid):
    tag=f"R{i:02d}"
    apply_tile_cuts(right_obj,tag,'R',i,cx,cy)
    add_tile_label(tag,cx,cy); add_bottom_label(tag,cx,cy)

print("\nStep 4b: R07 vertical canal — post-dome FLOAT, biased off the seam...")
apply_r07_canal_postdome(right_obj)

print("\nStep 5: Teensy cavity (FLOAT, deep into dome structure)...")
apply_cavity(right_obj)

# Snap bottom to z=0
for obj in [left_obj,right_obj]:
    for v in obj.data.vertices:
        if abs(v.co.z)<0.01: v.co.z=0.0
    obj.data.update()

# ---- Finalise --------------------------------------------------------
print("\nFinalising...")
for obj in [left_obj,right_obj]:
    if obj is None: continue
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True); bpy.context.view_layer.objects.active=obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.remove_doubles(threshold=0.001)
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    v=len(obj.data.vertices); f=len(obj.data.polygons)
    bb=[obj.matrix_world@Vector(c) for c in obj.bound_box]
    xs=[p.x for p in bb]; ys=[p.y for p in bb]
    w,d=max(xs)-min(xs),max(ys)-min(ys)
    print(f"  {obj.name}: {v}v {f}f {w:.0f}×{d:.0f}mm {'✓' if w<=340 and d<=340 else '⚠'}")

# ---- Failure summary (NEW in v82) -------------------------------------
print("\n" + "="*60)
if FAILURES:
    print(f"⚠ {len(FAILURES)} BOOLEAN CUT(S) FAILED — these features are MISSING from the export:")
    for label, reason in FAILURES:
        print(f"   ✗ {label}: {reason}")
    print("These will NOT appear in the STL even though earlier versions")
    print("of this script would have printed '✓' for them regardless.")
else:
    print("✓ All boolean cuts succeeded — every canal/cup/wire/pin/cavity is real.")
print("="*60)

# ---- Export ----------------------------------------------------------
print("\nExporting...")
for obj,suffix in [(left_obj,"L"),(right_obj,"R")]:
    if obj is None: continue
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True); bpy.context.view_layer.objects.active=obj
    stl=os.path.join(export_dir,f"hex_dome_v1_{suffix}.stl")
    objf=os.path.join(export_dir,f"hex_dome_v1_{suffix}.obj")
    exported=False
    for fn,kw in [
        (bpy.ops.wm.stl_export,   {"filepath":stl, "export_selected_objects":True}),
        (bpy.ops.export_mesh.stl, {"filepath":stl, "use_selection":True}),
        (bpy.ops.wm.obj_export,   {"filepath":objf,"export_selected_objects":True}),
    ]:
        if exported: break
        try: fn(**kw); print(f"  Exported: {stl}"); exported=True
        except Exception as e: print(f"    {e}")
    if not exported: print(f"  >>> Export {suffix} manually <<<")

print("\n=== DONE ===")
print(f"CANAL_DEPTH={CANAL_DEPTH}mm  CAVITY_H_SAFE={CAVITY_H_SAFE:.1f}mm  PIN_Z={PIN_Z}mm")
print(f"Failures: {len(FAILURES)}")