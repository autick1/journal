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


def make_part(name, bm, material, bones, smooth=False, weights=None):
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
    if weights is not None:                      # заданные вручную веса: [{кость: вес}, ...]
        for v, wd in zip(me.vertices, weights):
            for b, w in wd.items():
                if w > 0.005:
                    groups[b].add([v.index], w, 'REPLACE')
        PARTS.append(obj)
        return obj
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
    hm = head_matrix()
    bone("jaw", hm @ JAW_PIVOT, hm @ Vector((0, -0.075, -0.105)), "head")
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


# ----------------------------------------------------------------- тело: анатомия
# Тело собирается из метаболлов — анатомических масс, привязанных к костям скелета:
# грудная клетка с проступающими рёбрами, грудина, грудные мышцы, трапеции, лопатки,
# широчайшие, впалый живот с мышцами пресса, косые мышцы, таз с гребнями подвздошных
# костей, ягодицы; дельты, бицепсы, трицепсы, локтевые отростки, мышцы предплечья;
# квадрицепсы, бицепс бедра, приводящие, костлявые колени, икры, лодыжки.
# Метаболлы -> вокселизация -> Quadriflow (ретопология в квады) -> веса.
# Поверх анатомии тем же способом строится униформа (пиджак и брюки).

MB_K = 0.57                     # видимый радиус метабола = MB_K * radius (threshold 0.6, stiffness 2)
BODY_FACES = 5200               # бюджет ретопологии тела (квадов)
JACKET_FACES = 3600
PANTS_FACES = 2200
HEM_Z = 1.22                    # низ пиджака
SHOW_CLOTHES = True             # False — показать только анатомию (для проверки формы)


class Ball:
    """Описание одного метабола: область тела нужна для весов."""
    def __init__(self, region, kind, a, b=None, semi=(0.02, 0.02, 0.02), neg=False):
        self.region, self.kind, self.neg = region, kind, neg
        self.a, self.b = Vector(a), (Vector(b) if b is not None else None)
        self.semi = semi


def E(region, center, semi, axis=None, neg=False):
    ball = Ball(region, 'ELLIPSOID', center, semi=semi, neg=neg)
    ball.axis = Vector(axis).normalized() if axis is not None else Vector((0, 0, 1))
    return ball


def C(region, a, b, r, neg=False):
    return Ball(region, 'CAPSULE', a, b, semi=(r, r, r), neg=neg)


def P(name, t):
    """Точка на кости name: t=0 — начало, t=1 — конец."""
    h, tl, _ = BONES[name]
    return h.lerp(tl, t)


