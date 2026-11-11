"""
Диван «капитоне» со свитковыми подлокотниками и горбатой спинкой (по референсу, версия 2).

Состав (отдельные объекты, каждый < 20 000 треугольников — подходит для Roblox MeshPart):
  Sofa_Frame      — дерево: ножки, нижняя тяга, планка под подушкой, плоская профильная рама спинки,
                    рамки боковин (стойки + нижняя планка), кант по краю свитка подлокотника
  Sofa_Upholstery — ткань: корпус спинки (сзади обит, с бортиком), подлокотники-свитки
                    (узкие внизу, валик нависает наружу), тканевые спирали на торцах, фартук
  Sofa_Tufting    — стяжка «капитоне» (крупные пухлые ромбы, складки по диагоналям)
  Sofa_Cushion    — толстая подушка сиденья
  Sofa_Buttons    — пуговицы, обтянутые тканью

Размеры (м): ширина 2.1, глубина 0.80, высота 1.17, подлокотники 0.74, сиденье 0.53. Лицо — в -Y.

Запуск: blender --background --python build_sofa.py -- out_dir [velvet|white]
"""

import math
import os
import sys

import bpy
import bmesh
from mathutils import Matrix, Vector, noise

STYLE = "velvet"

D = 0.80                         # глубина
LEG_H = 0.13
RAIL_TOP = 0.17                  # верх нижней деревянной тяги
STRIP = (0.36, 0.40)             # деревянная планка под подушкой
CUSH = (0.40, 0.53)              # подушка сиденья
ARM_IN = 0.775                   # |x| внутренней стенки подлокотника
ROLL_C = (0.92, 0.61)            # центр валика (|x|, z)
ROLL_R = 0.13
ARM_BASE_OUT = 0.90              # |x| боковины внизу
BACK_T = 0.18
BACK_FRONT = D / 2 - BACK_T      # передняя плоскость спинки (y)
BACK_HALF = 0.76                 # полуширина спинки
# верх спинки (половина, от центра): горб, пологие «плечи», скругление к боковинам
BACK_TOP = [(0.0, 1.17), (0.08, 1.165), (0.16, 1.14), (0.23, 1.10), (0.30, 1.085), (0.50, 1.07),
            (0.66, 1.05), (0.73, 1.01), (0.76, 0.95)]
TUFT_A, TUFT_B = 0.135, 0.115    # полуразмеры ромба
TUFT_DEPTH = 0.05

PARTS = {}


def log(*a):
    print("[sofa]", *a, flush=True)


def activate(o):
    for x in bpy.context.selected_objects:
        x.select_set(False)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)


def add(bm, group):
    PARTS.setdefault(group, []).append(bm)


# ----------------------------------------------------------------- геометрические помощники
def box(bm, center, size):
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(center) @ Matrix.Diagonal((*size, 1)))


def prism_xz(bm, poly, y0, y1):
    front = [bm.verts.new((x, y0, z)) for x, z in poly]
    back = [bm.verts.new((x, y1, z)) for x, z in poly]
    bm.faces.new(front)
    bm.faces.new(list(reversed(back)))
    n = len(poly)
    for i in range(n):
        bm.faces.new((front[i], front[(i + 1) % n], back[(i + 1) % n], back[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)


def tube(bm, pts, r, segs=10, scale=(1.0, 1.0)):
    pts = [Vector(p) for p in pts]
    n = len(pts)
    rings = []
    ref = Vector((0, 1, 0))
    for i, p in enumerate(pts):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, n - 1)]
        t = (b - a).normalized()
        nr = ref - ref.dot(t) * t
        if nr.length < 1e-4:
            nr = Vector((1, 0, 0)) - Vector((1, 0, 0)).dot(t) * t
        nr.normalize()
        bn = t.cross(nr)
        rings.append([bm.verts.new(p + nr * (r * scale[0] * math.cos(2 * math.pi * k / segs)) +
                                   bn * (r * scale[1] * math.sin(2 * math.pi * k / segs))) for k in range(segs)])
    for ra, rb in zip(rings, rings[1:]):
        for k in range(segs):
            bm.faces.new((ra[k], ra[(k + 1) % segs], rb[(k + 1) % segs], rb[k]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])


