"""
Диван и кресло «1 в 1» с моделями Meshy (props/MeshyFurniture/Sofa, Armchair), построенные заново
из чистой геометрии и разделённые на детали. Размеры сняты с исходных моделей. Без текстур.

Детали (P = Sofa / Armchair):
  P_Leg_FL, P_Leg_FR, P_Leg_BL, P_Leg_BR   — ножки (дерево)
  P_Base               — царга под сиденьем (дерево)
  P_Seat               — подушка сиденья (ткань)
  P_Arm_L, P_Arm_R     — подлокотники-валики (ткань)
  P_ArmFront_L, _R     — деревянная стойка/накладка спереди подлокотника с завитком
  P_BackFrame          — деревянная рамка спинки
  P_BackPanel          — мягкая панель спинки (у дивана — стяжка «капитоне»)
  P_BackRear           — тканевая задняя панель спинки
  Sofa_Buttons         — пуговицы стяжки (только диван)

Лицо — в -Y. Запуск: blender --background --python build_seating.py -- out_dir sofa|armchair|both
"""

import math
import os
import sys

import bpy
import bmesh
from mathutils import Matrix, Vector, noise

SPECS = {
    "sofa": dict(
        prefix="Sofa",
        legs=[((0.835, -0.255), 0.085), ((0.823, 0.268), 0.085)],   # (центр |x|, y), сечение
        leg_h=0.15, leg_flare=0.13,
        base=dict(x=0.94, y=(-0.32, 0.32), z=(0.15, 0.27), lip=(0.21, 0.24, 0.012)),
        seat=dict(x=0.735, y=(-0.30, 0.16), z=(0.27, 0.45), r=0.05),
        arm_profile=[(0.725, 0.27), (0.91, 0.27), (0.905, 0.45), (0.97, 0.47), (1.015, 0.505), (1.04, 0.55),
                     (1.046, 0.60), (1.03, 0.635), (1.005, 0.665), (0.95, 0.695), (0.88, 0.703), (0.82, 0.69),
                     (0.78, 0.66), (0.755, 0.61), (0.74, 0.55), (0.73, 0.48)],
        arm_y=(-0.30, 0.32), scroll=dict(c=(0.92, 0.585), r=0.095),
        front="plate",
        back=dict(half=[(0.80, 0.15), (0.80, 0.70), (0.76, 0.745), (0.72, 0.832), (0.68, 0.887), (0.64, 0.935),
                        (0.60, 0.975), (0.56, 1.005), (0.52, 1.02), (0.40, 1.027), (0.28, 1.023), (0.24, 1.04),
                        (0.20, 1.088), (0.16, 1.108), (0.12, 1.12), (0.06, 1.125), (0.0, 1.127)],
                  y=(0.14, 0.325), frame=0.06, tilt=0.0, pivot=(0.23, 0.15), tufted=True),   # спинка до царги
    ),
    "armchair": dict(
        prefix="Armchair",
        legs=[((0.33, -0.34), 0.075), ((0.29, 0.218), 0.08)],
        leg_h=0.21, leg_flare=0.09,
        base=dict(x=0.375, y=(-0.40, 0.29), z=(0.21, 0.33), lip=(0.22, 0.30, 0.0)),
        seat=dict(x=0.29, y=(-0.37, 0.21), z=(0.33, 0.47), r=0.05),
        arm_profile=[(0.28, 0.33), (0.375, 0.33), (0.375, 0.56), (0.405, 0.585), (0.405, 0.645), (0.39, 0.675),
                     (0.34, 0.687), (0.29, 0.675), (0.28, 0.65)],
        arm_y=(-0.42, 0.26), scroll=dict(c=(0.345, 0.625), r=0.05),
        front="post",
        back=dict(half=[(0.37, 0.21), (0.37, 0.86), (0.30, 0.995), (0.24, 1.014), (0.20, 1.03), (0.10, 1.10),
                        (0.0, 1.10)],
                  y=(0.19, 0.30), frame=0.045, tilt=13.5, pivot=(0.25, 0.33), tufted=False, rear_inset=0.01),
    ),
}
TUFT_A, TUFT_B, TUFT_D = 0.13, 0.11, 0.035

