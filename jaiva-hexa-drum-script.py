# ============================================================
# Blender Script: Hex Dome Array V100
# (v82: honest do_diff() reporting + R07 seam bias)
# (v83: stronger end-of-build cleanup pass)
# (v84: per-cut manifold tracking — pinpointed L01/L06 pins)
# (v85: try-before-commit safe_cut — confirmed clean, 0 failures)
# (v86: per-pair PIN_Z override for Pair4 — L06/R07 pin lowered 5mm)
# (v87/v88: real bottom-face tile engraving, Z-position bug + fix)
# (v89: offset refinement — L03/L06/R07/R08 -20mm, R05 +40mm, R02
#  -10mm, font +10%)
# (v90: dedicated 10mm MIDI/DC cable port, R00 to the Teensy cavity)
# (v91: rounded inside corners at canal junctions, seam left square)
# (v92: rounded canal dead-end caps + a missed junction fix)
# (v93: R07 canal depth fix + centered on x=0)
# (v94: nudged R07 canal + bumped CAP_RADIUS to 5.3mm for "robustness")
# (v95: real R07 fix — reordered the canal cut before any wire holes,
#  using the simple box+separate-circle approach — measured 0 issues)
# (v96: reverted CAP_RADIUS to exact 5.0mm tangency)
# (v97/v98: unified box+cap into one single-mesh cutter for every
#  canal, fixed its winding order)
# (v99: R07 reverted to the v95 two-cut approach — down to 6 minor
#  residual issues total, all in non-structural rounding details,
#  confirmed working in an actual slice/print test)
# NEW in v100: Teensy cavity extended 10mm in +X (CAVITY_W 50→60mm),
# reaching further into R05's footprint per request. CAVITY_X_OFFSET
# (left edge) unchanged.
# ============================================================

import bpy
import bmesh
import math
import os
from mathutils import Vector

print("=== HEX DOME ARRAY V100 - CAVITY EXTENDED 10MM IN +X ===")

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
CAVITY_W = 60.0   # v100: was 50.0 — extended 10mm in +X per request,
                   # reaching further into R05's footprint. Left edge
                   # (CAVITY_X_OFFSET=9) is unchanged; only the right
                   # edge moves, from x=59 to x=69. Every canal segment
                   # and the CAVITY_H_SAFE calculation reference these
                   # constants directly, so they adjust automatically —
                   # no other coordinates need to change by hand.
CAVITY_D = 90.0
CAVITY_H = 30.0

# v87: real (printable) tile numbers engraved into the bottom face,
# replacing the old floating/unprinted text reference. Cut as a
# shallow recess so it actually shows up on the part, not just in
# the Blender viewport.
ENGRAVE_DEPTH = 0.6   # mm recessed into the bottom face
ENGRAVE_SIZE  = 8.8   # was 8.0, +10% per request
MIRROR_BOTTOM_TEXT = False  # flip to True if the engraved numbers come
                             # out mirrored when you look at the actual
                             # bottom face (this is the one part worth
                             # eyeballing in Blender before printing)

# v90: dedicated 10mm MIDI/DC cable port, R00 exterior wall straight
# to the Teensy cavity. Offset off R00's own center x (38.5mm) so it
# doesn't run straight through the existing wire-hole shaft, which
# sits exactly at x=38.5 — per explicit request, this is a fully
# separate path. x=50 stays inside both R00's NE edge and the
# cavity's own x-range (9..59).
CABLE_PORT_X   = 50.0
CABLE_PORT_DIA = 10.0
CABLE_PORT_R   = CABLE_PORT_DIA / 2.0

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
    # (x0, y0, x1, y1, cap0, cap1) — cap0/cap1 say whether THAT end is
    # a true dead end (wire-hole terminus) needing a rounded semicircle
    # cap, vs. a junction/cavity-opening/seam end that just needs the
    # normal small overlap to merge cleanly into whatever's there.
    (-2.0*H,                     y2-_wo,  CAVITY_X_OFFSET,              y2-_wo, True,  False),  # L02 cap … cavity
    (CAVITY_X_OFFSET + CAVITY_W, y2-_wo,  2.0*H,                        y2-_wo, False, True),    # cavity … R04 cap
    (-1.5*H,  y1-_wo,   1.5*H,  y1-_wo, True,  True),     # L04 cap … R06 cap
    (0.5*H,   y3-_wo,   1.5*H,  y3-_wo, False, True),     # junction … R01 cap
    (0.5*H,   CAVITY_D/2.0, 0.5*H, y3-_wo, False, False), # cavity … junction
    (0.5*H,   y1-_wo,   0.5*H, -CAVITY_D/2.0, False, False), # junction … cavity
    (0.0,     y0-_wo,   0.0,  y1-_wo, True,  False),      # R07 cap … seam (handled separately, post-dome)
    (H,       y0-_wo,   H,    y1-_wo, True,  False),      # R08 cap … junction
    (-1.5*H,  y3-_wo,  -0.5*H,  y3-_wo, True,  True),     # L00 cap … L01 cap
    (-H,      y3-_wo,  -H,      y2-_wo, False, False),    # junction … junction
    (-H,      y1-_wo,  -H,      y2-_wo, False, False),    # junction … junction
    (-H,      y0-_wo,  -H,      y1-_wo, True,  False),    # L06 cap … junction
]