def anatomy_balls():
    B = []
    up = (P("spine_02", 1) - P("spine_02", 0))
    # --- торс
    B += [E("torso", (0, -0.005, 1.71), (0.122, 0.082, 0.15), up),             # грудная клетка
          E("torso_up", (0, -0.035, 1.83), (0.15, 0.068, 0.07), up),            # верх груди
          E("torso_up", (0, -0.02, 1.872), (0.2, 0.055, 0.04)),                 # плечевой пояс
          C("torso", (0, -0.088, 1.65), (0, -0.098, 1.82), 0.009)]              # грудина
    for s in (1, -1):
        B += [E("torso_up", (0.075 * s, -0.078, 1.79), (0.078, 0.019, 0.05), (0.3 * s, 0, 1)),  # грудные
              E("torso_up", (0.08 * s, 0.025, 1.885), (0.085, 0.04, 0.035), (s, 0, 0.6)),  # трапеции
              E("torso_up", (0.088 * s, 0.072, 1.77), (0.058, 0.02, 0.07), (0.2 * s, 0, 1)),  # лопатки
              E("torso", (0.11 * s, 0.025, 1.68), (0.04, 0.06, 0.12)),          # широчайшие
              E("torso", (0.085 * s, -0.012, 1.46), (0.03, 0.048, 0.075)),     # косые
              E("pelvis", (0.098 * s, -0.022, 1.372), (0.02, 0.028, 0.016)),   # гребни подвздошных
              E("pelvis", (0.064 * s, 0.075, 1.27), (0.062, 0.048, 0.078))]   # ягодицы
        for z in (1.605, 1.645, 1.685, 1.725):                                  # межрёберные провалы
            B.append(E("torso", (0.108 * s, -0.045, z), (0.035, 0.03, 0.0065), neg=True))
        for z in (1.565, 1.505, 1.445):                                         # пресс
            B.append(E("torso", (0.027 * s, -0.07, z), (0.024, 0.009, 0.026)))
    B += [E("torso", (0, -0.018, 1.50), (0.088, 0.066, 0.11)),                   # впалый живот
          E("torso", (0, -0.005, 1.40), (0.1, 0.075, 0.07)),                    # низ живота
          E("pelvis", (0, 0.015, 1.31), (0.125, 0.088, 0.075))]                 # таз
    for z in (1.42, 1.5, 1.58, 1.66, 1.74, 1.82):                               # остистые отростки
        y = 0.058 if z < 1.62 else 0.078 - (z - 1.62) * 0.25
        B.append(E("torso", (0, y, z), (0.011, 0.012, 0.014)))
    # --- шея
    B += [C("neck", (0, -0.06, 1.87), (0, -0.2, 2.03), 0.034),
          E("neck", (0, -0.14, 1.955), (0.012, 0.012, 0.016))]                  # кадык
    for s in (1, -1):
        B.append(C("neck", (0.032 * s, -0.19, 2.035), (0.012 * s, -0.1, 1.895), 0.011))  # грудино-ключичные
    # --- руки
    for s, x in ((1, "l"), (-1, "r")):
        U, El, W = P(f"upperarm_{x}", 0), P(f"upperarm_{x}", 1), P(f"lowerarm_{x}", 1)
        Hh, Ht = P(f"hand_{x}", 0), P(f"hand_{x}", 1)
        ua, fa = (El - U), (W - El)
        B += [C(f"shoulder_{x}", (0.02 * s, -0.09, 1.885), (0.19 * s, -0.06, 1.9), 0.015),   # ключица
              E(f"shoulder_{x}", U + Vector((-0.004 * s, -0.004, -0.025)), (0.056, 0.06, 0.085), ua),  # дельта
              C(f"arm_{x}", U, El, 0.027),                                          # плечевая кость
              E(f"arm_{x}", U.lerp(El, 0.48) + Vector((0, -0.022, 0)), (0.032, 0.03, 0.12), ua),   # бицепс
              E(f"arm_{x}", U.lerp(El, 0.42) + Vector((0, 0.024, 0)), (0.034, 0.031, 0.14), ua),   # трицепс
              E(f"arm_{x}", El + Vector((0, 0.02, 0.005)), (0.02, 0.02, 0.022)),            # локоть
              C(f"forearm_{x}", El, El.lerp(W, 0.5), 0.025),
              C(f"forearm_{x}", El.lerp(W, 0.5), W, 0.019),
              E(f"forearm_{x}", El.lerp(W, 0.25) + Vector((0.012 * s, -0.01, 0)), (0.029, 0.026, 0.1), fa),
              E(f"hand_{x}", W + Vector((0.008 * s, 0.012, 0)), (0.011, 0.011, 0.011)),    # шиловидный отросток
              E(f"hand_{x}", Hh.lerp(Ht, 0.55), (0.016, 0.042, 0.052), Ht - Hh)]          # ладонь
    # --- ноги
    for s, x in ((1, "l"), (-1, "r")):
        T, K, A = P(f"thigh_{x}", 0), P(f"thigh_{x}", 1), P(f"calf_{x}", 1)
        Ft = P(f"foot_{x}", 1)
        th, sh = K - T, A - K
        B += [C(f"leg_{x}", T, K, 0.03),
              E(f"leg_{x}", T.lerp(K, 0.45) + Vector((0, -0.02, 0)), (0.045, 0.038, 0.19), th),   # квадрицепс
              E(f"leg_{x}", T.lerp(K, 0.45) + Vector((0, 0.026, 0)), (0.04, 0.034, 0.18), th),   # бицепс бедра
              E(f"leg_{x}", T.lerp(K, 0.3) + Vector((-0.02 * s, 0, 0)), (0.032, 0.034, 0.13), th),  # приводящие
              E(f"knee_{x}", K, (0.034, 0.031, 0.033)),                                         # колено
              E(f"knee_{x}", K + Vector((0, -0.024, 0.005)), (0.02, 0.012, 0.022)),             # надколенник
              C(f"shin_{x}", K, A, 0.021),
              E(f"shin_{x}", K.lerp(A, 0.25) + Vector((0, 0.022, 0)), (0.036, 0.036, 0.12), sh),  # икра
              E(f"foot_{x}", A, (0.025, 0.022, 0.022)),                                         # лодыжка
              E(f"foot_{x}", A.lerp(Ft, 0.5) + Vector((0, 0, -0.025)), (0.034, 0.025, 0.105), Ft - A),  # стопа
              E(f"foot_{x}", A + Vector((0, 0.025, -0.055)), (0.024, 0.026, 0.022))]           # пятка
    return B


def clothes_balls():
    up = (P("spine_02", 1) - P("spine_02", 0))
    jacket = [E("torso", (0, 0.0, 1.70), (0.147, 0.104, 0.18), up),
              E("torso_up", (0, -0.03, 1.835), (0.155, 0.088, 0.075), up),
              E("torso", (0, 0.002, 1.47), (0.112, 0.09, 0.1)),                  # талия
              E("pelvis", (0, 0.02, 1.29), (0.152, 0.112, 0.1))]                 # расклёшенный низ
    pants = [E("pelvis", (0, 0.015, 1.33), (0.135, 0.1, 0.09))]
    for s, x in ((1, "l"), (-1, "r")):
        U, El, W = P(f"upperarm_{x}", 0), P(f"upperarm_{x}", 1), P(f"lowerarm_{x}", 1)
        jacket += [E(f"shoulder_{x}", (0.205 * s, -0.04, 1.872), (0.078, 0.07, 0.04)),   # плечевые накладки
                   C(f"arm_{x}", U + Vector((0, 0, -0.02)), El, 0.049),
                   C(f"forearm_{x}", El, W, 0.045),
                   E(f"forearm_{x}", El.lerp(W, 0.93), (0.05, 0.05, 0.035), W - El)]     # раструб манжеты
        T, K, A = P(f"thigh_{x}", 0), P(f"thigh_{x}", 1), P(f"calf_{x}", 1)
        pants += [C(f"leg_{x}", T, K, 0.052),
                  E(f"knee_{x}", K, (0.05, 0.048, 0.05)),
                  C(f"shin_{x}", K, A + Vector((0, 0, 0.02)), 0.048),
                  E(f"shin_{x}", K.lerp(A, 0.9), (0.06, 0.058, 0.06), A - K)]            # клёш
    return jacket, pants


