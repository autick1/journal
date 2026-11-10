"""
Bellhop — жуткий коридорный. Процедурная сборка игрового персонажа в Blender.

Создаёт:
  * Bellhop_Mesh  — единый low-poly меш (~15–20k треугольников), 8 материалов,
                    UV-развёртка, веса на кости
  * Bellhop_Rig   — скелет для игр (pelvis/spine/neck/head, руки, 2 кости на палец, ноги)
  * всё в коллекции "Bellhop" (или "07_Export", если сцена создана new_character_scene.py)

Запуск:
  1) Blender -> вкладка Scripting -> Open -> build_bellhop.py -> Run Script
  2) или Claude Desktop через MCP: «прочитай build_bellhop.py и выполни его в Blender»
  3) или терминал: blender --background --python build_bellhop.py -- D:/path/Bellhop.blend

Повторный запуск пересобирает персонажа (удаляются только объекты Bellhop_*).
Пропорции и цвета вынесены в константы ниже — их удобно править.
"""

import math
import random
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

# ----------------------------------------------------------------- параметры
SEED = 7
CLOTH_JITTER = 0.004            # «мятость» ткани, м
HEAD_CENTER = Vector((0, -0.24, 2.10))
HEAD_TILT_DEG = 18              # наклон головы вперёд
FINGER_LEN = 0.34               # длина когтистых пальцев, м

COLORS = {
    "Jacket": ((0.20, 0.018, 0.022, 1), 0.85, 0.0),
    "Gold":   ((0.80, 0.52, 0.20, 1), 0.35, 1.0),
    "Pants":  ((0.045, 0.012, 0.012, 1), 0.9, 0.0),
    "Skin":   ((0.035, 0.012, 0.010, 1), 0.55, 0.0),
    "Teeth":  ((0.85, 0.82, 0.75, 1), 0.35, 0.0),
    "Shoes":  ((0.05, 0.02, 0.015, 1), 0.6, 0.0),
    "Button": ((0.75, 0.75, 0.72, 1), 0.25, 1.0),
}
EYE_EMISSION = 25.0

random.seed(SEED)
BONES = {}      # name -> (head, tail, parent)
PARTS = []      # созданные объекты-части до объединения


# ----------------------------------------------------------------- материалы
def get_material(name):
    full = f"M_Bellhop_{name}"
    mat = bpy.data.materials.get(full) or bpy.data.materials.new(full)
    mat.use_nodes = True if bpy.app.version < (5, 0) else mat.use_nodes
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if name == "Eyes":
        color, rough, metal = (1, 1, 1, 1), 0.3, 0.0
    else:
        color, rough, metal = COLORS[name]
    mat.diffuse_color = color
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if name == "Eyes":
        key = "Emission Color" if "Emission Color" in bsdf.inputs else "Emission"
        bsdf.inputs[key].default_value = (1, 0.97, 0.9, 1)
        bsdf.inputs["Emission Strength"].default_value = EYE_EMISSION
    return mat


# ----------------------------------------------------------------- геометрия
def catmull(points, radii, sub):
    """Сглаживает ломаную (Catmull-Rom) и линейно интерполирует радиусы."""
    if len(points) < 3 or sub <= 1:
        return points, radii
    pts, rds = [], []
    n = len(points)
    for i in range(n - 1):
        p0 = points[max(i - 1, 0)]
        p1, p2 = points[i], points[i + 1]
        p3 = points[min(i + 2, n - 1)]
        for k in range(sub):
            t = k / sub
            t2, t3 = t * t, t * t * t
            p = 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                       + (-p0 + 3 * p1 - 3 * p2 + p3) * t3)
            pts.append(p)
            r1, r2 = radii[i], radii[i + 1]
            rds.append((r1[0] + (r2[0] - r1[0]) * t, r1[1] + (r2[1] - r1[1]) * t))
    pts.append(points[-1])
    rds.append(radii[-1])
    return pts, rds