# v91: every point where two canal segments meet at a corner/T/cross,
# worked out by hand from the endpoints above. Rounding these makes
# wire-pulling smoother (no sharp 90° snag point) and prints cleaner.
# Deliberately NOT included: (0, y1-_wo), where R07's canal merges
# into the shared y1-row trunk — that point sits exactly on x=0, the
# L/R split line, and has to stay flat/square for the two halves to
# mate cleanly. Every junction below is safely interior to one half.
CANAL_FILLET_RADIUS = 7.0   # mm — slightly larger than the canal's own
                             # 5mm half-width, just enough to round the
                             # corner without noticeably widening the
                             # channel
CANAL_JUNCTIONS = [
    (0.5*H, y3-_wo, 'R'),   # R00 wire-drop meets the y3-row trunk
    (0.5*H, y1-_wo, 'R'),   # R05 wire-drop meets the y1-row trunk
    (H,     y1-_wo, 'R'),   # v92 fix: R08's column crosses the y1-row
                            # trunk at R06's x — missed in v91
    (-H,    y3-_wo, 'L'),   # y3-row trunk meets the L03/L06 column
    (-H,    y2-_wo, 'L'),   # L03/L06 column crosses the y2-row trunk
    (-H,    y1-_wo, 'L'),   # L03/L06 column crosses the y1-row trunk
]

# v97: caps are no longer a separate boolean step. v92's approach (cut
# the straight canal, THEN boolean-union a separate circle onto its
# end) needs that circle and the box to merge via a boolean — and the
# only radius with zero visual kink (exact tangency) is exactly the
# float-precision case CSG solvers are worst at, which is what
# produced the malformed lens-shaped cusp seen in the viewport.
# make_canal_with_caps_cutter below builds the straight sides AND any
# semicircular cap as ONE continuous polygon from the start, so there
# is no separate shape to union — cap0/cap1 in CANAL_SEGMENTS now
# drive that directly, and apply_canal_caps / CAP_RADIUS / CANAL_CAPS
# are retired.

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

# v86: per-pair Z override. A pin bridges two tiles, so both sides of a
# pair must move together or the pin won't line up when glued — this
# is keyed by pair label, not by individual tile, and applied to
# whichever tile that label shows up on. Pair4 (L06↔R07) sits far
# enough from the dome center that PIN_Z=20mm put the cutter high
# enough to poke through the top surface — lowering it 5mm keeps it
# fully inside the wall there. The other 3 pairs are unaffected.
PIN_Z_OVERRIDES = {
    'Pair4': PIN_Z - 5.0,   # 20.0 → 15.0mm
}