def sweep_xz(bm, path, y0, profile, center):
    """Профиль [(внутрь, по Y)] протягивается вдоль ломаной path (XZ); «внутрь» — к точке center."""
    n = len(path)
    rings = []
    c = Vector(center)
    for i, p in enumerate(path):
        p = Vector(p)
        a, b = Vector(path[max(i - 1, 0)]), Vector(path[min(i + 1, n - 1)])
        t = (b - a).normalized()
        nr = Vector((-t.y, t.x))
        if nr.dot(c - p) < 0:
            nr = -nr
        rings.append([bm.verts.new((p.x + nr.x * di, y0 + dy, p.y + nr.y * di)) for di, dy in profile])
    m = len(profile)
    for ra, rb in zip(rings, rings[1:]):
        for k in range(m):
            bm.faces.new((ra[k], ra[(k + 1) % m], rb[(k + 1) % m], rb[k]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])


def chaikin(pts, it=3, closed=False):
    for _ in range(it):
        new = [] if closed else [pts[0]]
        rng = range(len(pts)) if closed else range(len(pts) - 1)
        for i in rng:
            a, b = pts[i], pts[(i + 1) % len(pts)]
            new += [tuple(0.75 * u + 0.25 * v for u, v in zip(a, b)), tuple(0.25 * u + 0.75 * v for u, v in zip(a, b))]
        if not closed:
            new.append(pts[-1])
        pts = new
    return pts


def inside(poly, x, z):
    c = False
    n = len(poly)
    for i in range(n):
        x1, z1 = poly[i]
        x2, z2 = poly[(i + 1) % n]
        if (z1 > z) != (z2 > z) and x < (x2 - x1) * (z - z1) / (z2 - z1) + x1:
            c = not c
    return c


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

    def area(p):
        return 0.5 * sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p)))
    return offset_poly(poly, -d) if abs(area(out)) > abs(area(poly)) else out


def back_top_full():
    right = BACK_TOP
    left = [(-x, z) for x, z in reversed(right[1:])]
    return left + right


# ----------------------------------------------------------------- низ
def build_base():
    fr = bmesh.new()
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * (ARM_BASE_OUT - 0.07), sy * (D / 2 - 0.08)
            bmesh.ops.create_cone(fr, cap_ends=True, segments=4, radius1=0.05, radius2=0.068, depth=LEG_H - 0.04,
                                  matrix=Matrix.Translation((x, y, 0.03 + (LEG_H - 0.04) / 2))
                                  @ Matrix.Rotation(math.pi / 4, 4, 'Z'))
            box(fr, Vector((x, y, 0.016)), (0.085, 0.085, 0.032))          # раструб-башмачок
    # нижняя тяга вокруг основания
    box(fr, Vector((0, 0, (LEG_H + RAIL_TOP) / 2)), (2 * ARM_BASE_OUT - 0.02, D - 0.04, RAIL_TOP - LEG_H))   # утоплена за рамки боковин
    # деревянная планка под подушкой (спереди, между подлокотниками)
    box(fr, Vector((0, -D / 2 + 0.03, sum(STRIP) / 2)), (2 * ARM_IN + 0.01, 0.05, STRIP[1] - STRIP[0]))
    add(fr, "Sofa_Frame")
    # фартук из ткани между тягой и планкой
    up = bmesh.new()
    box(up, Vector((0, 0.0, (RAIL_TOP + STRIP[0]) / 2)), (2 * ARM_IN + 0.01, D - 0.07, STRIP[0] - RAIL_TOP))
    add(up, "Sofa_Upholstery")


def build_cushion():
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=7, use_grid_fill=True)
    y0, y1 = -D / 2 + 0.005, BACK_FRONT + 0.01
    for v in bm.verts:
        u, w, h = v.co.x * 2, v.co.y * 2, v.co.z * 2
        crown = 0.02 * (1 - u * u) * (1 - w * w) if h > 0 else 0.0
        bulge = 0.012 * (1 - h * h) if w < -0.9 else 0.0                     # пухлый передний край
        v.co = Vector((u * (ARM_IN - 0.005), (y0 + y1) / 2 + w * (y1 - y0) / 2 - bulge,
                       sum(CUSH) / 2 + h * (CUSH[1] - CUSH[0]) / 2 + crown))
    bmesh.ops.bevel(bm, geom=[e for e in bm.edges if e.calc_face_angle(0) > 0.5], offset=0.035, segments=3,
                    profile=0.6, affect='EDGES', clamp_overlap=True)
    add(bm, "Sofa_Cushion")


