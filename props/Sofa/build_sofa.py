"""
Диван-«капитоне» с горбатой спинкой и подлокотниками-валиками (по референсу).

Состав (отдельные объекты, каждый < 20 000 треугольников — подходит для Roblox MeshPart):
  Sofa_Frame      — ножки, царга с филёнкой, валик-рамка по контуру спинки, волюты подлокотников (дерево)
  Sofa_Upholstery — корпус спинки (силуэт с горбом) и подлокотники-валики
  Sofa_Tufting    — стяжка «капитоне» внутри рамки спинки (ромбы, складки по диагоналям)
  Sofa_Cushion    — подушка сиденья
  Sofa_Buttons    — пуговицы стяжки (латунь)

Размеры (м): ширина 2.0, глубина 0.86, высота спинки 1.13, подлокотники 0.74, сиденье 0.49.
Лицо дивана смотрит в -Y.

Запуск: blender --background --python build_sofa.py -- out_dir [velvet|white]
"""

import math
import os
import sys

import bpy
import bmesh
from mathutils import Matrix, Vector, noise

STYLE = "velvet"

W = 2.0                    # ширина
D = 0.86                   # глубина
LEG_H = 0.15
BASE_TOP = 0.31            # верх царги
SEAT_TOP = 0.49
ARM_W = 0.20               # ширина подлокотника
ARM_TOP = 0.74
ROLL_R = 0.095             # радиус валика подлокотника
BACK_T = 0.17              # толщина спинки
BACK_Y = D / 2 - BACK_T / 2
# силуэт верха спинки (половина, от центра к краю): (x, z) — горб в центре, «плечи», скат к подлокотникам
BACK_TOP = [(0.0, 1.13), (0.10, 1.12), (0.16, 1.07), (0.22, 1.02), (0.44, 1.015), (0.62, 0.97), (0.80, 0.86)]
TUFT_A, TUFT_B = 0.125, 0.105   # полуразмеры ромба стяжки (по X и Z)
TUFT_DEPTH = 0.036

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


def box(bm, center, size):
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(center) @ Matrix.Diagonal((*size, 1)))