# v87: L03, L06, R07, R08 each have a canal trunk running straight
# down their own center column (x = their cx exactly — that's not a
# coincidence, the canal is routed there on purpose to feed the wire
# hole above it). v88: R05 has the same issue (CANAL_SEGMENTS[4]/[5]
# both sit at x=38.5mm — R05's own cx). Offsets below are per your
# direct measurement, not my earlier guess. Every other tile is
# unaffected and keeps its label dead-center.
BOTTOM_LABEL_OFFSET = {
    'L03': (-20.0, 0.0),
    'L06': (-20.0, 0.0),
    'R07': (-20.0, 0.0),
    'R08': (-20.0, 0.0),
    'R05': ( 40.0, 0.0),
    'R02': (-10.0, 0.0),
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

def make_hole_cutter_y(name, hole_x, y0, y1, hole_z, radius):
    """v90: same idea as make_hole_cutter, but bored along Y instead
    of X — used for the R00→cavity cable port. y0 should be clearly
    outside the dome, y1 clearly inside/past the target region (same
    'always overlap past the boundary, never end exactly on a face'
    rule used by every other cutter in this script)."""
    length=y1-y0; centre_y=(y0+y1)/2.0
    mesh=bpy.data.meshes.new(name+"_mesh"); obj=bpy.data.objects.new(name,mesh)
    bpy.context.collection.objects.link(obj)
    bm=bmesh.new(); segs=64; half=length/2.0; bv,tv=[],[]
    for i in range(segs):
        a=2*math.pi*i/segs
        x_off=radius*math.cos(a); z_off=radius*math.sin(a)
        bv.append(bm.verts.new((x_off,-half,z_off))); tv.append(bm.verts.new((x_off,half,z_off)))
    for i in range(segs):
        j=(i+1)%segs; bm.faces.new([bv[i],bv[j],tv[j],tv[i]])
    bm.faces.new(list(reversed(bv))); bm.faces.new(tv)
    bm.normal_update(); bm.to_mesh(mesh); bm.free(); mesh.validate()
    obj.location=Vector((hole_x,centre_y,hole_z))
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
    """v97: superseded by make_canal_with_caps_cutter for every
    pre-dome canal (cap0=cap1=False reproduces this exactly).
    v99: back in active use for R07's post-dome canal specifically —
    a plain box turned out to be the more robust choice against that
    one harder, post-dome target. See apply_r07_canal_postdome."""
    w2=CANAL_WIDTH/2.0; ov=2.0
    if abs(y0-y1)<0.01:
        bx0,bx1=min(x0,x1)-ov,max(x0,x1)+ov; by0,by1=y0-w2,y0+w2
    else:
        bx0,bx1=x0-w2,x0+w2; by0,by1=min(y0,y1)-ov,max(y0,y1)+ov
    return make_box_cutter(name,bx0,by0,-0.1,bx1-bx0,by1-by0,CANAL_DEPTH+0.1)

def make_canal_with_caps_cutter(name, x0, y0, x1, y1, cap0, cap1,
                                  width=CANAL_WIDTH, depth=CANAL_DEPTH):
    """v97: one watertight cutter per canal segment — straight sides,
    with an optional semicircular cap built into the SAME outline at
    either end, instead of cutting a plain box and separately
    boolean-unioning a circle onto it afterward. There's no seam
    between 'box' and 'circle' for the solver to trip on here, because
    the cap curve and the straight walls are the same continuous
    polygon from the start — this is what replaces the old
    make_canal_cutter + make_fillet_cutter(cap) combination for ends
    that need rounding.
    cap0/cap1: whether the (x0,y0)/(x1,y1) end gets a semicircle. The
    non-capped case still gets the usual small overlap extension so it
    merges cleanly into whatever's there (junction, cavity, seam)."""
    w2 = width/2.0
    L = math.hypot(x1-x0, y1-y0)
    if L < 0.01:
        return make_box_cutter(name, x0-w2, y0-w2, -0.1, width, width, depth+0.1)
    ux, uy = (x1-x0)/L, (y1-y0)/L     # unit vector along the segment
    nx, ny = -uy, ux                  # unit normal (perpendicular)
    ov = 2.0

    s0 = 0.0 if cap0 else -ov
    s1 = L   if cap1 else  L+ov

    def P(s, t):
        return (x0+ux*s+nx*w2*t, y0+uy*s+ny*w2*t)

    pts = [P(s0, 1), P(s1, 1)]
    if cap1:
        a0 = math.atan2(ny, nx)
        for i in range(1, 16):
            a = a0 - math.pi*i/16
            pts.append((x1 + w2*math.cos(a), y1 + w2*math.sin(a)))
    pts.append(P(s1, -1)); pts.append(P(s0, -1))
    if cap0:
        a0 = math.atan2(-ny, -nx)
        for i in range(1, 16):
            a = a0 - math.pi*i/16
            pts.append((x0 + w2*math.cos(a), y0 + w2*math.sin(a)))

    # v98 fix: the traversal above builds the outline CLOCKWISE, but
    # every other cutter in this script (the circular ones especially,
    # via increasing-angle = CCW point generation) assumes
    # counter-clockwise winding for outward-facing normals. That
    # mismatch flipped this cutter's faces — which explains both
    # symptoms at once: a boolean difference with inverted normals can
    # fail to remove material at all (R07's canal vanishing) and can
    # also produce wrong/extra geometry where it shouldn't (the
    # unexpected tall protrusion). Reversing here matches the
    # established convention.
    pts.reverse()

    mesh=bpy.data.meshes.new(name+"_mesh"); obj=bpy.data.objects.new(name,mesh)
    bpy.context.collection.objects.link(obj)
    bm=bmesh.new()
    z0,z1=-0.1, depth+0.1
    bv=[bm.verts.new((px,py,z0)) for px,py in pts]
    tv=[bm.verts.new((px,py,z1)) for px,py in pts]
    n=len(pts)
    for i in range(n):
        j=(i+1)%n
        bm.faces.new([bv[i],bv[j],tv[j],tv[i]])
    bm.faces.new(list(reversed(bv))); bm.faces.new(tv)
    bm.normal_update(); bm.to_mesh(mesh); bm.free(); mesh.validate()
    return obj

def make_fillet_cutter(name, x, y, radius=CANAL_FILLET_RADIUS):
    """v91: a vertical cylinder centered on a canal junction, cut to
    the same z-range as the canals themselves. A plain circle naturally
    rounds whichever inside corners meet at that point — works the
    same whether it's an L-bend, a T-junction, or a full cross, with
    no need to work out exactly which quadrant is concave."""
    mesh=bpy.data.meshes.new(name+"_mesh"); obj=bpy.data.objects.new(name,mesh)
    bpy.context.collection.objects.link(obj)
    bm=bmesh.new(); segs=32
    z0,z1=-0.1, CANAL_DEPTH+0.1
    bv,tv=[],[]
    for i in range(segs):
        a=2*math.pi*i/segs
        xo=radius*math.cos(a); yo=radius*math.sin(a)
        bv.append(bm.verts.new((xo,yo,z0))); tv.append(bm.verts.new((xo,yo,z1)))
    for i in range(segs):
        j=(i+1)%segs; bm.faces.new([bv[i],bv[j],tv[j],tv[i]])
    bm.faces.new(list(reversed(bv))); bm.faces.new(tv)
    bm.normal_update(); bm.to_mesh(mesh); bm.free(); mesh.validate()
    obj.location=Vector((x,y,0.0))
    return obj

def apply_transforms(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True); bpy.context.view_layer.objects.active=obj
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)