# ----------------------------------------------------------------- подлокотники-свитки
def arm_profile():
    """Сечение подлокотника (u = |x|, z): узкая боковина внизу, валик нависает наружу."""
    xc, zc = ROLL_C
    pts = [(ARM_IN, RAIL_TOP), (ARM_IN, zc - 0.02)]
    for k in range(17):                                  # дуга валика: изнутри через верх наружу и вниз
        a = math.radians(185 - 245 * k / 16)
        pts.append((xc + ROLL_R * math.cos(a), zc + ROLL_R * math.sin(a)))
    pts += [(ARM_BASE_OUT + 0.035, 0.44), (ARM_BASE_OUT + 0.005, 0.38), (ARM_BASE_OUT, RAIL_TOP)]
    return pts


def build_arms():
    prof = arm_profile()
    xc, zc = ROLL_C
    y_f, y_b = -D / 2 + 0.01, D / 2 - 0.01
    for s in (-1, 1):
        poly = [(s * u, z) for u, z in prof]
        if s > 0:
            poly = list(reversed(poly))
        up = bmesh.new()
        prism_xz(up, poly, y_f, y_b)
        for v in up.verts:
            v.co.z += 0.002 * noise.noise(v.co * 7)
        # тканевая спираль на торце валика + центральная пуговица
        spiral = []
        for k in range(80):
            t = k / 79
            ang = math.radians(90) - s * 2 * math.pi * 1.55 * t
            r = ROLL_R * 0.86 * (1 - 0.8 * t)
            spiral.append((s * (xc + r * math.cos(ang) * s), y_f - 0.012 - 0.01 * t, zc + r * math.sin(ang)))
        tube(up, spiral, 0.024, segs=10, scale=(1.0, 0.8))
        bmesh.ops.create_uvsphere(up, u_segments=12, v_segments=8, radius=0.03,
                                  matrix=Matrix.Translation((s * xc, y_f - 0.03, zc)) @ Matrix.Diagonal((1, 0.6, 1, 1)))
        add(up, "Sofa_Upholstery")

        fr = bmesh.new()
        # деревянный кант по наружному краю торца: от верха валика вниз по боковине
        edge = [(s * u, z) for u, z in prof[9:]]
        path = [(x - s * 0.012, z) for x, z in edge]
        sweep_xz(fr, chaikin(path, 2), y_f - 0.004,
                 [(0.0, 0.0), (0.0, -0.02), (0.012, -0.026), (0.03, -0.026), (0.034, 0.0)], (0, 0.45))
        # рамка боковины: стойки спереди и сзади + нижняя планка
        xo = s * (ARM_BASE_OUT + 0.012)
        for y in (y_f + 0.045, y_b - 0.045):
            box(fr, Vector((xo, y, (RAIL_TOP + 0.47) / 2)), (0.03, 0.09, 0.47 - RAIL_TOP))
        span = y_b - y_f - 2 * 0.09                  # планки — между стойками, без перекрытия граней
        box(fr, Vector((xo - s * 0.002, 0, RAIL_TOP + 0.035)), (0.026, span, 0.07))
        box(fr, Vector((xo - s * 0.002, 0, 0.452)), (0.022, span, 0.035))
        add(fr, "Sofa_Frame")


# ----------------------------------------------------------------- спинка
def build_back():
    top = back_top_full()
    outline = [(-BACK_HALF, RAIL_TOP)] + top + [(BACK_HALF, RAIL_TOP)]
    yf, yb = BACK_FRONT, D / 2 - 0.01
    up = bmesh.new()
    prism_xz(up, outline, yf + 0.02, yb)
    # бортик по контуру задней стороны
    zb = RAIL_TOP + 0.07
    rim_top = [(x * 0.935, z - 0.055) for x, z in top]
    xl, xr = rim_top[0][0], rim_top[-1][0]
    rim = ([(xl + 0.05, zb), (xl, zb), (xl, zb + 0.05)] + rim_top
           + [(xr, zb + 0.05), (xr, zb), (xr - 0.05, zb)])   # опорные точки у углов — углы скругляются плотно
    rim = chaikin(rim + [rim[0]], 2)
    tube(up, [(x, yb + 0.006, z) for x, z in rim], 0.014, segs=6)
    add(up, "Sofa_Upholstery")

    # плоская профильная деревянная рама: по верху и вниз по бокам до подлокотников
    path = [(-BACK_HALF, ROLL_C[1] + 0.05)] + top + [(BACK_HALF, ROLL_C[1] + 0.05)]
    path = chaikin(path, 3)
    fr = bmesh.new()
    sweep_xz(fr, path, yf + 0.03,
             [(-0.008, 0.0), (-0.008, -0.05), (0.004, -0.064), (0.05, -0.064), (0.064, -0.052), (0.068, 0.0)],
             (0, 0.7))
    add(fr, "Sofa_Frame")

    # стяжка внутри рамы
    inner_top = [(x * 0.96, z - 0.075) for x, z in top]
    inner = [(-BACK_HALF + 0.06, CUSH[1] - 0.02)] + inner_top + [(BACK_HALF - 0.06, CUSH[1] - 0.02)]
    inner = chaikin(inner + [inner[0]], 2, closed=False)[:-1]
    build_tufting(inner, yf)