S = None          # текущая спецификация
OUT = []          # (объект, материал)


def log(*a):
    print("[seat]", *a, flush=True)


def activate(o):
    for x in bpy.context.selected_objects:
        x.select_set(False)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)


def box(bm, x, y, z):
    c = Vector(((x[0] + x[1]) / 2, (y[0] + y[1]) / 2, (z[0] + z[1]) / 2))
    s = (x[1] - x[0], y[1] - y[0], z[1] - z[0])
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(c) @ Matrix.Diagonal((*s, 1)))


def prism_xz(bm, poly, y0, y1):
    f = [bm.verts.new((x, y0, z)) for x, z in poly]
    b = [bm.verts.new((x, y1, z)) for x, z in poly]
    bm.faces.new(f)
    bm.faces.new(list(reversed(b)))
    n = len(poly)
    for i in range(n):
        bm.faces.new((f[i], f[(i + 1) % n], b[(i + 1) % n], b[i]))


def prism_yz(bm, poly, x0, x1):
    a = [bm.verts.new((x0, y, z)) for y, z in poly]
    b = [bm.verts.new((x1, y, z)) for y, z in poly]
    bm.faces.new(a)
    bm.faces.new(list(reversed(b)))
    n = len(poly)
    for i in range(n):
        bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]))


def tube(bm, pts, r, segs=8):
    pts = [Vector(p) for p in pts]
    rings = []
    for i, p in enumerate(pts):
        t = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
        nr = Vector((0, 1, 0)) - Vector((0, 1, 0)).dot(t) * t
        if nr.length < 1e-4:
            nr = Vector((1, 0, 0)) - Vector((1, 0, 0)).dot(t) * t
        nr.normalize()
        bn = t.cross(nr)
        rings.append([bm.verts.new(p + nr * r * math.cos(2 * math.pi * k / segs) + bn * r * math.sin(2 * math.pi * k / segs))
                      for k in range(segs)])
    for ra, rb in zip(rings, rings[1:]):
        for k in range(segs):
            bm.faces.new((ra[k], ra[(k + 1) % segs], rb[(k + 1) % segs], rb[k]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])


def chaikin(pts, it=2, closed=True):
    for _ in range(it):
        n = len(pts)
        new = []
        for i in range(n if closed else n - 1):
            a, b = pts[i], pts[(i + 1) % n]
            new += [tuple(0.75 * u + 0.25 * v for u, v in zip(a, b)), tuple(0.25 * u + 0.75 * v for u, v in zip(a, b))]
        if not closed:
            new = [pts[0]] + new + [pts[-1]]
        pts = new
    return pts


def offset_poly(poly, d):
    n = len(poly)
    out = []
    for i in range(n):
        p0, p1, p2 = Vector(poly[i - 1]), Vector(poly[i]), Vector(poly[(i + 1) % n])
        e1, e2 = (p1 - p0).normalized(), (p2 - p1).normalized()
        n1, n2 = Vector((-e1.y, e1.x)), Vector((-e2.y, e2.x))
        bis = n1 + n2
        bis = n1 if bis.length < 1e-6 else bis.normalized()
        out.append(tuple(p1 + bis * (d / max(0.3, bis.dot(n1)))))
    area = lambda p: 0.5 * sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p)))
    return offset_poly(poly, -d) if abs(area(out)) > abs(area(poly)) else out


def inside(poly, x, z):
    c = False
    for i in range(len(poly)):
        x1, z1 = poly[i]
        x2, z2 = poly[(i + 1) % len(poly)]
        if (z1 > z) != (z2 > z) and x < (x2 - x1) * (z - z1) / (z2 - z1) + x1:
            c = not c
    return c