def apply_canal_fillets(left_obj, right_obj):
    """v91: round the inside corners of the canal network at every
    junction in CANAL_JUNCTIONS — deliberately skipping the one that
    sits on the L/R seam, so the two halves still mate flush there.
    Run pre-dome, same stage as the straight canal cuts, since it's
    the same flat, simple geometry."""
    for x,y,half in CANAL_JUNCTIONS:
        target = left_obj if half=='L' else right_obj
        cutter = make_fillet_cutter(f"Fillet_{half}_{x:.0f}_{y:.0f}", x, y)
        apply_transforms(cutter)
        safe_cut(f"{half} canal fillet ({x:.0f},{y:.0f})", target, cutter, primary='EXACT')
        bpy.data.objects.remove(cutter, do_unlink=True)

# v97: apply_canal_caps retired — see make_canal_with_caps_cutter and
# the cap0/cap1 fields now built into CANAL_SEGMENTS above. Caps are
# cut as part of the same single mesh as their canal, not as a
# separate boolean step anymore.

# v97: apply_r07_cap_postdome retired — its cap is now built directly
# into apply_r07_canal_postdome's own cutter (cap0=True), same as
# every other capped canal segment. No more separate nudge-to-match
# bookkeeping between two cuts that need to stay aligned with each
# other.

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

def duplicate_obj(obj, name):
    """v85: cheap disposable copy used to try a cut without risking the
    real mesh — only commit if the result turns out clean."""
    new_data = obj.data.copy()
    new_obj = bpy.data.objects.new(name, new_data)
    new_obj.matrix_world = obj.matrix_world.copy()
    bpy.context.collection.objects.link(new_obj)
    return new_obj

def try_cut_on_copy(target, cutter, solver):
    """v85: duplicate target, attempt the boolean on the COPY only,
    measure how much manifold damage (if any) it introduced relative
    to target's current state. Returns (ok, delta_nonmanifold,
    delta_zero_area, dup_object_or_None). Caller decides whether to
    keep it."""
    nm0, za0 = report_manifold_stats(target)
    dup = duplicate_obj(target, target.name + "_TRY")
    ok = do_diff(dup, cutter, solver=solver)
    if not ok:
        bpy.data.objects.remove(dup, do_unlink=True)
        return False, None, None, None
    nm1, za1 = report_manifold_stats(dup)
    return True, nm1 - nm0, za1 - za0, dup

def safe_cut(label, target, cutter, primary='EXACT'):
    """v85: 'try before you commit'. Attempts `primary` solver on a
    disposable copy; if that copy comes out manifold-clean, its mesh
    data replaces target's and we're done. If not, tries the other
    solver on a fresh copy too, and keeps whichever of the two
    candidates is cleanest (preferring `primary` on a tie). This is
    what catches cases like L01/L06's pins, where a solver applies
    without raising an exception but still leaves real non-manifold
    edges behind — that result is now simply never committed if a
    cleaner alternative exists."""
    alt = 'FLOAT' if primary == 'EXACT' else 'EXACT'
    ok1, dn1, dz1, dup1 = try_cut_on_copy(target, cutter, primary)

    if ok1 and dn1 == 0 and dz1 == 0:
        target.data = dup1.data
        bpy.data.objects.remove(dup1, do_unlink=True)
        print(f"  {label} ✓ ({primary})")
        return True

    ok2, dn2, dz2, dup2 = try_cut_on_copy(target, cutter, alt)

    candidates = []
    if ok1: candidates.append((dn1 + dz1, primary, dup1))
    if ok2: candidates.append((dn2 + dz2, alt, dup2))

    if not candidates:
        print(f"  {label} ✗ FAILED — material NOT removed (both solvers failed)")
        FAILURES.append((label, "boolean failed (both solvers)"))
        return False

    candidates.sort(key=lambda c: c[0])
    best_score, best_solver, best_dup = candidates[0]
    target.data = best_dup.data

    for _, _, d in candidates:
        if d is not best_dup:
            bpy.data.objects.remove(d, do_unlink=True)
    bpy.data.objects.remove(best_dup, do_unlink=True)

    if best_score <= 0:
        # v94 fix: a score of exactly 0 means clean; a NEGATIVE score
        # means this cut's baseline already had leftover non-manifold
        # edges from something earlier, and this cut happened to
        # absorb/fix some of them — that's an improvement, not damage.
        # The old `== 0` check mis-reported negative scores as "N
        # manifold issues" when N was actually negative.
        loser = primary if best_solver == alt else alt
        print(f"  {label} ✓ ({best_solver}) — {loser} left damage, used {best_solver} instead")
    else:
        print(f"  {label} ✓ ({best_solver}) — ⚠ cleanest available still has {best_score} manifold issue(s)")
        FAILURES.append((label, f"cleanest available result still has {best_score} manifold issues ({best_solver})"))
    return True

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