def keep_largest_shell(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    seen, shells = set(), []
    for v in bm.verts:
        if v.index in seen:
            continue
        stack, shell = [v], []
        seen.add(v.index)
        while stack:
            x = stack.pop()
            shell.append(x)
            for e in x.link_edges:
                w = e.other_vert(x)
                if w.index not in seen:
                    seen.add(w.index)
                    stack.append(w)
        shells.append(shell)
    shells.sort(key=len)
    junk = [v for sh in shells[:-1] for v in sh]
    if junk:
        bmesh.ops.delete(bm, geom=junk, context='VERTS')
    # микро-рёбра (< 0.2 мм) после вокселизации Quadriflow считает ошибкой сетки
    short = [e for e in bm.edges if e.calc_length() < 2e-4]
    if short:
        bmesh.ops.collapse(bm, edges=short)
    bm.to_mesh(obj.data)
    bm.free()


def asymmetry(me):
    """Насколько сетка несимметрична по X: 95-й перцентиль расстояния от отражённых вершин до поверхности."""
    from mathutils.bvhtree import BVHTree
    verts = [v.co.copy() for v in me.vertices]
    tree = BVHTree.FromPolygons(verts, [p.vertices[:] for p in me.polygons])
    d = sorted(tree.find_nearest(Vector((-c.x, c.y, c.z)))[3] or 0.0 for c in verts[::3])
    return d[int(len(d) * 0.95)] if d else 0.0


def retopo_best(obj, faces, tries=4, good=0.004):
    """Quadriflow нестабилен на длинных тонких формах (может «съесть» ногу):
    пробуем несколько seed и оставляем самый симметричный результат."""
    src = obj.data.copy()
    best = None
    for k in range(tries):
        if k:
            old = obj.data
            obj.data = src.copy()
            bpy.data.meshes.remove(old)
        res = bpy.ops.object.quadriflow_remesh(target_faces=faces, use_preserve_sharp=False,
                                               use_mesh_symmetry=False, seed=SEED + k)
        if res != {'FINISHED'}:
            continue
        score = asymmetry(obj.data)
        if best is None or score < best[0]:
            if best is not None:
                bpy.data.meshes.remove(best[1])
            best = (score, obj.data.copy())
        if score < good:
            break
    bpy.data.meshes.remove(src)
    if best is None:
        return {'CANCELLED'}
    old = obj.data
    obj.data = best[1]
    bpy.data.meshes.remove(old)
    print(f"[bellhop] ретопология {obj.name}: {len(obj.data.polygons)} квадов, асимметрия {best[0] * 1000:.1f} мм")
    return {'FINISHED'}


def balls_to_mesh(name, balls, faces, resolution=0.006):
    """Метаболлы -> меш -> вокселизация -> Quadriflow."""
    mb = bpy.data.metaballs.new(f"{name}_MB")
    mb.resolution = mb.render_resolution = resolution
    mb.threshold = 0.6
    ob = bpy.data.objects.new(f"{name}_MB", mb)
    bpy.context.scene.collection.objects.link(ob)
    for b in balls:
        if b.kind == 'CAPSULE':
            e = mb.elements.new(type='CAPSULE')
            d = b.b - b.a
            e.co = (b.a + b.b) / 2
            e.radius = b.semi[0] / MB_K
            e.size_x = d.length / 2
            e.rotation = d.normalized().to_track_quat('X', 'Z')
        else:
            e = mb.elements.new(type='ELLIPSOID')
            m = max(b.semi)
            e.co = b.a
            e.radius = m / MB_K
            e.size_x, e.size_y, e.size_z = (s / m for s in b.semi)
            e.rotation = b.axis.to_track_quat('Z', 'Y')
        e.use_negative = b.neg
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.metaballs.remove(mb)
    obj = bpy.data.objects.new(f"Bellhop_{name}", me)
    bpy.context.scene.collection.objects.link(obj)
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    me.remesh_voxel_size = 0.005
    bpy.ops.object.voxel_remesh()
    keep_largest_shell(obj)          # убрать внутренние полости и обрезки — иначе Quadriflow откажется
    res = retopo_best(obj, faces)
    if res != {'FINISHED'}:                     # запасной вариант — Decimate
        mod = obj.modifiers.new("dec", 'DECIMATE')
        mod.ratio = min(1.0, faces * 2 / max(len(me.polygons), 1))
        bpy.ops.object.modifier_apply(modifier=mod.name)
    # страховка: согласованные нормали наружу (важно для выталкивания одежды и экспорта)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return obj


REGION_BONES = {
    "torso": ["pelvis", "spine_01", "spine_02", "spine_03"],
    "torso_up": ["spine_02", "spine_03", "clavicle_l", "clavicle_r", "neck"],
    "pelvis": ["pelvis", "spine_01", "thigh_l", "thigh_r"],
    "neck": ["spine_03", "neck", "head"],
}
for _x in "lr":
    REGION_BONES.update({
        f"shoulder_{_x}": ["spine_03", f"clavicle_{_x}", f"upperarm_{_x}"],
        f"arm_{_x}": [f"upperarm_{_x}", f"lowerarm_{_x}"],
        f"forearm_{_x}": [f"upperarm_{_x}", f"lowerarm_{_x}", f"hand_{_x}"],
        f"hand_{_x}": [f"lowerarm_{_x}", f"hand_{_x}"],
        f"leg_{_x}": ["pelvis", f"thigh_{_x}", f"calf_{_x}"],
        f"knee_{_x}": [f"thigh_{_x}", f"calf_{_x}"],
        f"shin_{_x}": [f"thigh_{_x}", f"calf_{_x}", f"foot_{_x}"],
        f"foot_{_x}": [f"calf_{_x}", f"foot_{_x}"],
    })


def region_weights(obj, balls, smooth_iters=6):
    """Веса: кандидаты-кости по 2 ближайшим мышцам, обратное расстояние до костей, сглаживание по сетке."""
    np = _np()
    me = obj.data
    co = np.array([v.co[:] for v in me.vertices])
    pos = [b for b in balls if not b.neg]
    names = list(BONES)
    idx = {n: i for i, n in enumerate(names)}
    # расстояние до «ядра» каждого метабола
    dist = np.empty((len(co), len(pos)))
    for j, b in enumerate(pos):
        a = np.array(b.a[:])
        if b.kind == 'CAPSULE':
            ab = np.array((b.b - b.a)[:])
            t = np.clip(((co - a) @ ab) / (ab @ ab), 0, 1)
            dist[:, j] = np.linalg.norm(a + t[:, None] * ab - co, axis=1) - b.semi[0]
        else:
            dist[:, j] = np.linalg.norm(co - a, axis=1) - max(b.semi)
    nearest = np.argsort(dist, axis=1)[:, :2]
    # расстояние до каждой кости
    bd = np.empty((len(co), len(names)))
    for i, n in enumerate(names):
        h, t, _ = BONES[n]
        h, ab = np.array(h[:]), np.array((t - h)[:])
        tt = np.clip(((co - h) @ ab) / (ab @ ab), 0, 1)
        bd[:, i] = np.linalg.norm(h + tt[:, None] * ab - co, axis=1)
    W = np.zeros((len(co), len(names)))
    for vi in range(len(co)):
        cand = set()
        for j in nearest[vi]:
            cand.update(REGION_BONES[pos[j].region])
        ci = [idx[c] for c in cand]
        w = 1.0 / (bd[vi, ci] ** 4 + 1e-9)
        W[vi, ci] = w / w.sum()
    # сглаживание весов по рёбрам сетки
    edges = np.array([e.vertices[:] for e in me.edges])
    for _ in range(smooth_iters):
        acc = np.zeros_like(W)
        cnt = np.zeros(len(co))
        np.add.at(acc, edges[:, 0], W[edges[:, 1]])
        np.add.at(acc, edges[:, 1], W[edges[:, 0]])
        np.add.at(cnt, edges[:, 0], 1)
        np.add.at(cnt, edges[:, 1], 1)
        W = 0.5 * W + 0.5 * acc / np.maximum(cnt, 1)[:, None]
    return [{names[i]: W[v, i] for i in np.argsort(-W[v])[:4] if W[v, i] > 0.01} for v in range(len(co))]


def transfer_weights(src_co, src_w, obj):
    """Одежда берёт веса с ближайших точек тела (как Data Transfer)."""
    from mathutils.kdtree import KDTree
    kd = KDTree(len(src_co))
    for i, c in enumerate(src_co):
        kd.insert(c, i)
    kd.balance()
    out = []
    for v in obj.data.vertices:
        acc = {}
        found = kd.find_n(v.co, 4)
        tot = 0.0
        for _, i, d in found:
            k = 1.0 / (d + 1e-4)
            tot += k
            for b, w in src_w[i].items():
                acc[b] = acc.get(b, 0.0) + w * k
        out.append({b: w / tot for b, w in acc.items()})
    return out


def obj_to_part(obj, name, material, weights, smooth=True, jitter_amount=0.0, hidden=None):
    """hidden — маска вершин, скрытых под одеждой: грани, у которых скрыты все вершины, удаляются."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    if jitter_amount:
        jitter(bm, jitter_amount)
    if hidden is not None:
        layer = bm.verts.layers.int.new("orig")
        for v in bm.verts:
            v[layer] = v.index
        bm.verts.ensure_lookup_table()
        dead = [f for f in bm.faces if all(hidden[v.index] for v in f.verts)]
        bmesh.ops.delete(bm, geom=dead, context='FACES_ONLY')
        loose = [v for v in bm.verts if not v.link_faces]
        bmesh.ops.delete(bm, geom=loose, context='VERTS')
        weights = [weights[v[layer]] for v in bm.verts]
        bm.verts.layers.int.remove(layer)
    me_name = obj.data.name
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.meshes.remove(bpy.data.meshes[me_name])
    return make_part(name, bm, material, sorted({b for w in weights for b in w}),
                     smooth=smooth, weights=weights)


def cut_mesh(obj, plane_co, plane_no, select=lambda co: True):
    """Отрезает часть меша по плоскости (сторона по нормали удаляется)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    geom = [f for f in bm.faces if select(f.calc_center_median())]
    geom = list({e for f in geom for e in f.edges}) + geom + list({v for f in geom for v in f.verts})
    bmesh.ops.bisect_plane(bm, geom=geom, plane_co=plane_co, plane_no=plane_no, clear_outer=True)
    bm.to_mesh(obj.data)
    bm.free()


def band(src_obj, name, material, predicate, offset, bones):
    """Золотая окантовка: копия полосы граней одежды, приподнятая над поверхностью."""
    bm = bmesh.new()
    bm.from_mesh(src_obj.data)
    bm.normal_update()
    keep = [f for f in bm.faces if predicate(f.calc_center_median())]
    drop = [f for f in bm.faces if f not in set(keep)]
    bmesh.ops.delete(bm, geom=drop, context='FACES')
    bm.normal_update()
    for v in bm.verts:
        v.co += v.normal * offset
    return make_part(name, bm, material, bones, smooth=True)


def push_outside(cloth, body_tree, gap=0.007, passes=3):
    """«Коллизия» ткани с телом: вершины одежды выталкиваются наружу кожи с зазором,
    затем ткань сглаживается (без возврата внутрь тела)."""
    bm = bmesh.new()
    bm.from_mesh(cloth.data)
    for it in range(passes):
        for v in bm.verts:
            loc, nrm, _, _ = body_tree.find_nearest(v.co)
            if loc is None:
                continue
            depth = (v.co - loc).dot(nrm)
            if depth < gap:
                v.co += nrm * (gap - depth)
        if it < passes - 2:
            bmesh.ops.smooth_vert(bm, verts=bm.verts, factor=0.5,
                                  use_axis_x=True, use_axis_y=True, use_axis_z=True)
        elif it == passes - 2:
            jitter(bm, CLOTH_JITTER * 0.6)          # «мятость» до последнего выталкивания
    bm.to_mesh(cloth.data)
    bm.free()


def raycast(obj, origin, direction):
    from mathutils.bvhtree import BVHTree
    tree = BVHTree.FromObject(obj, bpy.context.evaluated_depsgraph_get())
    hit, normal, _, _ = tree.ray_cast(Vector(origin), Vector(direction).normalized())
    return hit, normal


def build_body():
    """Анатомическое тело + униформа поверх него."""
    body_balls = anatomy_balls()
    body = balls_to_mesh("Body", body_balls, BODY_FACES)
    bw = region_weights(body, body_balls)
    body_co = [v.co.copy() for v in body.data.vertices]
    from mathutils.bvhtree import BVHTree
    body_tree = BVHTree.FromObject(body, bpy.context.evaluated_depsgraph_get())
    if not SHOW_CLOTHES:
        obj_to_part(body, "Body", "Skin", bw)

    # пальцы-когти (трубки) — анатомия ладони уже в теле
    for s, x in ((1, "l"), (-1, "r")):
        for fname, path in finger_paths(s).items():
            bm = bmesh.new()
            tube(bm, path, [0.016, 0.013, 0.009, 0.0], segs=6, sub=3)
            make_part(f"Finger_{fname}_{x}", bm, "Skin", [f"hand_{x}", f"{fname}_01_{x}", f"{fname}_02_{x}"],
                      smooth=True)
    if not SHOW_CLOTHES:
        return

    jacket_balls, pants_balls = clothes_balls()
    # ткань охватывает раздутую копию анатомии -> одежда повторяет крупные формы тела и не протыкается
    jacket_regions = ("torso", "torso_up", "pelvis", "shoulder", "arm", "forearm")
    pants_regions = ("pelvis", "leg", "knee", "shin")
    for b in body_balls:
        if b.neg:
            continue
        base = b.region.rsplit("_", 1)[0] if b.region[-2:] in ("_l", "_r") else b.region
        inflated = Ball(b.region, b.kind, b.a, b.b, semi=tuple(x + 0.01 for x in b.semi))
        inflated.axis = getattr(b, "axis", Vector((0, 0, 1)))
        if base in jacket_regions:
            jacket_balls.append(inflated)
        if base in pants_regions:
            pants_balls.append(inflated)
    jacket = balls_to_mesh("JacketSrc", jacket_balls, JACKET_FACES, resolution=0.008)
    cut_mesh(jacket, (0, 0, HEM_Z), (0, 0, -1))                                   # подол
    for s, x in ((1, "l"), (-1, "r")):
        El, W = P(f"upperarm_{x}", 1), P(f"lowerarm_{x}", 1)
        d = (W - El).normalized()
        cut_mesh(jacket, W - d * 0.03, d, select=lambda c, s=s: c.x * s > 0.2)    # манжеты
    pants = balls_to_mesh("PantsSrc", pants_balls, PANTS_FACES, resolution=0.008)
    cut_mesh(pants, (0, 0, 0.07), (0, 0, -1))
    push_outside(pants, body_tree, gap=0.009, passes=3)
    push_outside(jacket, body_tree, gap=0.009, passes=3)

    # детали поверх пиджака: окантовки, пуговицы, эполеты
    band(jacket, "HemTrim", "Gold", lambda c: c.z < HEM_Z + 0.022, 0.003, ["pelvis", "spine_01"])
    for s, x in ((1, "l"), (-1, "r")):
        El, W = P(f"upperarm_{x}", 1), P(f"lowerarm_{x}", 1)
        d = (W - El).normalized()
        cuff_c = W - d * 0.03

        def near_cuff(c, cc=cuff_c, d=d, s=s):
            return c.x * s > 0.2 and -0.03 < (c - cc).dot(d) < 0.0
        band(jacket, f"Cuff_{x}", "Gold", near_cuff, 0.003, [f"lowerarm_{x}"])

        top, _ = raycast(jacket, (0.2 * s, -0.04, 2.3), (0, 0, -1))
        if top:
            rot = Matrix.Rotation(math.radians(-8 * s), 3, 'Y')
            bm = bmesh.new()
            box(bm, top + Vector((0, 0, 0.006)), (0.12, 0.13, 0.014), rot)
            make_part(f"Epaulette_{x}", bm, "Jacket", [f"clavicle_{x}", f"upperarm_{x}"])
            bm = bmesh.new()
            box(bm, top + Vector((0, 0, 0.0)), (0.128, 0.138, 0.01), rot)
            make_part(f"EpauletteTrim_{x}", bm, "Gold", [f"clavicle_{x}", f"upperarm_{x}"])
    bm = bmesh.new()
    for x in (-0.05, 0.05):
        for z in (1.52, 1.62, 1.72):
            hit, n = raycast(jacket, (x, -1.0, z), (0, 1, 0))
            if hit:
                sphere(bm, hit + n * 0.002, 0.012, segs=8, rings=4, scale=(1, 0.5, 1))
    make_part("Buttons", bm, "Button", ["spine_01", "spine_02"], smooth=True)

    # стоячий воротник
    bm = bmesh.new()
    tube(bm, [(0, -0.075, 1.93), (0, -0.1, 2.0)], [(0.064, 0.058), (0.06, 0.054)], segs=14, sub=1)
    make_part("Collar", bm, "Jacket", ["spine_03", "neck"])
    bm = bmesh.new()
    tube(bm, [(0, -0.097, 1.99), (0, -0.101, 2.006)], [(0.062, 0.056), (0.061, 0.055)], segs=14, sub=1)
    make_part("CollarTrim", bm, "Gold", ["spine_03", "neck"])

    # кожа, полностью скрытая под одеждой, удаляется (как в игровых моделях): ничего не протыкает
    # при анимации и экономит полигоны. Полная анатомия — при SHOW_CLOTHES = False.
    dg = bpy.context.evaluated_depsgraph_get()
    cloth_trees = [BVHTree.FromObject(o, dg) for o in (jacket, pants)]
    body.data.update()
    hidden = []
    for v in body.data.vertices:
        hit = any(t.ray_cast(v.co - v.normal * 0.003, v.normal, 0.1)[0] is not None for t in cloth_trees)
        hidden.append(hit)
    obj_to_part(body, "Body", "Skin", bw, hidden=hidden)
    obj_to_part(jacket, "Jacket", "Jacket", transfer_weights(body_co, bw, jacket))
    obj_to_part(pants, "Pants", "Pants", transfer_weights(body_co, bw, pants))

    # большие плоские ботинки
    for s, x in ((1, "l"), (-1, "r")):
        ax = P(f"calf_{x}", 1).x
        bm = bmesh.new()
        tube(bm, [(ax, 0.085, 0.055), (ax, 0.03, 0.06), (ax, -0.08, 0.045), (ax, -0.19, 0.035)],
             [(0.050, 0.045), (0.058, 0.055), (0.060, 0.040), (0.045, 0.028)], segs=10, sub=2)
        for v in bm.verts:
            v.co.z = max(v.co.z, 0.0)
        make_part(f"Shoe_{x}", bm, "Shoes", [f"foot_{x}", f"calf_{x}"])


# ----------------------------------------------------------------- голова
# Голова строится как поверхность signed distance field (SDF): анатомические массы
# (свод черепа, затылок, челюсть, подбородок, скулы, надбровье) плавно сливаются,
# из них вычитаются виски, впалые щёки, глазницы, носовые щели и щель рта.
# Квад-сфера «натягивается» на эту поверхность лучами из центра, затем на неё
# наносится кожа: шум, морщины, складки у рта, шрам. Все координаты — локальные
# для головы (лицо смотрит в -Y, верх +Z), метры.

HEAD_RES = 34                   # плотность сетки головы (34 -> ~14k треугольников)
MOUTH_AXIS_Y = -0.03            # ось, вокруг которой изгибается улыбка
MOUTH_HALF_ANGLE = 1.38         # половина ширины улыбки, радианы (~79°)
JAW_PIVOT = Vector((0, 0.025, -0.035))


def head_matrix():
    return Matrix.Translation(HEAD_CENTER) @ Matrix.Rotation(math.radians(HEAD_TILT_DEG), 4, 'X')


def _np():
    import numpy as np
    return np


def _ell(p, c, r):
    """Приближённое расстояние до эллипсоида (Inigo Quilez)."""
    np = _np()
    q = (p - np.asarray(c)) / np.asarray(r)
    k0 = np.linalg.norm(q, axis=1)
    k1 = np.linalg.norm(q / np.asarray(r), axis=1)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)


