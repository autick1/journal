"""
Текстурирование модели коридорного из Tripo (STL без UV и цветов) -> игровой PBR-ассет.

Что делает:
  1. Импорт STL, ориентация (лицом в -Y, вверх +Z), масштаб в метры (рост 2.4 м).
  2. Ремонт сетки: STL от Tripo — «суп» из ~25 тыс. несвязанных кусков со щелями.
     Solidify закрывает щели -> вокселизация -> внешняя оболочка -> Shrinkwrap обратно
     на исходную поверхность (детали сохраняются) -> чистка провалов и вывернутых граней.
     Результат: цельная High-копия (~1.1 млн граней) — источник для запекания.
  3. Игровая Low-копия: Decimate до ~40 тыс. треугольников + UV-развёртка.
  4. Разметка областей (по положению и нормалям): фуражка, латунная лента, козырёк,
     лицо, зубы, глаза, пиджак, латунь (манжеты, подол, эполеты, пуговицы), кисти, когти,
     брюки, обувь. Для каждой — процедурный PBR-материал.
  5. Запекание в текстуры (Cycles): BaseColor, Roughness, Metallic, Normal (детали с High),
     AO (с High), Emission (глаза). Итоговый материал — одна PBR-текстурная сборка.
  6. Сохранение .blend (текстуры упакованы), PNG-текстур и экспорт GLB/FBX.

Запуск (терминал):
  blender --background --python texture_tripo.py -- model.stl out_dir [разрешение=2048]
Внутри Blender: поменяй STL_PATH / OUT_DIR ниже и запусти во вкладке Scripting.
"""

import math
import os
import sys
import time

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector

STL_PATH = "model.stl"
OUT_DIR = "BellhopTripo_out"
TEX_RES = 2048
HEIGHT = 2.4                     # итоговый рост, м
LOW_TRIS = 40000
VOXEL = 0.0035
SOLID = 0.012                    # толщина Solidify для закрытия щелей
AO_DISTANCE = 0.15               # радиус AO, м
NORMAL_SMOOTH = 6                # сглаживание High перед запеканием нормалей
FACING = 'POS_X'                 # куда смотрит лицо в исходном STL (у Tripo-модели: +X)

# Зоны (метры, после ориентации). Подобраны по ортогональным видам модели.
Z_SHOE = 0.155
Z_HEM = 1.55                     # низ пиджака
HEM_BAND = 0.03                  # латунная кайма над подолом
Z_CUFF = (1.055, 1.13)           # латунные манжеты
Z_CLAW = 0.70                    # ниже — когти
Z_HAT = 2.19                     # низ фуражки
HAT_BAND = 0.045                 # латунная лента над низом фуражки
ARM_X = 0.28                     # |x| больше — рука (выше z=1.2)
ARM_X_LOW = 0.35                 # ниже z=1.2 (кисти рядом с ногами)
NECK_Y = -0.22                   # впереди этой плоскости — лицо, позади — воротник
MOUTH_Z = (1.965, 2.095)
VISOR_Y = -0.47                  # козырёк — всё фуражечное впереди этой плоскости
EYE_Z = 2.158
EYE_X = (-0.026, 0.078)
EYE_R = 0.021

MATERIALS = {   # имя: (цвет, roughness, metallic)
    "RedFabric":  ((0.13, 0.012, 0.016), 0.82, 0.0),
    "DarkFabric": ((0.025, 0.010, 0.010), 0.88, 0.0),
    "OldBrass":   ((0.62, 0.42, 0.17), 0.36, 1.0),
    "Skin":       ((0.020, 0.008, 0.006), 0.50, 0.0),
    "Teeth":      ((0.80, 0.76, 0.66), 0.38, 0.0),
    "Claws":      ((0.050, 0.035, 0.025), 0.32, 0.0),
    "Leather":    ((0.030, 0.014, 0.010), 0.45, 0.0),
    "Eyes":       ((1.0, 0.97, 0.9), 0.30, 0.0),
}


def log(*a):
    print("[tripo]", *a, flush=True)


def activate(o):
    for x in bpy.context.selected_objects:
        x.select_set(False)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)