def report_manifold_stats(obj):
    """v83: count non-manifold edges and near-zero-area faces directly,
    so 'is this object actually clean' is a number instead of a guess.
    A non-manifold edge is one that isn't shared by exactly 2 faces —
    the signature of an overlapping/duplicate-skin problem like the
    striped look seen in the slicer. Near-zero-area faces are the
    classic FLOAT-boolean tangent-cut leftovers."""
    bm=bmesh.new(); bm.from_mesh(obj.data); bm.normal_update()
    nonmanifold = sum(1 for e in bm.edges if not e.is_manifold)
    zero_area   = sum(1 for f in bm.faces if f.calc_area() < 1e-5)
    bm.free()
    return nonmanifold, zero_area

_R07_CANAL_IDX = 6  # CANAL_SEGMENTS[6] = (0.0, y0-_wo, 0.0, y1-_wo) — R07 vertical rise

def apply_canals(solid_obj, half_char):
    """EXACT canal cuts on flat plate — simple axis-aligned box × flat surface.
    R07's canal (index 6, x=0mm through tile center) is deferred to post-dome
    step for the right half to avoid EXACT z-drift issues at cx=0.
    v85: each cut now goes through safe_cut — tried on a disposable
    copy first, only committed if the result is manifold-clean.
    v97: cap0/cap1 (now part of each CANAL_SEGMENTS entry) build any
    needed rounded end directly into the cutter's own outline — see
    make_canal_with_caps_cutter."""
    xmin,xmax,ymin,ymax=get_bbox(solid_obj)
    for si,(sx0,sy0,sx1,sy1,cap0,cap1) in enumerate(CANAL_SEGMENTS):
        if half_char == 'R' and si == _R07_CANAL_IDX:
            print(f"  R canal[{si}] R07 → deferred to post-dome")
            continue
        clipped=clip_segment(sx0,sy0,sx1,sy1,xmin,xmax,ymin,ymax,margin=3.0)
        if clipped is None: continue
        nx0,ny0,nx1,ny1=clipped
        if abs(nx0-nx1)<0.5 and abs(ny0-ny1)<0.5: continue
        canal=make_canal_with_caps_cutter(f"Canal_{half_char}_{si}",nx0,ny0,nx1,ny1,cap0,cap1)
        apply_transforms(canal)
        safe_cut(f"{half_char} canal[{si}]", solid_obj, canal, primary='EXACT')
        bpy.data.objects.remove(canal,do_unlink=True)