def _smin(a, b, k):
    np = _np()
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b * (1 - h) + a * h - k * h * (1 - h)


def _cut(a, b, k):
    """Плавное вычитание b из a."""
    return -_smin(-a, b, k)


def mouth_frame(p):
    """Угол вокруг оси рта, радиус, линия смыкания губ и полувысота щели."""
    np = _np()
    x, y, z = p[:, 0], p[:, 1] - MOUTH_AXIS_Y, p[:, 2]
    theta = np.arctan2(x, -y)
    rho = np.hypot(x, y)
    tn = np.clip(np.abs(theta) / MOUTH_HALF_ANGLE, 0, 1.5)
    zc = -0.048 + 0.046 * tn ** 2                       # уголки улыбки вверх, к скулам
    half = 0.033 * np.clip(1 - 0.8 * tn ** 2, 0.07, 1)  # щель сужается к уголкам
    return theta, rho, zc, half


def face_radius(theta):
    """Радиус лицевой части челюсти (эллипс) под углом theta — по нему ставятся зубы."""
    np = _np()
    a, b = 0.086, 0.084
    return 1.0 / np.sqrt((np.sin(theta) / a) ** 2 + (np.cos(theta) / b) ** 2)


def skull_sdf(p, detail=True):
    np = _np()
    # --- массы
    d = _ell(p, (0, 0.012, 0.035), (0.083, 0.098, 0.098))            # свод черепа
    d = _smin(d, _ell(p, (0, 0.055, 0.0), (0.066, 0.06, 0.075)), 0.03)  # затылок
    d = _smin(d, _ell(p, (0, -0.036, -0.05), (0.086, 0.078, 0.058)), 0.025)  # челюсть
    d = _smin(d, _ell(p, (0, -0.062, -0.1), (0.034, 0.03, 0.024)), 0.02)  # острый подбородок
    for s in (1, -1):
        d = _smin(d, _ell(p, (0.062 * s, -0.058, 0.004), (0.03, 0.026, 0.02)), 0.014)  # скулы
        d = _smin(d, _ell(p, (0.068 * s, -0.01, -0.07), (0.018, 0.03, 0.02)), 0.018)  # углы челюсти
    d = _smin(d, _ell(p, (0, -0.072, 0.052), (0.074, 0.03, 0.02)), 0.016)  # надбровная дуга
    d = _smin(d, _ell(p, (0, -0.058, 0.098), (0.02, 0.03, 0.03)), 0.02)    # гребень на лбу
    if not detail:
        return d
    # --- вычитания
    for s in (1, -1):
        d = _cut(d, _ell(p, (0.088 * s, -0.012, 0.035), (0.022, 0.032, 0.03)), 0.018)    # виски
        d = _cut(d, _ell(p, (0.078 * s, -0.045, -0.035), (0.024, 0.034, 0.03)), 0.016)    # впалые щёки
        big = 1.08 if s > 0 else 1.0                                                     # асимметрия
        d = _cut(d, _ell(p, (0.036 * s, -0.094, 0.022),
                         (0.025 * big, 0.034, 0.022 * big)), 0.009)                     # глазницы
        d = _cut(d, _ell(p, (0.009 * s, -0.1, -0.008), (0.004, 0.012, 0.009)), 0.004)    # носовые щели
    theta, rho, zc, half = mouth_frame(p)
    r_in = face_radius(theta) - 0.02
    mouth = np.maximum(np.maximum(np.abs(p[:, 2] - zc) - half, r_in - rho),
                       (np.abs(theta) - MOUTH_HALF_ANGLE) * rho)
    d = _cut(d, mouth, 0.006)
    return d