def make(name, bm, mat, bevel=0.0, smooth=False, M=None):
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    ngons = [f for f in bm.faces if len(f.verts) > 4]          # вогнутые n-угольники -> треугольники
    if ngons:
        bmesh.ops.triangulate(bm, faces=ngons, quad_method='BEAUTY', ngon_method='EAR_CLIP')
    if M is not None:
        bmesh.ops.transform(bm, matrix=M, verts=bm.verts)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    if bevel:
        m = o.modifiers.new("Bevel", 'BEVEL')
        m.width, m.segments, m.limit_method, m.angle_limit = bevel, 2, 'ANGLE', math.radians(35)
        m.harden_normals = True
        activate(o)
        bpy.ops.object.modifier_apply(modifier=m.name)
    for p in o.data.polygons:
        p.use_smooth = smooth
    OUT.append((o, mat))
    return o


def back_outline(half):
    right_up = list(half)                                   # от низа справа до центра сверху
    left_down = [(-x, z) for x, z in reversed(right_up[:-1])]
    return right_up + left_down


# ----------------------------------------------------------------- детали
def legs(P):
    (fx, fy), fs = S["legs"][0]
    (bx, by), bs = S["legs"][1]
    for tag, (cx, cy, s) in {"FL": (-fx, fy, fs), "FR": (fx, fy, fs), "BL": (-bx, by, bs), "BR": (bx, by, bs)}.items():
        bm = bmesh.new()
        h = S["leg_h"]
        bmesh.ops.create_cone(bm, cap_ends=True, segments=4, radius1=s * 0.55, radius2=s * 0.72, depth=h * 0.75,
                              matrix=Matrix.Translation((cx, cy, h * 0.375)) @ Matrix.Rotation(math.pi / 4, 4, 'Z'))
        box(bm, (cx - S["leg_flare"] / 2, cx + S["leg_flare"] / 2), (cy - S["leg_flare"] / 2, cy + S["leg_flare"] / 2),
            (h * 0.75, h))                                                      # капитель ножки
        box(bm, (cx - s * 0.45, cx + s * 0.45), (cy - s * 0.45, cy + s * 0.45), (0.0, 0.02))   # башмачок
        make(f"{P}_Leg_{tag}", bm, "Wood", bevel=0.004)


def base(P):
    b = S["base"]
    bm = bmesh.new()
    box(bm, (-b["x"] + 0.01, b["x"] - 0.01), b["y"], b["z"])
    z0, z1, lip = b["lip"]
    if lip:
        box(bm, (-b["x"], b["x"]), (b["y"][0] - lip, b["y"][1]), (z0, z1))      # молдинг по периметру
    make(f"{P}_Base", bm, "Wood", bevel=0.005)


def seat(P):
    s = S["seat"]
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=6, use_grid_fill=True)
    y0, y1 = s["y"]
    z0, z1 = s["z"]
    for v in bm.verts:
        u, w, h = v.co.x * 2, v.co.y * 2, v.co.z * 2
        crown = 0.015 * (1 - u * u) * (1 - w * w) if h > 0 else 0.0
        v.co = Vector((u * s["x"], (y0 + y1) / 2 + w * (y1 - y0) / 2, (z0 + z1) / 2 + h * (z1 - z0) / 2 + crown))
    bmesh.ops.bevel(bm, geom=[e for e in bm.edges if e.calc_face_angle(0) > 0.5], offset=s["r"], segments=3,
                    profile=0.6, affect='EDGES', clamp_overlap=True)
    make(f"{P}_Seat", bm, "Fabric", smooth=True)