def apply_r07_canal_postdome(right_obj):
    """Apply R07 vertical canal AFTER dome displacement (deferred to
    avoid the EXACT z-drift that breaks dome-lift detection when this
    cut happens pre-dome at cx=0 — see _R07_CANAL_IDX above).
    v93: rebuilt to match every other canal exactly — same depth as
    every other canal, centered on R07's own hole at x=0.
    v94: added a small nudge off dead-center — turned out not to be
    the actual cause (same 11 issues persisted regardless), but kept
    as cheap extra robustness.
    v97/v98: tried the unified single-mesh capsule cutter (with the
    cap built in) here too — made things WORSE (26 manifold issues,
    up from 11), even though that same cutter works perfectly for
    every OTHER capped canal (L00,L01,L02,L04,L06,R01,R04,R06,R08 all
    report zero issues with it). The common thread isn't the cutter
    shape — it's that R07 is the ONLY canal cut post-dome, against a
    far more complex, irregularly-triangulated surface than every
    other canal gets (those are all cut on the flat plate, before the
    dome even exists). More cutter complexity is the wrong direction
    against a harder target.
    v99 fix: back to the proven simpler two-cut approach for this one
    special case — a plain box (no cap baked in) here, then a
    separate circle for the cap right after (see apply_r07_cap_postdome).
    This combination measured zero failures back when it was last used
    (right after the v95 reorder fix) — keeping the unified cutter for
    every other (pre-dome) canal, where it's provably the better fit."""
    R07_X_NUDGE = 0.4   # mm, off dead-center — cheap extra robustness,
                         # kept from v94 even though it wasn't the fix
    sx0,sy0,sx1,sy1,cap0,cap1 = CANAL_SEGMENTS[_R07_CANAL_IDX]
    xmin,xmax,ymin,ymax = get_bbox(right_obj)
    clipped = clip_segment(sx0,sy0,sx1,sy1,xmin,xmax,ymin,ymax,margin=3.0)
    if clipped is None:
        print("  R07 canal post-dome: nothing to cut (clipped out)"); return
    nx0,ny0,nx1,ny1 = clipped
    if abs(nx0-nx1)<0.5 and abs(ny0-ny1)<0.5:
        print("  R07 canal post-dome: segment too short"); return
    nx0 += R07_X_NUDGE; nx1 += R07_X_NUDGE

    canal = make_canal_cutter("Canal_R07_postdome", nx0, ny0, nx1, ny1)
    apply_transforms(canal)
    safe_cut("R07 canal (post-dome, nudged 0.4mm, plain box)", right_obj, canal, primary='EXACT')
    bpy.data.objects.remove(canal, do_unlink=True)

    if cap0:
        cap_x, cap_y = nx0, ny0   # the wire-hole end, using the same
                                   # (clipped, nudged) coordinates the
                                   # canal cut itself just used
        cap = make_fillet_cutter("Cap_R07_postdome", cap_x, cap_y, radius=CANAL_WIDTH/2.0)
        apply_transforms(cap)
        safe_cut("R07 canal cap (post-dome, separate)", right_obj, cap, primary='EXACT')
        bpy.data.objects.remove(cap, do_unlink=True)

def apply_tile_cuts(solid_obj, tag, half_char, tile_idx, cx, cy):
    """Post-dome cuts:
    - Cup / wire: FLOAT preferred (dome surface is complex triangulation)
    - Pin holes: EXACT preferred (seam walls are flat vertical rectangles)
    Cavity applied separately after all tile cuts.
    v85: every cut goes through safe_cut, which only commits a result
    if it's manifold-clean — this is what fixed L01/L06's pins without
    needing per-tile PIN_Z tuning."""
    cup=make_cup_cutter(f"Cut_{tag}",cx,cy)
    apply_transforms(cup)
    safe_cut(f"{tag} cup", solid_obj, cup, primary='FLOAT')
    bpy.data.objects.remove(cup,do_unlink=True)

    wire=make_wire_hole_cutter(f"Wire_{tag}",cx,cy)
    apply_transforms(wire)
    safe_cut(f"{tag} wire", solid_obj, wire, primary='FLOAT')
    bpy.data.objects.remove(wire,do_unlink=True)

    key=(half_char,tile_idx)
    if key in PIN_ASSIGNMENTS:
        fside,dirn,lbl=PIN_ASSIGNMENTS[key]
        face_x=cx+cos30*S if fside=='R' else cx-cos30*S
        r=PIN_RADIUS+PIN_CLEARANCE
        pin_z=PIN_Z_OVERRIDES.get(lbl, PIN_Z)   # v86: per-pair override
        hole=make_hole_cutter(f"Hole_{tag}",face_x,cy,pin_z,dirn,PIN_DEPTH,r)
        apply_transforms(hole)
        safe_cut(f"{tag} {lbl} pin (z={pin_z:.0f})", solid_obj, hole, primary='EXACT')
        bpy.data.objects.remove(hole,do_unlink=True)

def apply_cavity(solid_obj):
    """Teensy cavity — deep pocket into dome (CAVITY_H_SAFE ≈ 30mm).
    Uses FLOAT: EXACT creates a fully enclosed void (0 shell) when the
    cavity ceiling doesn't pierce the bottom face cleanly."""
    cav=make_box_cutter("Cavity_R",
                        CAVITY_X_OFFSET, -CAVITY_D/2.0, -2.0,
                        CAVITY_W, CAVITY_D, CAVITY_H_SAFE+2.0)
    apply_transforms(cav)
    safe_cut("Teensy cavity", solid_obj, cav, primary='FLOAT')
    bpy.data.objects.remove(cav,do_unlink=True)

def add_tile_label(label,cx,cy):
    dz=dome_z(cx,cy)
    bpy.ops.object.text_add(location=(cx,cy,dz+PLATE_H+1.0))
    txt=bpy.context.active_object; txt.name=f"TileNum_{label}"
    txt.data.body=label; txt.data.size=8.0
    txt.data.align_x='CENTER'; txt.data.align_y='CENTER'
    return txt