def apply_mod(o, m):
    activate(o)
    bpy.ops.object.modifier_apply(modifier=m.name)


# ----------------------------------------------------------------- 1. импорт
def import_stl(path):
    bpy.ops.wm.stl_import(filepath=path)
    o = bpy.context.selected_objects[0]
    o.name = "Tripo_Source"
    co = np.empty(len(o.data.vertices) * 3)
    o.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    k = HEIGHT / (co[:, 2].max() - co[:, 2].min())
    rot = {'POS_X': -90, 'NEG_X': 90, 'POS_Y': 180, 'NEG_Y': 0}[FACING]
    o.data.transform(Matrix.Rotation(math.radians(rot), 4, 'Z') @ Matrix.Diagonal((k, k, k, 1)))
    co = np.empty(len(o.data.vertices) * 3)
    o.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    o.data.transform(Matrix.Translation((0, 0, -co[:, 2].min())))
    log(f"импорт: {len(o.data.polygons)} треугольников, масштаб {k:.4f}")
    return o


# ----------------------------------------------------------------- 2. ремонт
def shells_of(bm):
    bm.verts.ensure_lookup_table()
    seen, shells = set(), []
    for v in bm.verts:
        if v.index in seen:
            continue
        st, sh = [v], []
        seen.add(v.index)
        while st:
            x = st.pop()
            sh.append(x)
            for e in x.link_edges:
                w = e.other_vert(x)
                if w.index not in seen:
                    seen.add(w.index)
                    st.append(w)
        shells.append(sh)
    return shells


def keep_outer(o):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    shells = shells_of(bm)

    def extent(sh):
        c = np.array([v.co[:] for v in sh])
        return np.prod(c.max(0) - c.min(0) + 1e-6)
    shells.sort(key=extent, reverse=True)
    bmesh.ops.delete(bm, geom=[v for sh in shells[1:] for v in sh], context='VERTS')
    bm.to_mesh(o.data)
    bm.free()


def drop_tiny_shells(o, min_verts):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    junk = [v for sh in shells_of(bm) if len(sh) < min_verts for v in sh]
    if junk:
        bmesh.ops.delete(bm, geom=junk, context='VERTS')
    bm.to_mesh(o.data)
    bm.free()


def _neighbors_avg(co, e):
    acc = np.zeros_like(co)
    cnt = np.zeros(len(co))
    np.add.at(acc, e[:, 0], co[e[:, 1]])
    np.add.at(acc, e[:, 1], co[e[:, 0]])
    np.add.at(cnt, e[:, 0], 1)
    np.add.at(cnt, e[:, 1], 1)
    return acc / np.maximum(cnt, 1)[:, None]


def fix_pits(o, iters=14):
    me = o.data
    co = np.array([v.co[:] for v in me.vertices])
    e = np.array([ed.vertices[:] for ed in me.edges])
    for _ in range(iters):
        avg = _neighbors_avg(co, e)
        dev = np.linalg.norm(co - avg, axis=1)
        bad = dev > max(0.0009, np.median(dev) * 3)
        co[bad] = avg[bad]
    me.vertices.foreach_set("co", co.ravel())
    me.update()


def unfold(o, fn0, iters=12):
    me = o.data
    quads = np.array([p.vertices[:3] for p in me.polygons])
    co = np.array([v.co[:] for v in me.vertices])
    e = np.array([ed.vertices[:] for ed in me.edges])
    for _ in range(iters):
        a, b, c = co[quads[:, 0]], co[quads[:, 1]], co[quads[:, 2]]
        n = np.cross(b - a, c - a)
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        flip = (n * fn0).sum(1) < -0.1
        if not flip.any():
            break
        mask = np.zeros(len(co), bool)
        mask[np.unique(quads[flip].ravel())] = True
        ext = mask.copy()
        ext[e[mask[e[:, 0]], 1]] = True
        ext[e[mask[e[:, 1]], 0]] = True
        co[ext] = _neighbors_avg(co, e)[ext]
    me.vertices.foreach_set("co", co.ravel())
    me.update()