def _skin_offset(p, n):
    """Смещение вдоль нормали: поры/шум, морщины на лбу, складки от рта, шрам."""
    from mathutils import noise
    x, y, z = p
    off = 0.0013 * noise.fractal(Vector((x * 60, y * 60, z * 60)), 0.8, 2.0, 4)
    off += 0.0006 * noise.noise(Vector((x * 220, y * 220, z * 220)))
    front = max(0.0, min(1.0, (-y - 0.04) / 0.04))
    # горизонтальные морщины на лбу
    if 0.05 < z < 0.11:
        m = math.sin((z + 0.002 * noise.noise(Vector((x * 30, 0, z * 30)))) * 520)
        off -= 0.0007 * max(m, 0) ** 3 * front * math.sin((z - 0.05) / 0.06 * math.pi)
    # складки от уголков рта к скулам
    theta = math.atan2(x, -(y - MOUTH_AXIS_Y))
    tn = abs(theta) / MOUTH_HALF_ANGLE
    for k, z0 in ((0.0, -0.018), (0.06, 0.0)):
        line_t = 1.0 - k - 0.15 * (z - z0) / 0.05
        dist = abs(tn - line_t) * 0.09
        if -0.025 < z - z0 < 0.06:
            off -= 0.0018 * math.exp(-(dist / 0.0035) ** 2) * front
    # диагональный шрам через правую глазницу на скулу
    a, b = Vector((-0.07, 0.075)), Vector((-0.012, -0.02))
    q = Vector((x, z))
    t = max(0.0, min(1.0, (q - a).dot(b - a) / (b - a).length_squared))
    ds = (a + (b - a) * t - q).length
    if y < -0.04:
        off -= 0.002 * math.exp(-(ds / 0.0022) ** 2)
        off += 0.0008 * math.exp(-((ds - 0.004) / 0.0015) ** 2)   # вздутые края шрама
    return off