def add_bottom_label(label,cx,cy):
    """Floating, UNPRINTED reference text in the Blender viewport only
    (never exported — useful for quickly identifying a tile while
    spinning the model around). See add_bottom_engraving() below for
    the real, printable version."""
    bpy.ops.object.text_add(location=(cx,cy,-1.0))
    txt=bpy.context.active_object; txt.name=f"TileNum_B_{label}"
    txt.data.body=label; txt.data.size=8.0
    txt.data.align_x='CENTER'; txt.data.align_y='CENTER'
    txt.rotation_euler=(math.pi,0,0)
    return txt

def make_text_cutter(label, cx, cy, depth=ENGRAVE_DEPTH, size=ENGRAVE_SIZE):
    """v87: builds an actual solid cutter for the given text, used to
    boolean-engrave it into the bottom (z=0) face. The cutter is built
    flat at the origin, extruded into a real prism, then moved into
    place — same general approach as every other cutter in this
    script. It straddles z=0 by an extra 0.5mm on the outside so the
    boolean never runs edge-on along an existing flat face (the same
    lesson learned from the L01/L06 pin issue and the R07 seam fix)."""
    bpy.ops.object.text_add(location=(0,0,0))
    txt = bpy.context.active_object
    txt.data.body = label
    txt.data.size = size
    txt.data.align_x = 'CENTER'; txt.data.align_y = 'CENTER'
    if MIRROR_BOTTOM_TEXT:
        txt.scale.x = -1.0
    bpy.ops.object.select_all(action='DESELECT')
    txt.select_set(True); bpy.context.view_layer.objects.active = txt
    bpy.ops.object.convert(target='MESH')
    mesh_obj = bpy.context.active_object

    # Extrude the flat glyph mesh downward into a solid prism.
    bm = bmesh.new()
    bm.from_mesh(mesh_obj.data)
    faces = bm.faces[:]
    ret = bmesh.ops.extrude_face_region(bm, geom=faces)
    new_verts = [v for v in ret['geom'] if isinstance(v, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0,0,-(depth+0.5)), verts=new_verts)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.normal_update(); bm.to_mesh(mesh_obj.data); bm.free()
    mesh_obj.data.update()

    # v88 FIX: the cutter must straddle world z=0 (the bottom face) to
    # actually carve the surface — not sit somewhere inside the solid.
    # After the extrude above, local z spans [-(depth+0.5), 0]. The
    # 180°-about-X rotation negates z, folding that to a rotated range
    # of [0, depth+0.5] (always starting at 0, regardless of depth).
    # Adding location.z = -0.5 shifts that to world z = [-0.5, depth]
    # — 0.5mm poking harmlessly below the part, `depth` mm recessed up
    # into the material. (v87 mistakenly used location.z = depth here,
    # which shifted the whole cutter to world z = [depth, 2*depth+0.5]
    # — entirely above the surface, carving an invisible, fully
    # enclosed internal void instead of an actual surface recess.)
    mesh_obj.rotation_euler = (math.pi, 0, 0)
    mesh_obj.location = (cx, cy, -0.5)
    bpy.ops.object.select_all(action='DESELECT')
    mesh_obj.select_set(True); bpy.context.view_layer.objects.active = mesh_obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return mesh_obj

def add_bottom_engraving(solid_obj, tag, cx, cy):
    """v87: the real, printable version of the bottom tile number —
    boolean-subtracted into the actual mesh as a shallow recess, so it
    shows up when sliced and printed. Tiles in BOTTOM_LABEL_OFFSET get
    shifted sideways off their canal trunk first."""
    ox, oy = BOTTOM_LABEL_OFFSET.get(tag, (0.0, 0.0))
    cutter = make_text_cutter(tag, cx+ox, cy+oy)
    safe_cut(f"{tag} bottom engrave", solid_obj, cutter, primary='FLOAT')
    bpy.data.objects.remove(cutter, do_unlink=True)

def add_r00_cable_port(right_obj):
    """v90: dedicated straight 10mm port from outside R00's tile,
    bored along Y, directly to the Teensy cavity — independent of the
    sensor wire-hole shaft (explicit request: a separate route).
    Z is centered on HALF THE MINIMUM available wall height along the
    whole path, not just at the entry point — found by sampling
    dome_z, not assumed. That minimum almost always occurs right at
    the entry (farthest from the dome center = thinnest cross
    section), so sizing for it guarantees the bore stays fully inside
    material everywhere along its length, even though the dome height
    varies a lot between R00's edge and the cavity."""
    R00_CY = 100.0  # R00's own tile center y, from the grid
    y_outer = R00_CY + S + 10.0          # comfortably outside R00's tip
    y_inner = (CAVITY_D / 2.0) - 10.0    # 10mm past the cavity's near
                                          # edge — guarantees the bore
                                          # actually merges with the
                                          # cavity void instead of
                                          # leaving a thin uncut wall

    samples = 40
    heights = [PLATE_H + dome_z(CABLE_PORT_X, y_outer + (y_inner-y_outer)*i/(samples-1))
               for i in range(samples)]
    min_h = min(heights)
    hole_z = min_h / 2.0
    print(f"  R00 cable port: path height {min_h:.1f}..{max(heights):.1f}mm along "
          f"x={CABLE_PORT_X:.0f}, centering bore at z={hole_z:.1f}mm")

    cutter = make_hole_cutter_y("Hole_R00_Port", CABLE_PORT_X, y_outer, y_inner,
                                 hole_z, CABLE_PORT_R)
    apply_transforms(cutter)
    safe_cut(f"R00 cable port ({CABLE_PORT_DIA:.0f}mm, z={hole_z:.0f})",
             right_obj, cutter, primary='FLOAT')
    bpy.data.objects.remove(cutter, do_unlink=True)