def repair(src):
    t = time.time()
    o = src.copy()
    o.data = src.data.copy()
    o.name = "Tripo_High"
    bpy.context.scene.collection.objects.link(o)
    m = o.modifiers.new("solid", 'SOLIDIFY')
    m.thickness, m.offset = SOLID, 0.0
    apply_mod(o, m)
    activate(o)
    o.data.remesh_voxel_size = VOXEL
    bpy.ops.object.voxel_remesh()
    keep_outer(o)
    o.data.update()
    fn0 = np.empty(len(o.data.polygons) * 3)
    o.data.polygons.foreach_get("normal", fn0)
    fn0 = fn0.reshape(-1, 3)
    sw = o.modifiers.new("sw", 'SHRINKWRAP')
    sw.target, sw.wrap_method = src, 'NEAREST_SURFACEPOINT'
    apply_mod(o, sw)
    fix_pits(o)
    unfold(o, fn0)
    bm = bmesh.new()                                    # нормали наружу — иначе normal map «вывернется»
    bm.from_mesh(o.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(o.data)
    bm.free()
    for p in o.data.polygons:
        p.use_smooth = True
    log(f"ремонт: High {len(o.data.polygons)} граней за {time.time() - t:.0f} с")
    return o


# ----------------------------------------------------------------- 3. low-poly + UV
def make_low(high):
    """Игровая сетка: High -> сглаживание (убирает шум Tripo, тонкие пальцы и когти остаются)
    -> Decimate до LOW_TRIS -> UV. Мелкие детали High переходят в normal map.
    (QuadriFlow тут не годится: «съедает» длинные тонкие пальцы.)"""
    o = high.copy()
    o.data = high.data.copy()
    o.name = "Bellhop_Tripo"
    bpy.context.scene.collection.objects.link(o)
    sm = o.modifiers.new("smooth", 'SMOOTH')
    sm.iterations, sm.factor = 10, 0.6
    apply_mod(o, sm)
    tris_now = sum(len(p.vertices) - 2 for p in o.data.polygons)
    d = o.modifiers.new("dec", 'DECIMATE')
    d.ratio = LOW_TRIS / tris_now
    d.use_collapse_triangulate = True
    apply_mod(o, d)
    sm = o.modifiers.new("relax", 'SMOOTH')                 # выровнять треугольники после Decimate
    sm.iterations, sm.factor = 2, 0.3
    apply_mod(o, sm)
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(o.data)
    bm.free()
    for p in o.data.polygons:
        p.use_smooth = True
    unwrap(o)
    log(f"low-poly: {sum(len(p.vertices) - 2 for p in o.data.polygons)} треугольников, UV готова")
    return o


def make_proxy(high):
    """Чистый посредник: вокселизация High (замкнутая, без складок проекции)."""
    o = high.copy()
    o.data = high.data.copy()
    o.name = "Tripo_Proxy"
    bpy.context.scene.collection.objects.link(o)
    activate(o)
    o.data.remesh_voxel_size = 0.006
    bpy.ops.object.voxel_remesh()
    sm = o.modifiers.new("smooth", 'SMOOTH')
    sm.iterations, sm.factor = 2, 0.5
    apply_mod(o, sm)
    o.hide_render = True
    return o


def vertex_ao(low, proxy, rays=24, dist=None):
    """AO по вершинам low: лучи по полусфере над ближайшей точкой чистого посредника."""
    from mathutils.bvhtree import BVHTree
    dist = dist or AO_DISTANCE
    tree = BVHTree.FromObject(proxy, bpy.context.evaluated_depsgraph_get())
    rng = np.random.default_rng(1)
    d = rng.normal(size=(rays, 3))
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    dirs = [Vector(v) for v in d]
    ao = np.ones(len(low.data.vertices))
    for i, v in enumerate(low.data.vertices):
        loc, nrm, _, _ = tree.find_nearest(v.co)
        if loc is None:
            continue
        origin = loc + nrm * 0.003
        hits = total = 0
        for r in dirs:
            if r.dot(nrm) < 0:
                r = -r
            w = r.dot(nrm)
            total += w
            if tree.ray_cast(origin, r, dist)[0] is not None:
                hits += w
        ao[i] = 1.0 - hits / max(total, 1e-6)
    attr = low.data.color_attributes.new("AO", 'FLOAT_COLOR', 'POINT')
    attr.data.foreach_set("color", np.repeat(ao, 4).astype(np.float32) * np.tile([1, 1, 1, 0], len(ao)) +
                          np.tile([0, 0, 0, 1], len(ao)))
    log(f"AO по вершинам: среднее {ao.mean():.2f}")


def unwrap(o):
    """UV: xatlas (если установлен — pip install xatlas в Python Blender), иначе Smart UV.
    На сетке после Decimate Smart UV дробит развёртку на тысячи микроостровов."""
    me = o.data
    try:
        import xatlas
    except ImportError:
        xatlas = None
    if xatlas is not None and all(len(p.vertices) == 3 for p in me.polygons):
        V = np.empty(len(me.vertices) * 3, np.float32)
        me.vertices.foreach_get("co", V)
        F = np.empty(len(me.polygons) * 3, np.uint32)
        me.polygons.foreach_get("vertices", F)
        atlas = xatlas.Atlas()
        atlas.add_mesh(V.reshape(-1, 3), F.reshape(-1, 3))
        po = xatlas.PackOptions()
        po.resolution, po.padding, po.bilinear = TEX_RES, 4, True
        atlas.generate(xatlas.ChartOptions(), po)
        _, ind, uvs = atlas[0]
        layer = me.uv_layers.new(name="UVMap") if not me.uv_layers else me.uv_layers[0]
        layer.data.foreach_set("uv", uvs[ind.ravel()].ravel().astype(np.float32))
        log(f"UV (xatlas): {atlas.chart_count} карт, заполнение {atlas.utilization:.0%}")
        return
    activate(o)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(72), island_margin=0.004, area_weight=0.7)
    bpy.ops.uv.pack_islands(margin=0.004)
    bpy.ops.object.mode_set(mode='OBJECT')
    log("UV (Smart UV Project; для лучшей развёртки установи xatlas)")