def prism_xz(bm, poly, y0, y1):
    front = [bm.verts.new((x, y0, z)) for x, z in poly]
    back = [bm.verts.new((x, y1, z)) for x, z in poly]
    f0 = bm.faces.new(front)
    f1 = bm.faces.new(list(reversed(back)))
    n = len(poly)
    for i in range(n):
        bm.faces.new((front[i], front[(i + 1) % n], back[(i + 1) % n], back[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return f0, f1


def prism_yz(bm, poly, x0, x1):
    """Многоугольник в плоскости YZ, выдавленный по X (профиль подлокотника)."""
    a = [bm.verts.new((x0, y, z)) for y, z in poly]
    b = [bm.verts.new((x1, y, z)) for y, z in poly]
    bm.faces.new(a)
    bm.faces.new(list(reversed(b)))
    n = len(poly)
    for i in range(n):
        bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)


def tube(bm, pts, r, segs=10, closed=False):
    """Трубка постоянного радиуса вдоль ломаной (валик-рамка, завиток)."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    rings = []
    ref = Vector((0, 1, 0))
    for i, p in enumerate(pts):
        a = pts[(i - 1) % n] if (closed or i > 0) else p
        b = pts[(i + 1) % n] if (closed or i < n - 1) else p
        t = (b - a).normalized()
        nrm = (ref - ref.dot(t) * t)
        if nrm.length < 1e-4:
            nrm = Vector((1, 0, 0)) - Vector((1, 0, 0)).dot(t) * t
        nrm.normalize()
        bn = t.cross(nrm)
        rings.append([bm.verts.new(p + nrm * (r * math.cos(2 * math.pi * k / segs)) +
                                   bn * (r * math.sin(2 * math.pi * k / segs))) for k in range(segs)])
    for i in range(n if closed else n - 1):
        ra, rb = rings[i], rings[(i + 1) % n]
        for k in range(segs):
            bm.faces.new((ra[k], ra[(k + 1) % segs], rb[(k + 1) % segs], rb[k]))
    if not closed:
        bm.faces.new(list(reversed(rings[0])))
        bm.faces.new(rings[-1])


def back_outline():
    """Полный контур спинки (XZ): низ на уровне сиденья, верх — силуэт с горбом."""
    right = BACK_TOP
    left = [(-x, z) for x, z in reversed(right[1:])]
    top = left + right
    xe = right[-1][0]
    return [(-xe, SEAT_TOP - 0.06)] + top + [(xe, SEAT_TOP - 0.06)], top


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
    """Сдвиг замкнутого контура внутрь на d (по биссектрисам)."""
    n = len(poly)
    out = []
    for i in range(n):
        p0, p1, p2 = Vector(poly[i - 1]), Vector(poly[i]), Vector(poly[(i + 1) % n])
        e1 = (p1 - p0).normalized()
        e2 = (p2 - p1).normalized()
        n1 = Vector((-e1.y, e1.x))
        n2 = Vector((-e2.y, e2.x))
        bis = (n1 + n2)
        if bis.length < 1e-6:
            bis = n1
        bis.normalize()
        k = d / max(0.3, bis.dot(n1))
        out.append(tuple(p1 + bis * k))
    # ориентация: если площадь уменьшилась — сдвинули внутрь, иначе — наружу
    def area(p):
        return 0.5 * sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p)))
    if abs(area(out)) > abs(area(poly)):
        return offset_poly(poly, -d)
    return out


# ----------------------------------------------------------------- части
def build_legs_and_base():
    bm = bmesh.new()
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * (W / 2 - 0.12), sy * (D / 2 - 0.11)
            # сужающаяся ножка: усечённая пирамида + башмачок + капитель
            bmesh.ops.create_cone(bm, cap_ends=True, segments=4, radius1=0.042, radius2=0.058, depth=LEG_H - 0.05,
                                  matrix=Matrix.Translation((x, y, 0.035 + (LEG_H - 0.05) / 2))
                                  @ Matrix.Rotation(math.pi / 4, 4, 'Z'))
            box(bm, Vector((x, y, 0.018)), (0.072, 0.072, 0.036))
            box(bm, Vector((x, y, LEG_H - 0.01)), (0.1, 0.1, 0.03))
    add(bm, "Sofa_Frame")
    # царга: короб + филёнка спереди + карниз
    bm = bmesh.new()
    poly = [(-W / 2 + 0.03, LEG_H), (W / 2 - 0.03, LEG_H), (W / 2 - 0.03, BASE_TOP), (-W / 2 + 0.03, BASE_TOP)]
    f0, f1 = prism_xz(bm, poly, -D / 2 + 0.03, D / 2 - 0.03)
    front = min(bm.faces, key=lambda f: f.calc_center_median().y)
    bmesh.ops.inset_region(bm, faces=[front], thickness=0.025, depth=0.0)
    bmesh.ops.inset_region(bm, faces=[front], thickness=0.004, depth=-0.008)
    box(bm, Vector((0, -D / 2 + 0.03, BASE_TOP - 0.008)), (W - 0.02, 0.035, 0.022))   # карниз
    box(bm, Vector((0, -D / 2 + 0.035, LEG_H + 0.01)), (W - 0.04, 0.03, 0.02))        # нижняя тяга
    add(bm, "Sofa_Frame")


def build_seat():
    bm = bmesh.new()
    x0 = W / 2 - ARM_W
    y0, y1 = -D / 2 + 0.01, BACK_Y - BACK_T / 2 + 0.02
    nx, ny, nz = 40, 16, 4
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=6, use_grid_fill=True)
    for v in bm.verts:
        u, w, h = v.co.x * 2, v.co.y * 2, v.co.z * 2
        crown = 0.018 * (1 - u * u) * (1 - w * w) if h > 0 else 0.0          # пухлый верх
        v.co = Vector(((u * x0), (y0 + y1) / 2 + w * (y1 - y0) / 2,
                       (BASE_TOP + SEAT_TOP) / 2 + h * (SEAT_TOP - BASE_TOP) / 2 + crown))
    bmesh.ops.bevel(bm, geom=[e for e in bm.edges if e.calc_face_angle(0) > 0.5], offset=0.03, segments=3,
                    profile=0.6, affect='EDGES', clamp_overlap=True)
    add(bm, "Sofa_Cushion")


def arm_profile():
    """Сечение подлокотника в плоскости YZ — нет; сечение в XZ для левого подлокотника (x<0)."""
    xo = -W / 2
    xi = -W / 2 + ARM_W
    xc, zc = xo + ARM_W / 2 + 0.005, ARM_TOP - ROLL_R
    pts = [(xi, BASE_TOP), (xi, zc - 0.02)]
    for k in range(0, 13):                       # валик: дуга от внутренней стороны через верх наружу
        a = math.radians(-20 + 230 * k / 12)
        pts.append((xc + ROLL_R * math.cos(a) * 1.08, zc + ROLL_R * math.sin(a)))
    pts.append((xo + 0.035, zc - 0.11))           # под валиком наружная стенка слегка утоплена
    pts.append((xo + 0.03, BASE_TOP))
    return pts, (xc, zc)


def build_arms():
    for s in (-1, 1):
        prof, (xc, zc) = arm_profile()
        prof = [(s * x, z) for x, z in prof]
        if s > 0:
            prof = list(reversed(prof))
        bm = bmesh.new()
        y_front, y_back = -D / 2 + 0.035, BACK_Y
        prism_xz(bm, prof, y_front, y_back)
        for v in bm.verts:                         # мягкая обивка: лёгкая неровность
            v.co += Vector((0, 0, 0.002 * noise.noise(v.co * 8)))
        add(bm, "Sofa_Upholstery")
        # волюта на торце валика: спираль-трубка + торцевая пластина-пилястра
        bm = bmesh.new()
        cx, cz = s * xc, zc
        y = y_front - 0.012
        spiral = []
        turns = 1.6
        for k in range(70):
            t = k / 69
            ang = math.pi / 2 + s * 2 * math.pi * turns * t
            r = ROLL_R * 0.95 * (1 - 0.82 * t)
            spiral.append((cx + r * math.cos(ang) * 1.05, y - 0.004 * t, cz + r * math.sin(ang)))
        tube(bm, spiral, 0.011, segs=8)
        sphere_m = Matrix.Translation((cx, y - 0.01, cz)) @ Matrix.Diagonal((1, 0.6, 1, 1))
        bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=0.022, matrix=sphere_m)
        # пилястра: вертикальная планка по передней кромке подлокотника до царги
        px = s * (W / 2 - ARM_W / 2 + 0.005)
        box(bm, Vector((px, y_front - 0.006, (BASE_TOP + zc - ROLL_R * 0.9) / 2)),
            (ARM_W * 0.62, 0.02, zc - ROLL_R * 0.9 - BASE_TOP))
        box(bm, Vector((px, y_front - 0.013, (BASE_TOP + zc - ROLL_R * 0.9) / 2)),
            (ARM_W * 0.36, 0.012, zc - ROLL_R * 0.9 - BASE_TOP - 0.06))
        add(bm, "Sofa_Frame")


def build_back():
    outline, top = back_outline()
    yf, yb = BACK_Y - BACK_T / 2, BACK_Y + BACK_T / 2
    # корпус спинки
    bm = bmesh.new()
    body = [(x, max(z, LEG_H + 0.01) if z < SEAT_TOP else z) for x, z in outline]
    body = [(body[0][0], LEG_H + 0.01)] + body[1:-1] + [(body[-1][0], LEG_H + 0.01)]   # сзади до самой царги
    prism_xz(bm, body, yf + 0.03, yb)
    add(bm, "Sofa_Upholstery")
    # валик-рамка по верху и бокам спинки
    bm = bmesh.new()
    rim = []
    xe = BACK_TOP[-1][0]
    rim_pts = [(-xe + 0.01, SEAT_TOP)] + [(x * 0.985, z - 0.05) for x, z in top] + [(xe - 0.01, SEAT_TOP)]
    # сгладить ломаную (Chaikin), чтобы валик шёл плавно
    for _ in range(3):
        new = [rim_pts[0]]
        for a, b in zip(rim_pts, rim_pts[1:]):
            new += [(0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]),
                    (0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1])]
        new.append(rim_pts[-1])
        rim_pts = new
    tube(bm, [(x, yf - 0.004, z) for x, z in rim_pts], 0.046, segs=12)
    add(bm, "Sofa_Frame")
    # стяжка «капитоне» внутри рамки
    inner = offset_poly([(x * 0.985, z - 0.05) for x, z in outline], 0.045)
    xs = [p[0] for p in inner]
    zs = [p[1] for p in inner]
    step = 0.0125
    nx = int((max(xs) - min(xs)) / step) + 1
    nz = int((max(zs) - min(zs)) / step) + 1
    x0, z0 = min(xs), min(zs)
    z_btn0 = SEAT_TOP + 0.07
    bm = bmesh.new()
    grid = {}
    buttons = []

    def height(x, z):
        u = x / TUFT_A + (z - z_btn0) / TUFT_B
        v = x / TUFT_A - (z - z_btn0) / TUFT_B
        su, sv = abs(math.sin(math.pi * u / 2)), abs(math.sin(math.pi * v / 2))
        pillow = (su * sv) ** 0.45                          # 0 на линиях складок, 1 в центре ромба
        return TUFT_DEPTH * pillow

    def nearest_on_poly(x, z):
        best, bd = None, 1e9
        n = len(inner)
        for k in range(n):
            a, b = Vector(inner[k]), Vector(inner[(k + 1) % n])
            ab = b - a
            t = max(0.0, min(1.0, (Vector((x, z)) - a).dot(ab) / max(ab.length_squared, 1e-12)))
            q = a + ab * t
            d = (q - Vector((x, z))).length
            if d < bd:
                best, bd = q, d
        return best, bd

    inside_map = {}
    for i in range(nx + 1):
        for j in range(nz + 1):
            inside_map[(i, j)] = inside(inner, x0 + i * step, z0 + j * step)
    for i in range(nx + 1):
        for j in range(nz + 1):
            near = any(inside_map.get((i + a, j + b)) for a in (-1, 0, 1) for b in (-1, 0, 1))
            if not near:
                continue
            x, z = x0 + i * step, z0 + j * step
            q, dist = nearest_on_poly(x, z)
            if not inside_map[(i, j)]:
                x, z, dist = q.x, q.y, 0.0                   # край притянут точно к контуру — без «лесенки»
            fall = min(1.0, dist / 0.06) ** 0.7              # плавный подъём от рамки
            yy = yf + 0.004 - (0.012 + height(x, z)) * fall  # утоплено за валик-рамку
            grid[(i, j)] = bm.verts.new((x, yy, z))
    for i in range(nx):
        for j in range(nz):
            q = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            if all(k in grid for k in q) and any(inside_map[k] for k in q):
                bm.faces.new([grid[k] for k in q])
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.002)
    bmesh.ops.dissolve_degenerate(bm, dist=0.0005, edges=bm.edges)
    add(bm, "Sofa_Tufting")
    # пуговицы в узлах ромбов
    bm = bmesh.new()
    for a in range(-12, 13):
        for b in range(0, 10):
            x = a * TUFT_A
            z = z_btn0 + b * TUFT_B
            if (a + b) % 2:
                continue
            if inside(offset_poly(inner, 0.03), x, z):
                yy = yf + 0.004 - 0.012 - 0.002
                bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=0.011,
                                          matrix=Matrix.Translation((x, yy, z)) @ Matrix.Diagonal((1, 0.55, 1, 1)))
                buttons.append((x, z))
    add(bm, "Sofa_Buttons")
    log(f"стяжка: {len(buttons)} пуговиц")


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


def finish(o, bevel=0.0, smooth_angle=None):
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


def material(name, color, rough, kind):
    mat = bpy.data.materials.new(name)
    if bpy.app.version < (5, 0):
        mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = rough
    mat.diffuse_color = (*color, 1)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    if kind == "velvet":
        sh = "Sheen Weight" if "Sheen Weight" in bsdf.inputs else "Sheen"
        if sh in bsdf.inputs:
            bsdf.inputs[sh].default_value = 0.15
        if "Sheen Tint" in bsdf.inputs and bsdf.inputs["Sheen Tint"].type == 'RGBA':
            bsdf.inputs["Sheen Tint"].default_value = (min(1, color[0] * 2.5), color[1] * 2, color[2] * 2, 1)
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = 60
        nt.links.new(coord.outputs["Object"], nz.inputs["Vector"])
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = tuple(c * 0.75 for c in color) + (1,)
        ramp.color_ramp.elements[1].color = tuple(min(1, c * 1.15) for c in color) + (1,)
        nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    elif kind == "wood":
        wave = nt.nodes.new("ShaderNodeTexWave")
        wave.bands_direction = 'X'
        wave.inputs["Scale"].default_value = 22
        wave.inputs["Distortion"].default_value = 3
        nt.links.new(coord.outputs["Object"], wave.inputs["Vector"])
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = tuple(c * 0.8 for c in color) + (1,)
        ramp.color_ramp.elements[1].color = tuple(min(1, c * 1.12) for c in color) + (1,)
        nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        ccw = "Coat Weight" if "Coat Weight" in bsdf.inputs else "Clearcoat"
        if ccw in bsdf.inputs:
            bsdf.inputs[ccw].default_value = 0.3
    elif kind == "brass":
        bsdf.inputs["Metallic"].default_value = 1.0
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
    build_legs_and_base()
    build_seat()
    build_arms()
    build_back()
    objs = {name: to_object(name, bms) for name, bms in PARTS.items()}
    finish(objs["Sofa_Frame"], bevel=0.004)
    finish(objs["Sofa_Upholstery"], bevel=0.008)
    finish(objs["Sofa_Cushion"])
    finish(objs["Sofa_Tufting"])
    finish(objs["Sofa_Buttons"])
    if STYLE == "white":
        fabric = material("M_Sofa_Fabric", (0.78, 0.76, 0.72), 0.7, "velvet")
        wood = material("M_Sofa_Wood", (0.8, 0.79, 0.76), 0.5, "plain")
    else:
        fabric = material("M_Sofa_Velvet", (0.06, 0.004, 0.008), 0.75, "velvet")
        wood = material("M_Sofa_Wood", (0.045, 0.022, 0.012), 0.38, "wood")
    brass = material("M_Sofa_Brass", (0.7, 0.5, 0.2), 0.3, "brass")
    for name, m in (("Sofa_Frame", wood), ("Sofa_Upholstery", fabric), ("Sofa_Cushion", fabric),
                    ("Sofa_Tufting", fabric), ("Sofa_Buttons", brass)):
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
