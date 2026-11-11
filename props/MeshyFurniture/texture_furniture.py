"""
Текстуры для мебели из Meshy (GLB без UV и цветов): кресло, диван, кровать.

Пайплайн:
  1. Импорт, масштаб в реальные метры, ориентация (лицом в -Y, вверх +Z).
  2. Игровая сетка: Decimate до ~19 000 треугольников (лимит Roblox MeshPart — 20 000) + UV (xatlas).
  3. Разметка «дерево / ткань» по форме:
       chair/sofa — низ (ножки, царга) и рамки по краю силуэта на видах спереди/сзади/сбоку — дерево,
                    внутренние поля, подушки, подлокотники — ткань (бархат);
       bed        — постель внутри каркаса — ткань (лён), каркас — дерево.
  4. Запекание (Cycles): BaseColor (с AO), Roughness, Normal (детали с исходной сетки), AO.
  5. Экспорт: GLB с текстурами, FBX + PNG-карты для Roblox SurfaceAppearance, .blend.

Запуск: blender --background --python texture_furniture.py -- model.glb out_dir chair|sofa|bed [1024]
"""

import math
import os
import sys
import time

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector

LOW_TRIS = 19000
HEAD_ZONE = 0.30                # кровать: доля длины у изголовья — подушки и простыня (белые)
CELL = 0.01                     # шаг растра силуэтов, м

PRESETS = {
    #         размер (ось, м)    низ-дерево (доля высоты)  ширина рамки, м   ткань
    "chair": dict(size=("z", 1.10), base=0.235, frame=0.045, fabric="velvet"),
    "sofa":  dict(size=("x", 2.10), base=0.20, frame=0.045, fabric="velvet"),
    "bed":   dict(size=("y", 2.20), base=None, frame=None, fabric="linen"),
}
COLORS = {
    "wood":   ((0.10, 0.032, 0.020), (0.035, 0.011, 0.007), 0.45),
    "velvet": ((0.16, 0.007, 0.012), (0.065, 0.004, 0.007), 0.68),
    "linen":  ((0.80, 0.77, 0.70), (0.62, 0.59, 0.53), 0.85),
    "duvet":  ((0.20, 0.012, 0.022), (0.10, 0.006, 0.012), 0.75),
}


def log(*a):
    print("[furn]", *a, flush=True)


def activate(o):
    for x in bpy.context.selected_objects:
        x.select_set(False)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)


# ----------------------------------------------------------------- импорт
def import_model(path, preset):
    bpy.ops.import_scene.gltf(filepath=path)
    o = next(x for x in bpy.data.objects if x.type == 'MESH')
    activate(o)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    o.parent = None
    co = np.empty(len(o.data.vertices) * 3)
    o.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    axis, size = preset["size"]
    ai = "xyz".index(axis)
    k = size / (co[:, ai].max() - co[:, ai].min())
    c = (co.max(0) + co.min(0)) / 2
    o.data.transform(Matrix.Diagonal((k, k, k, 1)) @ Matrix.Translation((-c[0], -c[1], -co[:, 2].min())))
    o.data.update()
    o.name = "High"
    return o


def make_low(high, name):
    o = high.copy()
    o.data = high.data.copy()
    o.name = o.data.name = name
    bpy.context.scene.collection.objects.link(o)
    d = o.modifiers.new("dec", 'DECIMATE')
    d.ratio = LOW_TRIS / len(o.data.polygons)
    d.use_collapse_triangulate = True
    activate(o)
    bpy.ops.object.modifier_apply(modifier=d.name)
    for p in o.data.polygons:
        p.use_smooth = True
    unwrap(o)
    return o