# ----------------------------------------------------------------- 4. разметка
def classify(c, n, front_y):
    """Область по центру грани c и нормали n. front_y(z) — передняя граница корпуса."""
    x, y, z = c
    ax = abs(x)
    if z < Z_SHOE:
        return "Leather"
    if z > Z_HAT:                                                # фуражка
        if y < VISOR_Y and z < Z_HAT + 0.04:
            return "Leather"                                     # козырёк выступает над лицом
        if z < Z_HAT + HAT_BAND:
            return "OldBrass"                                    # лента
        return "RedFabric"
    if z > 1.9 and y < NECK_Y and ax < 0.17:                     # лицо
        for ex in EYE_X:
            if (x - ex) ** 2 + (z - EYE_Z) ** 2 < EYE_R ** 2 and n.y < -0.3:
                return "Eyes"
        if MOUTH_Z[0] < z < MOUTH_Z[1] and y < front_face(z) + 0.035 and ax < 0.09:
            return "Teeth"
        return "Skin"
    arm = z > 0.5 and ((z < 1.2 and ax > ARM_X_LOW) or (z >= 1.2 and ax > ARM_X))
    if arm:
        if z < Z_CLAW:
            return "Claws"
        if z < Z_CUFF[0]:
            return "Skin"                                        # кисти
        if z < Z_CUFF[1]:
            return "OldBrass"                                    # манжеты
        return "RedFabric"
    if z >= Z_HEM:
        if z < Z_HEM + HEM_BAND:
            return "OldBrass"                                    # кайма подола
        return "RedFabric"
    return "DarkFabric"                                          # брюки


_FACE_FRONT = {}


def front_face(z):
    k = round(z, 2)
    return _FACE_FRONT.get(k, -0.4)