def build_tufting(inner, yf):
    xs, zs = [p[0] for p in inner], [p[1] for p in inner]
    step = 0.0125
    x0, z0 = min(xs) - step, min(zs) - step
    nx, nz = int((max(xs) - x0) / step) + 2, int((max(zs) - z0) / step) + 2
    zb = CUSH[1] + 0.06

    def height(x, z):
        u = x / TUFT_A + (z - zb) / TUFT_B
        v = x / TUFT_A - (z - zb) / TUFT_B
        return TUFT_DEPTH * (abs(math.sin(math.pi * u / 2)) * abs(math.sin(math.pi * v / 2))) ** 0.6

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
            q, dist = nearest(x, z)
            if not ins[(i, j)]:
                x, z, dist = q.x, q.y, 0.0
            fall = min(1.0, dist / 0.07) ** 0.6
            wr = 0.003 * noise.noise(Vector((x * 9, z * 9, 0.5)))
            grid[(i, j)] = bm.verts.new((x, yf + 0.02 - (0.01 + height(x, z) + wr) * fall, z))
    for i in range(nx):
        for j in range(nz):
            q = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            if all(k in grid for k in q) and any(ins[k] for k in q):
                bm.faces.new([grid[k] for k in q])
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.002)
    bmesh.ops.dissolve_degenerate(bm, dist=0.0005, edges=bm.edges)
    add(bm, "Sofa_Tufting")
    # пуговицы в узлах (утоплены в складки)
    bb = bmesh.new()
    count = 0
    inner_small = offset_poly(inner, 0.04)
    for a in range(-12, 13):
        for b in range(0, 10):
            if (a + b) % 2:
                continue
            x, z = a * TUFT_A, zb + b * TUFT_B
            if inside(inner_small, x, z):
                bmesh.ops.create_uvsphere(bb, u_segments=10, v_segments=6, radius=0.016,
                                          matrix=Matrix.Translation((x, yf + 0.02 - 0.01 - 0.002, z))
                                          @ Matrix.Diagonal((1, 0.5, 1, 1)))
                count += 1
    add(bb, "Sofa_Buttons")
    log(f"стяжка: {count} пуговиц")


# ----------------------------------------------------------------- объекты и материалы
def collection():
    c = bpy.data.collections.get("Sofa")
    if c is None:
        c = bpy.data.collections.new("Sofa")
        bpy.context.scene.collection.children.link(c)
    return c


def to_object(name, bms):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    for part in bms:
        tmp = bpy.data.meshes.new("tmp")
        part.to_mesh(tmp)
        bm.from_mesh(tmp)
        bpy.data.meshes.remove(tmp)
        part.free()
    ngons = [f for f in bm.faces if len(f.verts) > 4]
    if ngons:
        bmesh.ops.triangulate(bm, faces=ngons)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    collection().objects.link(o)
    return o


def finish(o, bevel=0.0):
    activate(o)
    if bevel:
        b = o.modifiers.new("Bevel", 'BEVEL')
        b.width, b.segments, b.limit_method, b.angle_limit = bevel, 2, 'ANGLE', math.radians(30)
        b.harden_normals = True
        bpy.ops.object.modifier_apply(modifier=b.name)
    for p in o.data.polygons:
        p.use_smooth = True
    wn = o.modifiers.new("WN", 'WEIGHTED_NORMAL')
    wn.keep_sharp = True
    bpy.ops.object.modifier_apply(modifier=wn.name)