def unwrap(o, res=2048):
    me = o.data
    try:
        import xatlas
    except ImportError:
        xatlas = None
    if xatlas is not None:
        V = np.empty(len(me.vertices) * 3, np.float32)
        me.vertices.foreach_get("co", V)
        F = np.empty(len(me.polygons) * 3, np.uint32)
        me.polygons.foreach_get("vertices", F)
        atlas = xatlas.Atlas()
        atlas.add_mesh(V.reshape(-1, 3), F.reshape(-1, 3))
        po = xatlas.PackOptions()
        po.resolution, po.padding, po.bilinear = res, 4, True
        atlas.generate(xatlas.ChartOptions(), po)
        _, ind, uvs = atlas[0]
        layer = me.uv_layers.new(name="UVMap")
        layer.data.foreach_set("uv", uvs[ind.ravel()].ravel().astype(np.float32))
        log(f"UV (xatlas): {atlas.chart_count} карт")
        return
    activate(o)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.003)
    bpy.ops.object.mode_set(mode='OBJECT')
    log("UV: Smart UV Project")


# ----------------------------------------------------------------- разметка
def _erode(mask, r):
    out = mask.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy <= r * r:
                out &= np.roll(np.roll(mask, dy, 0), dx, 1)
    return out


def _dilate(mask, r):
    return ~_erode(~mask, r)


def silhouette(points2d, lo, shape):
    m = np.zeros(shape, bool)
    ij = ((points2d - lo) / CELL).astype(int)
    ok = (ij[:, 0] >= 0) & (ij[:, 1] >= 0) & (ij[:, 0] < shape[0]) & (ij[:, 1] < shape[1])
    m[ij[ok, 0], ij[ok, 1]] = True
    return _erode(_dilate(m, 2), 2)            # закрыть дырки между вершинами