def assign_regions(low):
    me = low.data
    names = list(MATERIALS)
    me.materials.clear()
    for nm in names:
        me.materials.append(region_material(nm))
    cen = np.empty(len(me.polygons) * 3)
    me.polygons.foreach_get("center", cen)
    cen = cen.reshape(-1, 3)
    nrm = np.empty(len(me.polygons) * 3)
    me.polygons.foreach_get("normal", nrm)
    nrm = nrm.reshape(-1, 3)
    # передняя граница корпуса и лица по высоте (для пуговиц и зубов)
    fronts = {}
    for zk in np.arange(0, 2.5, 0.01):
        sel = (np.abs(cen[:, 2] - zk) < 0.01) & (np.abs(cen[:, 0]) < 0.12)
        if sel.any():
            fronts[round(zk, 2)] = cen[sel, 1].min()
    _FACE_FRONT.update(fronts)

    def front_y(z):
        return fronts.get(round(z, 2), -0.15)
    idx = np.array([names.index(classify(Vector(c), Vector(n), front_y)) for c, n in zip(cen, nrm)])
    me.polygons.foreach_set("material_index", idx)
    me.update()
    counts = {nm: int((idx == i).sum()) for i, nm in enumerate(names)}
    log("разметка:", counts)


def region_material(name):
    """Процедурный PBR-материал области (то, что запекается в текстуры)."""
    mat = bpy.data.materials.new(f"R_{name}")
    if bpy.app.version < (5, 0):
        mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    bsdf = nodes.get("Principled BSDF")
    color, rough, metal = MATERIALS[name]
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    coord = nodes.new("ShaderNodeTexCoord")

    def noise(scale, detail=4.0):
        n = nodes.new("ShaderNodeTexNoise")
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        links.new(coord.outputs["Object"], n.inputs["Vector"])
        return n

    def ramp(src, c0, c1, p0=0.35, p1=0.65):
        r = nodes.new("ShaderNodeValToRGB")
        r.color_ramp.elements[0].position, r.color_ramp.elements[0].color = p0, (*c0, 1)
        r.color_ramp.elements[1].position, r.color_ramp.elements[1].color = p1, (*c1, 1)
        links.new(src, r.inputs["Fac"])
        return r

    k = lambda c, f: tuple(min(1.0, x * f) for x in c)
    if name in ("RedFabric", "DarkFabric"):
        n = noise(14.0, 6.0)
        links.new(ramp(n.outputs["Fac"], k(color, 0.55), k(color, 1.3)).outputs["Color"], bsdf.inputs["Base Color"])
    elif name == "OldBrass":
        n = noise(35.0, 8.0)
        links.new(ramp(n.outputs["Fac"], (0.15, 0.10, 0.045), color, 0.36, 0.62).outputs["Color"],
                  bsdf.inputs["Base Color"])
        links.new(ramp(n.outputs["Fac"], (0.7,) * 3, (0.3,) * 3, 0.36, 0.62).outputs["Color"],
                  bsdf.inputs["Roughness"])
    elif name == "Skin":
        n = noise(22.0, 6.0)
        links.new(ramp(n.outputs["Fac"], k(color, 0.6), (0.05, 0.018, 0.013)).outputs["Color"],
                  bsdf.inputs["Base Color"])
    elif name == "Teeth":
        n = noise(50.0, 4.0)
        links.new(ramp(n.outputs["Fac"], (0.6, 0.53, 0.36), color, 0.3, 0.7).outputs["Color"],
                  bsdf.inputs["Base Color"])
    elif name in ("Claws", "Leather"):
        n = noise(60.0, 5.0)
        links.new(ramp(n.outputs["Fac"], k(color, 0.7), k(color, 1.4)).outputs["Color"], bsdf.inputs["Base Color"])
    return mat


# ----------------------------------------------------------------- 5. запекание
def new_image(name, color_space="sRGB"):
    img = bpy.data.images.new(name, TEX_RES, TEX_RES, alpha=False, float_buffer=False)
    img.colorspace_settings.name = color_space
    return img


def set_bake_target(obj, img):
    for mat in obj.data.materials:
        nodes = mat.node_tree.nodes
        node = nodes.get("BAKE_TARGET") or nodes.new("ShaderNodeTexImage")
        node.name = "BAKE_TARGET"
        node.image = img
        nodes.active = node