def tube(bm, points, radii, segs=8, sub=4, ref=Vector((1, 0, 0))):
    """Трубка вдоль пути с эллиптическим сечением. Радиус 0 на конце = острый кончик."""
    points = [Vector(p) for p in points]
    radii = [(r, r) if isinstance(r, (int, float)) else tuple(r) for r in radii]
    points, radii = catmull(points, radii, sub)
    n = len(points)
    tangents = []
    for i in range(n):
        a, b = points[max(i - 1, 0)], points[min(i + 1, n - 1)]
        tangents.append((b - a).normalized())
    normal = ref - ref.dot(tangents[0]) * tangents[0]
    if normal.length < 1e-4:
        normal = Vector((0, 1, 0)) - Vector((0, 1, 0)).dot(tangents[0]) * tangents[0]
    normal.normalize()

    rings = []
    for i, (p, t, r) in enumerate(zip(points, tangents, radii)):
        normal = (normal - normal.dot(t) * t).normalized()
        binorm = t.cross(normal)
        if max(r) < 1e-6:
            rings.append([bm.verts.new(p)])
            continue
        ring = []
        for j in range(segs):
            a = 2 * math.pi * j / segs
            ring.append(bm.verts.new(p + normal * (r[0] * math.cos(a)) + binorm * (r[1] * math.sin(a))))
        rings.append(ring)

    for ra, rb in zip(rings, rings[1:]):
        if len(ra) == 1 and len(rb) == 1:
            continue
        if len(ra) == 1 or len(rb) == 1:
            tip, ring = (ra[0], rb) if len(ra) == 1 else (rb[0], ra)
            for j in range(segs):
                bm.faces.new((ring[j], ring[(j + 1) % segs], tip))
            continue
        for j in range(segs):
            bm.faces.new((ra[j], ra[(j + 1) % segs], rb[(j + 1) % segs], rb[j]))
    # заглушки на концах — треугольный веер
    for ring, p in ((rings[0], points[0]), (rings[-1], points[-1])):
        if len(ring) > 1:
            c = bm.verts.new(p)
            for j in range(segs):
                bm.faces.new((ring[j], ring[(j + 1) % segs], c))
    return bm


def box(bm, center, size, rot=Matrix()):
    m = Matrix.Translation(center) @ rot.to_4x4() @ Matrix.Diagonal((*size, 1))
    bmesh.ops.create_cube(bm, size=1.0, matrix=m)


def sphere(bm, center, radius, segs=10, rings=6, scale=(1, 1, 1)):
    m = Matrix.Translation(center) @ Matrix.Diagonal((*scale, 1))
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=rings, radius=radius, matrix=m)


def jitter(bm, amount):
    for v in bm.verts:
        v.co += Vector((random.uniform(-1, 1), random.uniform(-1, 1), random.uniform(-1, 1))) * amount