def surface_samples(o):
    """Точки, равномерно покрывающие поверхность (вершин мало на крупных плоских треугольниках)."""
    me = o.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    me.calc_loop_triangles()
    tri = np.empty(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get("vertices", tri)
    tri = tri.reshape(-1, 3)
    a, b, c = co[tri[:, 0]], co[tri[:, 1]], co[tri[:, 2]]
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    n = np.minimum(np.ceil(area / (CELL * CELL * 0.25)).astype(int), 4000)
    idx = np.repeat(np.arange(len(tri)), n)
    rng = np.random.default_rng(0)
    u, v = rng.random(len(idx)), rng.random(len(idx))
    flip = u + v > 1
    u[flip], v[flip] = 1 - u[flip], 1 - v[flip]
    pts = a[idx] + (b[idx] - a[idx]) * u[:, None] + (c[idx] - a[idx]) * v[:, None]
    return np.vstack([co, pts])


def label_faces(high, low, kind, preset):
    """1 = ткань, 0 = дерево (по граням low-сетки, силуэты — по плотной high-сетке)."""
    hv = surface_samples(high)
    cen = np.empty(len(low.data.polygons) * 3)
    low.data.polygons.foreach_get("center", cen)
    cen = cen.reshape(-1, 3)
    nrm = np.empty(len(low.data.polygons) * 3)
    low.data.polygons.foreach_get("normal", nrm)
    nrm = nrm.reshape(-1, 3)
    lo, hi = hv.min(0), hv.max(0)
    H = hi[2] - lo[2]
    lab = np.ones(len(cen), np.int8)

    if kind == "bed":
        # постель — внутри каркаса: между столбиками по X, между спинками по Y, выше царг
        # по бокам между столбиками только низкая царга, поэтому свисающее одеяло ловится по высоте
        yspan = hi[1] - lo[1]
        inside = ((cen[:, 1] > lo[1] + 0.07 * yspan) & (cen[:, 1] < hi[1] - 0.095 * yspan)
                  & (cen[:, 2] > lo[2] + 0.245 * H) & (cen[:, 2] < lo[2] + 0.62 * H)
                  & (np.abs(cen[:, 0]) < 0.97 * hi[0]))
        lab[:] = 0
        lab[inside] = 1
        # свисающий край простыни у изголовья: снаружи, сбоку от столбиков, выше царги
        flap = ((np.abs(cen[:, 0]) > 0.86 * hi[0]) & (cen[:, 1] > lo[1] + 0.07 * yspan)
                & (cen[:, 1] < hi[1] - 0.055 * yspan) & (cen[:, 2] > lo[2] + 0.245 * H)
                & (cen[:, 2] < lo[2] + 0.5 * H) & (np.abs(nrm[:, 0]) > 0.5))
        lab[flap] = 1
        inside |= flap
        # одеяло (бордовое) — всё, кроме зоны у изголовья, где лежат подушки и отворот простыни
        head_is_hi = hv[hv[:, 1] > hi[1] - 0.1 * yspan, 2].max() > hv[hv[:, 1] < lo[1] + 0.1 * yspan, 2].max()
        dist_head = (hi[1] - cen[:, 1]) if head_is_hi else (cen[:, 1] - lo[1])
        lab[inside & (dist_head > HEAD_ZONE * yspan)] = 2
        return lab

    fw = int(round(preset["frame"] / CELL))
    views = {  # ось нормали, знак, (оси проекции)
        "front": (1, -1, (0, 2)), "back": (1, 1, (0, 2)),
        "left": (0, -1, (1, 2)), "right": (0, 1, (1, 2)),
    }
    for name, (ax, sgn, (a, b)) in views.items():
        lo2, hi2 = np.array([lo[a], lo[b]]), np.array([hi[a], hi[b]])
        shape = tuple((((hi2 - lo2) / CELL).astype(int) + 3).tolist())
        sil = silhouette(hv[:, [a, b]], lo2, shape)
        inner = _erode(sil, fw)
        sel = nrm[:, ax] * sgn > 0.5
        ij = ((cen[sel][:, [a, b]] - lo2) / CELL).astype(int)
        ij = np.clip(ij, 0, np.array(shape) - 1)
        lab[np.nonzero(sel)[0][~inner[ij[:, 0], ij[:, 1]]]] = 0
    # верхние грани выше подлокотников — торцы рамы спинки
    arm_top = lo[2] + 0.62 * H
    lab[(nrm[:, 2] > 0.6) & (cen[:, 2] > arm_top)] = 0
    lab[nrm[:, 2] < -0.6] = 0                                   # низ
    lab[cen[:, 2] < lo[2] + preset["base"] * H] = 0             # ножки и царга
    return lab


# ----------------------------------------------------------------- материалы и запекание
def material(name, kind):
    color, dark, rough = COLORS[kind]
    mat = bpy.data.materials.new(name)
    if bpy.app.version < (5, 0):
        mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = rough
    coord = nt.nodes.new("ShaderNodeTexCoord")
    patches = nt.nodes.new("ShaderNodeTexNoise")
    patches.inputs["Scale"].default_value = 7.0 if kind != "linen" else 4.0
    patches.inputs["Detail"].default_value = 6
    nt.links.new(coord.outputs["Object"], patches.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[0].color = 0.30, (*dark, 1)
    ramp.color_ramp.elements[1].position, ramp.color_ramp.elements[1].color = 0.60, (*color, 1)
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
    else:
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def new_image(name, res, cs="sRGB"):
    img = bpy.data.images.new(name, res, res, alpha=False)
    img.colorspace_settings.name = cs
    return img


def bake(low, kind, img, high=None, **kw):
    for mat in low.data.materials:
        nodes = mat.node_tree.nodes
        n = nodes.get("BAKE") or nodes.new("ShaderNodeTexImage")
        n.name = "BAKE"
        n.image = img
        nodes.active = n
    activate(low)
    sc = bpy.context.scene
    sc.render.bake.use_selected_to_active = high is not None
    if high is not None:
        high.select_set(True)
        bpy.context.view_layer.objects.active = low
        sc.render.bake.cage_extrusion = 0.015
        sc.render.bake.max_ray_distance = 0.03
    sc.render.bake.margin = 4
    t = time.time()
    bpy.ops.object.bake(type=kind, **kw)
    log(f"запечено {img.name} за {time.time() - t:.0f} с")


def img_np(img):
    a = np.empty(img.size[0] * img.size[1] * 4, np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(img.size[1], img.size[0], 4)


def bake_all(low, high, res, out):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = 16
    sc.render.bake.use_pass_direct = sc.render.bake.use_pass_indirect = False
    sc.render.bake.use_pass_color = True
    base = new_image("BaseColor", res)
    bake(low, 'DIFFUSE', base, pass_filter={'COLOR'})
    rough = new_image("Roughness", res, "Non-Color")
    bake(low, 'ROUGHNESS', rough)
    normal = new_image("Normal", res, "Non-Color")
    bake(low, 'NORMAL', normal, high=high, normal_space='TANGENT')
    a = img_np(normal)                                  # вывернутые тексели (луч попал в изнанку)
    back = a[..., 2] < 0.5
    a[back, :3] = 1 - a[back, :3]
    normal.pixels.foreach_set(a.ravel())
    ao = new_image("AO", res, "Non-Color")
    high.hide_render = True
    sc.world = sc.world or bpy.data.worlds.new("World")
    sc.world.light_settings.distance = 0.12
    sc.cycles.samples = 32
    bake(low, 'AO', ao)
    high.hide_render = False
    # цвет с AO (для Roblox — у SurfaceAppearance нет отдельной AO)
    B, A = img_np(base), img_np(ao)
    color = B.copy()
    color[..., :3] = B[..., :3] * (0.35 + 0.65 * A[..., :1])
    col_img = new_image("Color", res)
    col_img.pixels.foreach_set(color.ravel())
    metal = new_image("Metalness", res, "Non-Color")
    m = np.zeros((res, res, 4), np.float32)
    m[..., 3] = 1
    metal.pixels.foreach_set(m.ravel())
    maps = {"Color": col_img, "Roughness": rough, "Normal": normal, "AO": ao, "Metalness": metal}
    os.makedirs(os.path.join(out, "textures"), exist_ok=True)
    for k, img in maps.items():
        img.filepath_raw = os.path.join(out, "textures", f"{low.name}_{k}.png")
        img.file_format = 'PNG'
        img.save()
    return maps


def final_material(low, maps):
    mat = bpy.data.materials.new(f"M_{low.name}")
    if bpy.app.version < (5, 0):
        mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]

    def tex(k, y):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = maps[k]
        n.location = (-500, y)
        return n
    nt.links.new(tex("Color", 300).outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(tex("Roughness", 0).outputs["Color"], bsdf.inputs["Roughness"])
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tex("Normal", -300).outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    low.data.materials.clear()
    low.data.materials.append(mat)


def main():
    a = sys.argv[sys.argv.index("--") + 1:]
    src, out, kind = a[0], os.path.abspath(a[1]), a[2]
    res = int(a[3]) if len(a) > 3 else 1024
    preset = PRESETS[kind]
    name = {"chair": "Armchair", "sofa": "Sofa", "bed": "Bed"}[kind]
    os.makedirs(out, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    t0 = time.time()
    high = import_model(src, preset)
    low = make_low(high, name)
    lab = label_faces(high, low, kind, preset)
    log(f"{name}: {len(low.data.polygons)} треугольников, ткань {lab.mean():.0%}")
    low.data.materials.clear()                       # у импорта из Meshy свой белый материал — убрать
    low.data.materials.append(material("Wood", "wood"))
    low.data.materials.append(material("Fabric", preset["fabric"]))
    if kind == "bed":
        low.data.materials.append(material("Duvet", "duvet"))
    low.data.polygons.foreach_set("material_index", lab.astype(np.int32))
    low.data.update()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, f"{name}_regions.blend"))
    maps = bake_all(low, high, res, out)
    final_material(low, maps)
    bpy.data.objects.remove(high, do_unlink=True)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, f"{name}.blend"))
    activate(low)
    bpy.ops.export_scene.gltf(filepath=os.path.join(out, f"{name}.glb"), export_format='GLB', use_selection=True)
    bpy.ops.export_scene.fbx(filepath=os.path.join(out, f"{name}_Roblox.fbx"), use_selection=True,
                             axis_forward='-Z', axis_up='Y', apply_scale_options='FBX_SCALE_ALL', path_mode='STRIP')
    log(f"готово за {time.time() - t0:.0f} с -> {out}")


if __name__ == "__main__":
    main()