def build_skull_mesh():
    np = _np()
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=HEAD_RES - 1, use_grid_fill=True)
    center = np.array((0.0, 0.0, -0.01))
    dirs = np.array([v.co.normalized()[:] for v in bm.verts])
    # марш лучей снаружи внутрь до первого пересечения + уточнение бисекцией
    r = np.full(len(dirs), 0.22)
    step = 0.0015
    inside = np.zeros(len(dirs), bool)
    for _ in range(200):
        d = skull_sdf(center + dirs * r[:, None])
        hit = (d < 0) & ~inside
        inside |= hit
        r = np.where(inside, r, r - step)
        if inside.all():
            break
    lo, hi = r, r + step
    for _ in range(14):
        mid = 0.5 * (lo + hi)
        d = skull_sdf(center + dirs * mid[:, None])
        lo = np.where(d < 0, mid, lo)
        hi = np.where(d < 0, hi, mid)
    pts = center + dirs * (0.5 * (lo + hi))[:, None]
    # нормали SDF для смещения кожи
    e = 0.0008
    grads = np.stack([skull_sdf(pts + np.array(o)) - skull_sdf(pts - np.array(o))
                      for o in ((e, 0, 0), (0, e, 0), (0, 0, e))], axis=1)
    grads /= np.maximum(np.linalg.norm(grads, axis=1, keepdims=True), 1e-9)
    local = []
    for v, p, n in zip(bm.verts, pts, grads):
        pv, nv = Vector(p), Vector(n)
        v.co = pv + nv * _skin_offset(pv, nv)
        local.append(v.co.copy())
    return bm, local