# ----------------------------------------------------------------- части и веса
def seg_dist(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
    return (a + ab * t - p).length


def make_part(name, bm, material, bones, smooth=False):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(f"Bellhop_{name}")
    bm.to_mesh(me)
    bm.free()
    for poly in me.polygons:
        poly.use_smooth = smooth
    obj = bpy.data.objects.new(f"Bellhop_{name}", me)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(get_material(material))

    groups = {b: obj.vertex_groups.new(name=b) for b in bones}
    for v in me.vertices:
        ws = sorted(((b, 1.0 / (seg_dist(v.co, BONES[b][0], BONES[b][1]) ** 4 + 1e-9)) for b in bones),
                    key=lambda x: -x[1])[:3]
        total = sum(w for _, w in ws)
        for b, w in ws:
            w /= total
            if w > 0.01:
                groups[b].add([v.index], w, 'REPLACE')
    PARTS.append(obj)
    return obj


def bone(name, head, tail, parent=None):
    BONES[name] = (Vector(head), Vector(tail), parent)


# ----------------------------------------------------------------- скелет
def define_skeleton():
    bone("pelvis", (0, 0.02, 1.25), (0, 0.02, 1.38))
    bone("spine_01", (0, 0.02, 1.38), (0, 0.025, 1.60), "pelvis")
    bone("spine_02", (0, 0.025, 1.60), (0, -0.01, 1.82), "spine_01")
    bone("spine_03", (0, -0.01, 1.82), (0, -0.07, 1.93), "spine_02")
    bone("neck", (0, -0.07, 1.93), (0, -0.20, 2.03), "spine_03")
    bone("head", (0, -0.20, 2.03), (0, -0.30, 2.24), "neck")
    for s, sfx in ((1, "l"), (-1, "r")):
        bone(f"clavicle_{sfx}", (0.03 * s, -0.05, 1.90), (0.22 * s, -0.04, 1.88), "spine_03")
        bone(f"upperarm_{sfx}", (0.24 * s, -0.04, 1.87), (0.34 * s, -0.08, 1.38), f"clavicle_{sfx}")
        bone(f"lowerarm_{sfx}", (0.34 * s, -0.08, 1.38), (0.40 * s, -0.12, 0.88), f"upperarm_{sfx}")
        bone(f"hand_{sfx}", (0.40 * s, -0.12, 0.88), (0.43 * s, -0.14, 0.78), f"lowerarm_{sfx}")
        for fname, path in finger_paths(s).items():
            mid = len(path) // 2
            bone(f"{fname}_01_{sfx}", path[0], path[mid], f"hand_{sfx}")
            bone(f"{fname}_02_{sfx}", path[mid], path[-1], f"{fname}_01_{sfx}")
        bone(f"thigh_{sfx}", (0.08 * s, 0.02, 1.30), (0.10 * s, 0.0, 0.72), "pelvis")
        bone(f"calf_{sfx}", (0.10 * s, 0.0, 0.72), (0.11 * s, 0.03, 0.10), f"thigh_{sfx}")
        bone(f"foot_{sfx}", (0.11 * s, 0.03, 0.10), (0.11 * s, -0.15, 0.03), f"calf_{sfx}")


def finger_paths(s):
    """Пути пальцев: 4 когтя + большой. Кисть висит, ладонь смотрит внутрь (к телу)."""
    knuckle = Vector((0.43 * s, -0.14, 0.78))
    L = FINGER_LEN
    paths = {}
    for name, dy, scale in (("index", -0.03, 0.95), ("middle", -0.01, 1.0),
                            ("ring", 0.01, 0.95), ("pinky", 0.03, 0.8)):
        base = knuckle + Vector((0, dy, 0))
        spread = dy * 3.0
        l = L * scale
        paths[name] = [
            base,
            base + Vector((0.025 * s, spread * 0.4, -0.33 * l)),
            base + Vector((0.015 * s, spread * 0.8 - 0.02, -0.66 * l)),
            base + Vector((-0.03 * s, spread - 0.05, -1.0 * l)),
        ]
    tb = Vector((0.41 * s, -0.165, 0.845))
    paths["thumb"] = [tb, tb + Vector((0.005 * s, -0.05, -0.06)),
                      tb + Vector((-0.01 * s, -0.09, -0.13)), tb + Vector((-0.04 * s, -0.11, -0.19))]
    return paths


# ----------------------------------------------------------------- тело
JACKET_RINGS = [  # z, y-смещение (горб), (rx, ry)
    (1.22, 0.030, (0.170, 0.125)),
    (1.32, 0.035, (0.150, 0.112)),
    (1.45, 0.040, (0.128, 0.100)),
    (1.60, 0.035, (0.150, 0.110)),
    (1.75, 0.010, (0.190, 0.120)),
    (1.87, -0.030, (0.250, 0.120)),
    (1.94, -0.060, (0.200, 0.100)),
    (1.985, -0.080, (0.080, 0.065)),
]


def jacket_front_y(z):
    for (z1, y1, r1), (z2, y2, r2) in zip(JACKET_RINGS, JACKET_RINGS[1:]):
        if z1 <= z <= z2:
            t = (z - z1) / (z2 - z1)
            return y1 + (y2 - y1) * t - (r1[1] + (r2[1] - r1[1]) * t)
    return 0.0


def build_torso():
    bm = bmesh.new()
    tube(bm, [(0, y, z) for z, y, _ in JACKET_RINGS], [r for *_, r in JACKET_RINGS], segs=16, sub=3)
    jitter(bm, CLOTH_JITTER)
    # бёдра тоже влияют на подол, чтобы ноги не протыкали пиджак при шаге
    spine = ["pelvis", "spine_01", "spine_02", "spine_03", "clavicle_l", "clavicle_r", "thigh_l", "thigh_r"]
    make_part("Jacket", bm, "Jacket", spine)

    # золотая кайма по низу пиджака
    bm = bmesh.new()
    z, y, r = JACKET_RINGS[0]
    tube(bm, [(0, y, z - 0.003), (0, y, z + 0.022)],
         [(r[0] + 0.006, r[1] + 0.006), (r[0] + 0.004, r[1] + 0.004)], segs=16, sub=1)
    make_part("HemTrim", bm, "Gold", ["pelvis", "spine_01", "thigh_l", "thigh_r"])

    # стоячий воротник + золотой кант
    bm = bmesh.new()
    tube(bm, [(0, -0.08, 1.95), (0, -0.10, 2.02)], [(0.075, 0.065), (0.07, 0.06)], segs=12, sub=1)
    jitter(bm, CLOTH_JITTER * 0.5)
    make_part("Collar", bm, "Jacket", ["spine_03", "neck"])
    bm = bmesh.new()
    tube(bm, [(0, -0.098, 2.012), (0, -0.101, 2.03)], [(0.076, 0.066), (0.074, 0.064)], segs=12, sub=1)
    make_part("CollarTrim", bm, "Gold", ["spine_03", "neck"])

    # пуговицы: 2 ряда по 3
    bm = bmesh.new()
    for x in (-0.05, 0.05):
        for z in (1.52, 1.62, 1.72):
            sphere(bm, Vector((x, jacket_front_y(z) - 0.004, z)), 0.012, segs=8, rings=4,
                   scale=(1, 0.5, 1))
    make_part("Buttons", bm, "Button", ["spine_01", "spine_02"], smooth=True)

    # эполеты
    for s, sfx in ((1, "l"), (-1, "r")):
        bm = bmesh.new()
        rot = Matrix.Rotation(math.radians(-10 * s), 3, 'Y')
        box(bm, Vector((0.20 * s, -0.04, 1.905)), (0.12, 0.13, 0.022), rot)
        make_part(f"Epaulette_{sfx}", bm, "Jacket", [f"clavicle_{sfx}", f"upperarm_{sfx}"])
        bm = bmesh.new()
        box(bm, Vector((0.20 * s, -0.04, 1.900)), (0.13, 0.14, 0.012), rot)
        make_part(f"EpauletteTrim_{sfx}", bm, "Gold", [f"clavicle_{sfx}", f"upperarm_{sfx}"])


def build_arms():
    for s, sfx in ((1, "l"), (-1, "r")):
        sh, el, wr = BONES[f"upperarm_{sfx}"][0], BONES[f"upperarm_{sfx}"][1], BONES[f"lowerarm_{sfx}"][1]
        bones = [f"clavicle_{sfx}", f"upperarm_{sfx}", f"lowerarm_{sfx}"]
        bm = bmesh.new()
        sleeve_end = wr + (el - wr).normalized() * 0.02
        tube(bm, [sh + Vector((0, 0, 0.01)), sh.lerp(el, 0.5), el, el.lerp(wr, 0.5), sleeve_end],
             [0.058, 0.050, 0.046, 0.046, 0.052], segs=10, sub=4)
        jitter(bm, CLOTH_JITTER)
        make_part(f"Sleeve_{sfx}", bm, "Jacket", bones)

        # золотая манжета
        bm = bmesh.new()
        d = (el - wr).normalized()
        tube(bm, [wr + d * 0.06, wr + d * 0.04], [0.055, 0.056], segs=10, sub=1)
        make_part(f"Cuff_{sfx}", bm, "Gold", [f"lowerarm_{sfx}"])

        # запястье и ладонь
        hand_b = BONES[f"hand_{sfx}"]
        bm = bmesh.new()
        tube(bm, [wr + d * 0.05, wr, hand_b[0].lerp(hand_b[1], 0.5), hand_b[1]],
             [0.026, 0.024, (0.022, 0.045), (0.02, 0.05)], segs=8, sub=2)
        make_part(f"Palm_{sfx}", bm, "Skin", [f"lowerarm_{sfx}", f"hand_{sfx}"])

        # когтистые пальцы
        for fname, path in finger_paths(s).items():
            bm = bmesh.new()
            tube(bm, path, [0.016, 0.013, 0.009, 0.0], segs=6, sub=3)
            make_part(f"Finger_{fname}_{sfx}", bm, "Skin",
                      [f"hand_{sfx}", f"{fname}_01_{sfx}", f"{fname}_02_{sfx}"])


def build_legs():
    for s, sfx in ((1, "l"), (-1, "r")):
        hip, knee, ankle = BONES[f"thigh_{sfx}"][0], BONES[f"thigh_{sfx}"][1], BONES[f"calf_{sfx}"][1]
        bm = bmesh.new()
        tube(bm, [hip + Vector((0, 0, 0.015)), hip.lerp(knee, 0.5), knee, knee.lerp(ankle, 0.6),
                  ankle + Vector((0, 0, 0.01))],
             [0.060, 0.050, 0.044, 0.052, 0.070], segs=10, sub=4)
        jitter(bm, CLOTH_JITTER)
        make_part(f"Pants_{sfx}", bm, "Pants", ["pelvis", f"thigh_{sfx}", f"calf_{sfx}"])

        # большие плоские ботинки
        bm = bmesh.new()
        x = ankle.x
        tube(bm, [(x, 0.085, 0.055), (x, 0.03, 0.06), (x, -0.08, 0.045), (x, -0.19, 0.035)],
             [(0.050, 0.045), (0.058, 0.055), (0.060, 0.040), (0.045, 0.028)], segs=10, sub=2)
        for v in bm.verts:           # ровная подошва
            v.co.z = max(v.co.z, 0.0)
        make_part(f"Shoe_{sfx}", bm, "Shoes", [f"foot_{sfx}", f"calf_{sfx}"])


def build_head():
    head_m = Matrix.Translation(HEAD_CENTER) @ Matrix.Rotation(math.radians(HEAD_TILT_DEG), 4, 'X')

    def finish(bm, name, mat_name, smooth=False):
        bmesh.ops.transform(bm, matrix=head_m, verts=bm.verts)
        make_part(name, bm, mat_name, ["head"], smooth)

    # шея
    bm = bmesh.new()
    tube(bm, [(0, -0.06, 1.90), (0, -0.14, 1.99), (0, -0.21, 2.04)], [0.034, 0.032, 0.036], segs=8, sub=2)
    make_part("Neck", bm, "Skin", ["spine_03", "neck", "head"])

    # голова — вытянутая, широкая в челюсти
    bm = bmesh.new()
    tube(bm, [(0, 0.005, -0.115), (0, 0, -0.095), (0, 0, -0.05), (0, 0, 0.0), (0, 0, 0.05),
              (0, 0.005, 0.09), (0, 0.01, 0.115)],
         [0.0, (0.07, 0.065), (0.105, 0.09), (0.1, 0.092), (0.092, 0.09), (0.075, 0.078), 0.0],
         segs=14, sub=2)
    finish(bm, "Head", "Skin")

    # зубы — две чередующиеся дуги длинных клыков, широкая улыбка
    def mouth_point(angle_deg, z, out=0.003):
        a = math.radians(angle_deg)
        rx, ry = 0.104, 0.091
        smile = 0.025 * (abs(angle_deg) / 72) ** 2      # уголки улыбки вверх
        return Vector((rx * math.sin(a), -ry * math.cos(a) - out, z + smile))

    bm = bmesh.new()
    for i in range(13):                                 # верхний ряд — вниз
        a = -72 + i * 12
        length = 0.050 * (1 - 0.5 * abs(a) / 72)
        base = mouth_point(a, -0.012)
        tip = base + Vector((0, -0.006, -length))
        tube(bm, [base, base.lerp(tip, 0.5), tip], [0.0075, 0.006, 0.0], segs=5, sub=1)
    for i in range(12):                                 # нижний ряд — вверх, между верхними
        a = -66 + i * 12
        length = 0.044 * (1 - 0.5 * abs(a) / 72)
        base = mouth_point(a, -0.072)
        tip = base + Vector((0, -0.006, length))
        tube(bm, [base, base.lerp(tip, 0.5), tip], [0.007, 0.0055, 0.0], segs=5, sub=1)
    finish(bm, "Teeth", "Teeth", smooth=True)

    # светящиеся глаза
    bm = bmesh.new()
    for s in (1, -1):
        sphere(bm, Vector((0.043 * s, -0.083, 0.032)), 0.021, segs=10, rings=6)
    finish(bm, "Eyes", "Eyes", smooth=True)

    # шапка-таблетка с козырьком и золотыми полосами
    bm = bmesh.new()
    tube(bm, [(0, 0.008, 0.075), (0, 0.008, 0.125), (0, 0.008, 0.175)],
         [(0.094, 0.098), (0.097, 0.101), (0.101, 0.105)], segs=16, sub=1)
    jitter(bm, CLOTH_JITTER * 0.5)
    finish(bm, "Hat", "Jacket")
    bm = bmesh.new()
    for z0, z1 in ((0.074, 0.090), (0.150, 0.160)):
        r0 = 0.094 + 0.007 * (z0 - 0.075) / 0.1
        tube(bm, [(0, 0.008, z0), (0, 0.008, z1)], [(r0 + 0.005, r0 + 0.009), (r0 + 0.006, r0 + 0.010)],
             segs=16, sub=1)
    finish(bm, "HatTrim", "Gold")
    bm = bmesh.new()
    box(bm, Vector((0, -0.105, 0.072)), (0.13, 0.05, 0.008), Matrix.Rotation(math.radians(-12), 3, 'X'))
    finish(bm, "HatVisor", "Shoes")


# ----------------------------------------------------------------- сборка
def build_armature(collection):
    arm = bpy.data.armatures.new("Bellhop_Rig")
    obj = bpy.data.objects.new("Bellhop_Rig", arm)
    collection.objects.link(obj)
    arm.display_type = 'STICK'
    obj.show_in_front = True
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    ebs = {}
    for name, (h, t, _) in BONES.items():
        eb = arm.edit_bones.new(name)
        eb.head, eb.tail = h, t
        ebs[name] = eb
    for name, (h, _, parent) in BONES.items():
        if parent:
            ebs[name].parent = ebs[parent]
            ebs[name].use_connect = (ebs[parent].tail - h).length < 1e-5
    bpy.ops.object.mode_set(mode='OBJECT')
    return obj


def cleanup():
    for obj in list(bpy.data.objects):
        if obj.name.startswith("Bellhop_"):
            bpy.data.objects.remove(obj, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.armatures):
        for item in list(coll):
            if item.name.startswith("Bellhop_") and item.users == 0:
                coll.remove(item)


def target_collection():
    coll = bpy.data.collections.get("07_Export")
    if coll is None:
        coll = bpy.data.collections.get("Bellhop") or bpy.data.collections.new("Bellhop")
        if coll.name not in bpy.context.scene.collection.children:
            bpy.context.scene.collection.children.link(coll)
    return coll


def main():
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    cleanup()
    BONES.clear()
    PARTS.clear()
    define_skeleton()
    build_torso()
    build_arms()
    build_legs()
    build_head()

    coll = target_collection()
    # объединяем части в один меш
    bpy.ops.object.select_all(action='DESELECT')
    for p in PARTS:
        p.select_set(True)
    body = PARTS[0]
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.join()
    body.name = body.data.name = "Bellhop_Mesh"
    for c in list(body.users_collection):
        c.objects.unlink(body)
    coll.objects.link(body)

    # UV-развёртка
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.004)
    bpy.ops.object.mode_set(mode='OBJECT')

    # скелет и привязка
    rig = build_armature(coll)
    body.parent = rig
    mod = body.modifiers.new("Armature", 'ARMATURE')
    mod.object = rig

    tris = sum(len(p.vertices) - 2 for p in body.data.polygons)
    print(f"[bellhop] готово: {len(body.data.vertices)} вершин, {tris} треугольников, "
          f"{len(body.data.materials)} материалов, {len(BONES)} костей")

    if "--" in sys.argv:
        out = sys.argv[sys.argv.index("--") + 1:]
        if out and out[0].endswith(".blend"):
            bpy.ops.wm.save_as_mainfile(filepath=out[0])
            print(f"[bellhop] сохранено: {out[0]}")


if __name__ == "__main__":
    main()