def bake(obj, kind, img, high=None, **kw):
    set_bake_target(obj, img)
    sc = bpy.context.scene
    activate(obj)
    if high is not None:
        high.select_set(True)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
    t = time.time()
    sc.render.bake.use_selected_to_active = high is not None
    sc.render.bake.cage_extrusion = 0.02
    sc.render.bake.max_ray_distance = 0.04
    sc.render.bake.margin = 3
    bpy.ops.object.bake(type=kind, **kw)
    log(f"запечено {img.name} ({kind}) за {time.time() - t:.0f} с")


def swap_to_emission(obj, source):
    """Для запекания Metallic/Emission: подаём значение в Emission и печём EMIT."""
    saved = []
    for mat in obj.data.materials:
        nt = mat.node_tree
        bsdf = nt.nodes.get("Principled BSDF")
        emc = bsdf.inputs["Emission Color"] if "Emission Color" in bsdf.inputs else bsdf.inputs["Emission"]
        ems = bsdf.inputs["Emission Strength"]
        saved.append((emc, tuple(emc.default_value), ems, ems.default_value))
        name = mat.name[2:]
        if source == "metallic":
            v = MATERIALS[name][2]
            emc.default_value = (v, v, v, 1)
            ems.default_value = 1.0
        else:   # emission: только глаза
            emc.default_value = (*MATERIALS[name][0], 1) if name == "Eyes" else (0, 0, 0, 1)
            ems.default_value = 1.0
    return saved


def ao_to_emission(obj):
    saved = []
    for mat in obj.data.materials:
        nt = mat.node_tree
        out = nt.nodes.get("Material Output")
        old = [(l.from_socket, l.to_socket) for l in out.inputs["Surface"].links]
        attr = nt.nodes.new("ShaderNodeAttribute")
        attr.attribute_name = "AO"
        em = nt.nodes.new("ShaderNodeEmission")
        nt.links.new(attr.outputs["Color"], em.inputs["Color"])
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        saved.append((nt, old, attr, em))
    return saved


def restore_links(saved):
    for nt, old, attr, em in saved:
        nt.nodes.remove(attr)
        nt.nodes.remove(em)
        for a, b in old:
            nt.links.new(a, b)


def zero_metallic(obj):
    saved = []
    for mat in obj.data.materials:
        inp = mat.node_tree.nodes.get("Principled BSDF").inputs["Metallic"]
        saved.append((inp, inp.default_value, None, None))
        inp.default_value = 0.0
    return saved


def restore(saved):
    for emc, c, ems, s in saved:
        emc.default_value = c
        if ems is not None:
            ems.default_value = s


def fix_backfacing_normals(img):
    """Луч попал в микроскладку High с вывернутой нормалью -> в касательном пространстве
    нормаль «смотрит внутрь» (синий канал < 0.5). Такого у поверхности не бывает: разворачиваем."""
    a = np.array(img.pixels[:], np.float32).reshape(-1, 4)
    back = a[:, 2] < 0.5
    a[back, :3] = 1.0 - a[back, :3]
    img.pixels = a.ravel()
    log(f"normal map: исправлено {int(back.sum())} текселей с вывернутой нормалью")


def bake_all(low, high, out_dir):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = 16
    maps = {}
    sc.render.bake.use_pass_direct = False
    sc.render.bake.use_pass_indirect = False
    sc.render.bake.use_pass_color = True
    maps["BaseColor"] = new_image("Bellhop_BaseColor")
    saved = zero_metallic(low)                       # у металла нет диффуза -> латунь запеклась бы чёрной
    bake(low, 'DIFFUSE', maps["BaseColor"], pass_filter={'COLOR'})
    restore(saved)
    maps["Roughness"] = new_image("Bellhop_Roughness", "Non-Color")
    bake(low, 'ROUGHNESS', maps["Roughness"])
    maps["Metallic"] = new_image("Bellhop_Metallic", "Non-Color")
    saved = swap_to_emission(low, "metallic")
    bake(low, 'EMIT', maps["Metallic"])
    restore(saved)
    maps["Emission"] = new_image("Bellhop_Emission")
    saved = swap_to_emission(low, "emission")
    bake(low, 'EMIT', maps["Emission"])
    restore(saved)
    maps["Normal"] = new_image("Bellhop_Normal", "Non-Color")
    sm = high.modifiers.new("bake_smooth", 'SMOOTH')    # убрать микрошум Tripo, оставить формы
    sm.iterations, sm.factor = NORMAL_SMOOTH, 0.6
    bake(low, 'NORMAL', maps["Normal"], high=high, normal_space='TANGENT')
    high.modifiers.remove(sm)
    fix_backfacing_normals(maps["Normal"])
    maps["AO"] = new_image("Bellhop_AO", "Non-Color")
    sc.cycles.samples = 32
    saved = ao_to_emission(low)                     # AO посчитан по вершинам (vertex_ao)
    bake(low, 'EMIT', maps["AO"])
    restore_links(saved)
    os.makedirs(out_dir, exist_ok=True)
    for k, img in maps.items():
        img.filepath_raw = os.path.join(out_dir, f"Bellhop_{k}.png")
        img.file_format = 'PNG'
        img.save()
    return maps