def jaw_weight(co):
    """Нижняя часть лица (ниже линии губ, спереди) следует за костью jaw."""
    np = _np()
    _, _, zc, _ = mouth_frame(np.array([co[:]]))
    below = max(0.0, min(1.0, (zc[0] - co.z) / 0.018 + 0.5))
    front = max(0.0, min(1.0, (0.035 - co.y) / 0.045))
    w = below * front
    return {"jaw": w, "head": 1.0 - w}


def build_teeth():
    """Длинные плотные зубы по дуге рта; есть сломанный и кривой зуб."""
    np = _np()
    rnd = random.Random(SEED + 3)
    upper, lower = bmesh.new(), bmesh.new()
    n_up = 19
    span = MOUTH_HALF_ANGLE * 0.93
    for row, bm, count, offset in (("u", upper, n_up, 0.0), ("l", lower, n_up - 1, 0.5)):
        for i in range(count):
            th = -span + (i + offset) * (2 * span / (n_up - 1))
            _, _, zc, half = mouth_frame(np.array([[math.sin(th) * 0.1, MOUTH_AXIS_Y - math.cos(th) * 0.1, 0]]))
            zc, half = float(zc[0]), float(half[0])
            rho = float(face_radius(np.array([th]))[0]) - 0.011
            tn = abs(th) / MOUTH_HALF_ANGLE
            width = 0.0062 * (1 - 0.35 * tn)
            sign = -1 if row == "u" else 1
            root_z = zc - sign * (half + 0.006)
            length = (half + 0.006) * (1.05 + rnd.uniform(-0.06, 0.08))
            if row == "u" and i == 4:
                length *= 0.55                                  # сломанный зуб
            lean = rnd.uniform(-0.12, 0.12) + (0.35 if (row == "l" and i == 10) else 0)  # кривой
            pos = lambda t, z: Vector((math.sin(th + lean * t * 0.05) * (rho - 0.002 * t),
                                       MOUTH_AXIS_Y - math.cos(th + lean * t * 0.05) * (rho - 0.002 * t), z))
            pts = [pos(t, root_z + sign * length * t) for t in (0.0, 0.35, 0.7, 0.9, 1.0)]
            ref = Vector((math.cos(th), math.sin(th), 0))
            tube(bm, pts, [(width, width * 0.6), (width * 1.05, width * 0.65), (width, width * 0.6),
                           (width * 0.7, width * 0.45), 0.0], segs=8, sub=1, ref=ref)
    return upper, lower