def arms(P):
    prof = S["arm_profile"]
    y0, y1 = S["arm_y"]
    cx, cz = S["scroll"]["c"]
    r = S["scroll"]["r"]
    for side, sg in (("L", -1), ("R", 1)):
        poly = [(sg * x, z) for x, z in prof]
        if sg < 0:
            poly = list(reversed(poly))
        bm = bmesh.new()
        prism_xz(bm, chaikin(poly, 1), y0 + (0.0 if S["front"] == "plate" else 0.02), y1)
        make(f"{P}_Arm_{side}", bm, "Fabric", bevel=0.008, smooth=True)
        # спереди: дерево + завиток
        bm = bmesh.new()
        yf = y0 - 0.002
        if S["front"] == "plate":                       # диван: накладка по контуру торца
            prism_xz(bm, chaikin(poly, 1), yf - 0.02, yf + 0.004)
        else:                                           # кресло: изогнутая стойка от царги до валика
            x0, x1 = sorted((sg * 0.30, sg * 0.395))
            # S-образная стойка: передняя кромка снизу вверх, затем задняя (на 4.5 см глубже) сверху вниз
            front = [(-0.405, S["base"]["z"][0]), (-0.405, 0.33), (-0.36, 0.38), (-0.33, 0.45), (-0.33, 0.54),
                     (-0.38, 0.58)]
            post = front + [(y + 0.045, z) for y, z in reversed(front)]
            prism_yz(bm, post, x0, x1)
            bmesh.ops.create_cone(bm, cap_ends=True, segments=20, radius1=r, radius2=r, depth=0.04,
                                  matrix=Matrix.Translation((sg * cx, y0 - 0.0, cz)) @ Matrix.Rotation(math.pi / 2, 4, 'X'))
            yf = y0 - 0.02
        spiral = []
        for k in range(70):
            t = k / 69
            a = math.pi / 2 - sg * 2 * math.pi * 1.6 * t
            rr = r * 0.85 * (1 - 0.8 * t)
            spiral.append((sg * cx + rr * math.cos(a), yf - 0.02 - 0.006 * t, cz + rr * math.sin(a)))
        tube(bm, spiral, r * 0.14, segs=8)
        make(f"{P}_ArmFront_{side}", bm, "Wood", smooth=True)


def back(P):
    B = S["back"]
    outline = back_outline(B["half"])
    y0, y1 = B["y"]
    piv_y, piv_z = B["pivot"]
    M = (Matrix.Translation((0, piv_y, piv_z)) @ Matrix.Rotation(math.radians(-B["tilt"]), 4, 'X')
         @ Matrix.Translation((0, -piv_y, -piv_z)))
    inner = offset_poly(outline, B["frame"])
    # рамка: внешний контур минус внутренний (кольцо из четырёхугольников)
    bm = bmesh.new()
    n = len(outline)
    rings = []
    for (xo, zo), (xi, zi) in zip(outline, inner):
        rings.append([bm.verts.new((xo, y0 - 0.01, zo)), bm.verts.new((xi, y0 - 0.01, zi)),
                      bm.verts.new((xi, y1, zi)), bm.verts.new((xo, y1, zo))])
    for i in range(n):
        a, b = rings[i], rings[(i + 1) % n]
        for k in range(4):
            bm.faces.new((a[k], a[(k + 1) % 4], b[(k + 1) % 4], b[k]))
    make(f"{P}_BackFrame", bm, "Wood", M=M)
    # задняя тканевая панель
    bm = bmesh.new()
    prism_xz(bm, inner, y0 + 0.02, y1 - B.get("rear_inset", 0.0))
    make(f"{P}_BackRear", bm, "Fabric", M=M)
    # передняя мягкая панель (стяжка или пухлая подушка)
    panel(P, inner, y0, B["tufted"], M)