# ============================================================
# BUILD SEQUENCE
# ============================================================

print("\nStep 1: Build flat hex plates (solid-first, no interior walls)...")
left_obj  = make_flat_hex_solid(left_grid,  "SensorBase_L")
right_obj = make_flat_hex_solid(right_grid, "SensorBase_R")

print("\nStep 2: Cut canals into flat plates (EXACT on simple geometry)...")
apply_canals(left_obj,  'L')
apply_canals(right_obj, 'R')

print("\nStep 2b: Round canal junction corners (skipping the L/R seam joint)...")
apply_canal_fillets(left_obj, right_obj)
# v97: dead-end caps are now built directly into apply_canals' own
# cutters via cap0/cap1 — no separate "Step 2c" pass needed anymore.

print("\nStep 3: Add dome displacement via face normals (R07-safe)...")
add_dome_to_top(left_obj)
add_dome_to_top(right_obj)

print("\nStep 3b: R07 vertical canal — post-dome, BEFORE any tile's cup/wire/pin...")
apply_r07_canal_postdome(right_obj)

print("\nStep 4: Cut cups / wire holes / pin holes (EXACT post-dome)...")
for i,(cx,cy) in enumerate(left_grid):
    tag=f"L{i:02d}"
    apply_tile_cuts(left_obj,tag,'L',i,cx,cy)
    add_tile_label(tag,cx,cy); add_bottom_label(tag,cx,cy)
    add_bottom_engraving(left_obj,tag,cx,cy)
for i,(cx,cy) in enumerate(right_grid):
    tag=f"R{i:02d}"
    apply_tile_cuts(right_obj,tag,'R',i,cx,cy)
    add_tile_label(tag,cx,cy); add_bottom_label(tag,cx,cy)
    add_bottom_engraving(right_obj,tag,cx,cy)

print("\nStep 5: Teensy cavity (FLOAT, deep into dome structure)...")
apply_cavity(right_obj)

print("\nStep 5b: R00 cable port (10mm, straight to cavity, separate from wire hole)...")
add_r00_cable_port(right_obj)

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

    nm_before, za_before = report_manifold_stats(obj)

    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    # Pass 1: tight merge (catches exact duplicate verts from shared corners)
    bpy.ops.mesh.remove_doubles(threshold=0.001)
    # Pass 2 (v83): looser merge — catches accumulated FLOAT-boolean drift
    # across many sequential cuts (8 tiles × 2 cuts on the left half).
    # 0.02mm is far below any real feature size here (smallest is the
    # 5mm wire hole / 0.2mm pin clearance), so this can't eat real geometry.
    bpy.ops.mesh.remove_doubles(threshold=0.02)
    # v83: dissolve near-zero-area faces — the classic leftover from a
    # FLOAT boolean cutting tangent to the surface instead of cleanly
    # through it. These are the "extra skin" causing the striped look.
    bpy.ops.mesh.dissolve_degenerate(threshold=0.001)
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode='OBJECT')

    nm_after, za_after = report_manifold_stats(obj)

    v=len(obj.data.vertices); f=len(obj.data.polygons)
    bb=[obj.matrix_world@Vector(c) for c in obj.bound_box]
    xs=[p.x for p in bb]; ys=[p.y for p in bb]
    w,d=max(xs)-min(xs),max(ys)-min(ys)
    print(f"  {obj.name}: {v}v {f}f {w:.0f}×{d:.0f}mm {'✓' if w<=340 and d<=340 else '⚠'}")
    print(f"    non-manifold edges: {nm_before}→{nm_after}   "
          f"near-zero-area faces: {za_before}→{za_after}")
    if nm_after > 0 or za_after > 0:
        print(f"    ⚠ {obj.name} still has leftover non-manifold/degenerate geometry —")
        print(f"      this is consistent with the striped/double-skin look in the slicer.")
        FAILURES.append((f"{obj.name} mesh cleanup",
                          f"{nm_after} non-manifold edges, {za_after} near-zero-area faces remain"))

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