def build_eyes():
    """Светящиеся линзы на дне глазниц (положение ищется лучом по поверхности черепа)."""
    np = _np()
    bm = bmesh.new()
    center = np.array((0.0, 0.0, -0.01))
    for s in (1, -1):
        target = np.array((0.036 * s, -0.094, 0.022))
        d = (target - center) / np.linalg.norm(target - center)
        r = 0.2
        while skull_sdf((center + d * r)[None])[0] > 0 and r > 0.01:
            r -= 0.0005
        p = Vector(center + d * (r - 0.003))
        size = 0.0195 * (1.08 if s > 0 else 1.0)
        sphere(bm, p, size, segs=16, rings=8, scale=(1, 0.45, 0.9))
    return bm


def build_head():
    head_m = head_matrix()

    def finish(bm, name, mat_name, smooth=False):
        bmesh.ops.transform(bm, matrix=head_m, verts=bm.verts)
        make_part(name, bm, mat_name, ["head"], smooth)

    # детализированная голова: череп, челюсть, глазницы, рот, кожа (см. раздел «голова»)
    bm, local_co = build_skull_mesh()
    weights = [jaw_weight(co) for co in local_co]
    bmesh.ops.transform(bm, matrix=head_m, verts=bm.verts)
    make_part("Head", bm, "Skin", ["head", "jaw"], smooth=True, weights=weights)

    # зубы: верхний ряд — к голове, нижний — к челюсти
    upper, lower = build_teeth()
    for name, tbm, b in (("TeethUpper", upper, "head"), ("TeethLower", lower, "jaw")):
        bmesh.ops.transform(tbm, matrix=head_m, verts=tbm.verts)
        make_part(name, tbm, "Teeth", [b], smooth=True)

    # светящиеся линзы глубоко в глазницах
    bm = build_eyes()
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
    build_body()
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