def material(name, color, dark, rough, kind):
    """Потёртая ткань / дерево: крупные пятна (тёмные проплешины) + мелкая фактура."""
    mat = bpy.data.materials.new(name)
    if bpy.app.version < (5, 0):
        mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    mat.diffuse_color = (*color, 1)
    bsdf.inputs["Roughness"].default_value = rough
    coord = nt.nodes.new("ShaderNodeTexCoord")
    patches = nt.nodes.new("ShaderNodeTexNoise")
    patches.inputs["Scale"].default_value = 7.0
    patches.inputs["Detail"].default_value = 6
    patches.inputs["Roughness"].default_value = 0.65
    nt.links.new(coord.outputs["Object"], patches.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[0].color = 0.30, (*dark, 1)
    ramp.color_ramp.elements[1].position, ramp.color_ramp.elements[1].color = 0.58, (*color, 1)
    nt.links.new(patches.outputs["Fac"], ramp.inputs["Fac"])
    if kind == "wood":
        wave = nt.nodes.new("ShaderNodeTexWave")
        wave.inputs["Scale"].default_value = 18
        wave.inputs["Distortion"].default_value = 4
        nt.links.new(coord.outputs["Object"], wave.inputs["Vector"])
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type, mix.blend_type = 'RGBA', 'MULTIPLY'
        mix.inputs["Factor"].default_value = 0.35
        nt.links.new(ramp.outputs["Color"], mix.inputs[6])
        nt.links.new(wave.outputs["Color"], mix.inputs[7])
        nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
        ccw = "Coat Weight" if "Coat Weight" in bsdf.inputs else "Clearcoat"
        if ccw in bsdf.inputs:
            bsdf.inputs[ccw].default_value = 0.15
    else:
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        sh = "Sheen Weight" if "Sheen Weight" in bsdf.inputs else "Sheen"
        if sh in bsdf.inputs:
            bsdf.inputs[sh].default_value = 0.25
        if "Sheen Tint" in bsdf.inputs and bsdf.inputs["Sheen Tint"].type == 'RGBA':
            bsdf.inputs["Sheen Tint"].default_value = (min(1, color[0] * 3), color[1] * 2, color[2] * 2, 1)   # отлив в цвет ткани
        fine = nt.nodes.new("ShaderNodeTexNoise")
        fine.inputs["Scale"].default_value = 700
        nt.links.new(coord.outputs["Object"], fine.inputs["Vector"])
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.12
        bump.inputs["Distance"].default_value = 0.0006
        nt.links.new(fine.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def main():
    global STYLE
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = os.path.abspath(args[0]) if args else None
    if len(args) > 1:
        STYLE = args[1]
    for o in list(bpy.data.objects):
        if o.name.startswith("Sofa_"):
            bpy.data.objects.remove(o, do_unlink=True)
    PARTS.clear()
    build_base()
    build_cushion()
    build_arms()
    build_back()
    objs = {name: to_object(name, bms) for name, bms in PARTS.items()}
    finish(objs["Sofa_Frame"], bevel=0.004)
    finish(objs["Sofa_Upholstery"], bevel=0.006)
    for n in ("Sofa_Cushion", "Sofa_Tufting", "Sofa_Buttons"):
        finish(objs[n])
    if STYLE == "white":
        fabric = material("M_Sofa_Fabric", (0.75, 0.73, 0.69), (0.55, 0.53, 0.5), 0.75, "fabric")
        wood = material("M_Sofa_Wood", (0.78, 0.77, 0.74), (0.6, 0.59, 0.56), 0.5, "wood")
        btn = fabric
    else:
        fabric = material("M_Sofa_Velvet", (0.15, 0.006, 0.011), (0.06, 0.004, 0.007), 0.66, "fabric")
        wood = material("M_Sofa_Wood", (0.11, 0.035, 0.022), (0.035, 0.012, 0.008), 0.45, "wood")
        btn = material("M_Sofa_Buttons", (0.06, 0.006, 0.01), (0.03, 0.003, 0.005), 0.6, "fabric")
    for name, m in (("Sofa_Frame", wood), ("Sofa_Upholstery", fabric), ("Sofa_Cushion", fabric),
                    ("Sofa_Tufting", fabric), ("Sofa_Buttons", btn)):
        o = objs[name]
        o.data.materials.append(m)
        activate(o)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.003)
        bpy.ops.object.mode_set(mode='OBJECT')
        log(f"{name}: {sum(len(p.vertices) - 2 for p in o.data.polygons)} треугольников")
    if out:
        os.makedirs(out, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "Sofa.blend"))
        for o in bpy.data.objects:
            o.select_set(o.name.startswith("Sofa_"))
        bpy.ops.export_scene.gltf(filepath=os.path.join(out, "Sofa.glb"), export_format='GLB', use_selection=True)
        bpy.ops.export_scene.fbx(filepath=os.path.join(out, "Sofa_Roblox.fbx"), use_selection=True,
                                 axis_forward='-Z', axis_up='Y', apply_scale_options='FBX_SCALE_ALL',
                                 path_mode='STRIP')
        log(f"сохранено -> {out}")


if __name__ == "__main__":
    main()