def panel(P, inner, yf, tufted, M):
    xs, zs = [p[0] for p in inner], [p[1] for p in inner]
    step = 0.0125
    x0, z0 = min(xs) - step, min(zs) - step
    nx, nz = int((max(xs) - x0) / step) + 2, int((max(zs) - z0) / step) + 2
    zb = S["seat"]["z"][1] + 0.06

    def height(x, z):
        if not tufted:
            return 0.025
        u, v = x / TUFT_A + (z - zb) / TUFT_B, x / TUFT_A - (z - zb) / TUFT_B
        return 0.006 + TUFT_D * (abs(math.sin(math.pi * u / 2)) * abs(math.sin(math.pi * v / 2))) ** 0.6

    def nearest(x, z):
        best, bd = None, 1e9
        for k in range(len(inner)):
            a, b = Vector(inner[k]), Vector(inner[(k + 1) % len(inner)])
            ab = b - a
            t = max(0.0, min(1.0, (Vector((x, z)) - a).dot(ab) / max(ab.length_squared, 1e-12)))
            q = a + ab * t
            d = (q - Vector((x, z))).length
            if d < bd:
                best, bd = q, d
        return best, bd

    ins = {(i, j): inside(inner, x0 + i * step, z0 + j * step) for i in range(nx + 1) for j in range(nz + 1)}
    bm = bmesh.new()
    grid = {}
    for i in range(nx + 1):
        for j in range(nz + 1):
            if not any(ins.get((i + a, j + b)) for a in (-1, 0, 1) for b in (-1, 0, 1)):
                continue
            x, z = x0 + i * step, z0 + j * step
            q, d = nearest(x, z)
            if not ins[(i, j)]:
                x, z, d = q.x, q.y, 0.0
            fall = min(1.0, d / 0.06) ** 0.6
            grid[(i, j)] = bm.verts.new((x, yf + 0.004 - height(x, z) * fall, z))
    for i in range(nx):
        for j in range(nz):
            q = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            if all(k in grid for k in q) and any(ins[k] for k in q):
                bm.faces.new([grid[k] for k in q])
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.002)
    make(f"{P}_BackPanel", bm, "Fabric", smooth=True, M=M)
    if tufted:
        bm = bmesh.new()
        small = offset_poly(inner, 0.035)
        for a in range(-14, 15):
            for b in range(0, 10):
                if (a + b) % 2:
                    continue
                x, z = a * TUFT_A, zb + b * TUFT_B
                if inside(small, x, z):
                    bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=0.013,
                                              matrix=Matrix.Translation((x, yf + 0.004 - 0.008, z)) @ Matrix.Diagonal((1, 0.5, 1, 1)))
        make(f"{P}_Buttons", bm, "Fabric", smooth=True, M=M)


def build(kind, out):
    global S
    S = SPECS[kind]
    OUT.clear()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    P = S["prefix"]
    legs(P)
    base(P)
    seat(P)
    arms(P)
    back(P)
    cols = {"Wood": (0.30, 0.15, 0.08), "Fabric": (0.45, 0.04, 0.06)}
    mats = {}
    for n, c in cols.items():
        m = bpy.data.materials.new(n)
        m.diffuse_color = (*c, 1)
        m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*c, 1)
        mats[n] = m
    for o, mname in OUT:
        o.data.materials.clear()
        o.data.materials.append(mats[mname])
        log(f"{o.name}: {sum(len(p.vertices) - 2 for p in o.data.polygons)} треугольников")
    os.makedirs(out, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, f"{P}.blend"))
    for o in bpy.data.objects:
        o.select_set(o.name.startswith(P + "_"))
    bpy.ops.export_scene.gltf(filepath=os.path.join(out, f"{P}.glb"), export_format='GLB', use_selection=True)
    bpy.ops.export_scene.fbx(filepath=os.path.join(out, f"{P}_Roblox.fbx"), use_selection=True,
                             axis_forward='-Z', axis_up='Y', apply_scale_options='FBX_SCALE_ALL', path_mode='STRIP')
    log(f"{P} сохранён -> {out}")


def main():
    a = sys.argv[sys.argv.index("--") + 1:]
    out = os.path.abspath(a[0])
    kinds = ["sofa", "armchair"] if (len(a) < 2 or a[1] == "both") else [a[1]]
    for k in kinds:
        build(k, os.path.join(out, k))


if __name__ == "__main__":
    main()