# ----------------------------------------------------------------- 6. итоговый материал
def final_material(low, maps):
    mat = bpy.data.materials.new("M_Bellhop_Tripo")
    if bpy.app.version < (5, 0):
        mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    bsdf = nodes.get("Principled BSDF")

    def tex(key, x, y):
        n = nodes.new("ShaderNodeTexImage")
        n.image = maps[key]
        n.location = (x, y)
        return n
    base, ao = tex("BaseColor", -700, 300), tex("AO", -700, 50)
    mix = nodes.new("ShaderNodeMix")
    mix.data_type = 'RGBA'
    mix.blend_type = 'MULTIPLY'
    mix.inputs["Factor"].default_value = 0.8
    links.new(base.outputs["Color"], mix.inputs[6])
    links.new(ao.outputs["Color"], mix.inputs[7])
    links.new(mix.outputs[2], bsdf.inputs["Base Color"])
    links.new(tex("Roughness", -700, -200).outputs["Color"], bsdf.inputs["Roughness"])
    links.new(tex("Metallic", -700, -450).outputs["Color"], bsdf.inputs["Metallic"])
    nmap = nodes.new("ShaderNodeNormalMap")
    links.new(tex("Normal", -700, -700).outputs["Color"], nmap.inputs["Color"])
    links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    em = tex("Emission", -700, -950)
    emc = "Emission Color" if "Emission Color" in bsdf.inputs else "Emission"
    links.new(em.outputs["Color"], bsdf.inputs[emc])
    bsdf.inputs["Emission Strength"].default_value = 10.0
    # AO отдельно для glTF (occlusion) — exporter берёт glTF Material Output, если есть
    low.data.materials.clear()
    low.data.materials.append(mat)
    for p in low.data.polygons:
        p.material_index = 0
    return mat


def main():
    stl, out, res = STL_PATH, OUT_DIR, TEX_RES
    if "--" in sys.argv:
        a = sys.argv[sys.argv.index("--") + 1:]
        if a:
            stl = a[0]
        if len(a) > 1:
            out = a[1]
        if len(a) > 2:
            res = int(a[2])
    globals()["TEX_RES"] = res
    out = os.path.abspath(out)
    os.makedirs(out, exist_ok=True)
    t0 = time.time()
    src = import_stl(stl)
    high = repair(src)
    bpy.data.objects.remove(src, do_unlink=True)
    low = make_low(high)
    proxy = make_proxy(high)
    vertex_ao(low, proxy)
    bpy.data.objects.remove(proxy, do_unlink=True)
    assign_regions(low)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "Bellhop_Tripo_regions.blend"))
    maps = bake_all(low, high, os.path.join(out, "textures"))
    final_material(low, maps)
    high.hide_set(True)
    high.hide_render = True
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "Bellhop_Tripo.blend"))
    activate(low)
    bpy.ops.export_scene.gltf(filepath=os.path.join(out, "Bellhop_Tripo.glb"), export_format='GLB',
                              use_selection=True, export_apply=True)
    bpy.ops.export_scene.fbx(filepath=os.path.join(out, "Bellhop_Tripo.fbx"), use_selection=True,
                             path_mode='COPY', embed_textures=True, add_leaf_bones=False)
    log(f"готово за {time.time() - t0:.0f} с -> {out}")


if __name__ == "__main__":
    main()
