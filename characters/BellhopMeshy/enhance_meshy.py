"""
Доработка текстур модели коридорного из Meshy (GLB с UV и базовыми PBR-картами).

У Meshy-модели уже есть BaseColor / MetallicRoughness / Normal, но:
  * глаза не светятся (просто белые пятна в цвете),
  * латунь не металлическая (Metallic ~0),
  * кожа, руки, брюки и обувь — один и тот же чёрный «пластик»,
  * ткань без фактуры, нет AO.

Скрипт:
  1. Импортирует GLB, запекает карту позиций (для каждого текселя — точка на теле) и AO.
  2. Классифицирует тексели по цвету + положению: красная ткань, латунь, кожа (голова, кисти),
     брюки, кожа обуви/козырька, зубы, глаза.
  3. Пересобирает карты: BaseColor (латунь золотее и с патиной, зубы с желтизной, AO),
     Roughness, Metallic, Emission (глаза), Normal (+ плетение ткани), маска Sheen (бархат).
  4. Собирает PBR-материал, сохраняет .blend, PNG-карты, GLB (полная и игровая LOD-версия).

Запуск:  blender --background --python enhance_meshy.py -- model.glb out_dir [lod_tris=60000]
"""

import math
import os
import sys
import time

import bpy
import bmesh
import numpy as np

RES = 2048
LOD_TRIS = 60000
AO_DISTANCE = 0.12
EYE_EMISSION = 12.0

# Зоны по высоте/положению (метры, модель после импорта: рост ~1.9 м, центр в 0, лицо в -Y)
Z_HEAD = 0.72          # выше — голова (тёмное = кожа)
Z_SHOE = -0.80         # ниже — обувь
Z_HEM = 0.28           # ниже подола и не руки — брюки
HAND_X = 0.36          # |x| больше на уровне кистей — кисти
Z_HAND = (-0.65, -0.05)
VISOR_Y = -0.27        # на высоте фуражки впереди — козырёк
Z_HAT = 0.86


def log(*a):
    print("[meshy]", *a, flush=True)


def activate(o):
    for x in bpy.context.selected_objects:
        x.select_set(False)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)


def img_to_np(img):
    a = np.empty(img.size[0] * img.size[1] * 4, np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(img.size[1], img.size[0], 4)


def np_to_img(name, arr, colorspace="sRGB", float_buffer=False):
    h, w = arr.shape[:2]
    img = bpy.data.images.new(name, w, h, alpha=False, float_buffer=float_buffer)
    img.colorspace_settings.name = colorspace
    a = np.ones((h, w, 4), np.float32)
    a[..., :arr.shape[2] if arr.ndim == 3 else 1] = arr if arr.ndim == 3 else arr[..., None]
    if arr.ndim == 2:
        a[..., 1] = a[..., 2] = arr
    img.pixels.foreach_set(a.ravel())
    return img


# ----------------------------------------------------------------- запекание служебных карт
def bake_emit(obj, mat, build, name, float_buffer=True):
    """Временно подменяет выход материала на Emission(build(nodes)) и печёт EMIT."""
    nt = mat.node_tree
    out = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL')
    old = [(l.from_socket, l.to_socket) for l in out.inputs["Surface"].links]
    em = nt.nodes.new("ShaderNodeEmission")
    tmp = build(nt)
    nt.links.new(tmp, em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    img = bpy.data.images.new(name, RES, RES, alpha=False, float_buffer=float_buffer)
    img.colorspace_settings.name = "Non-Color"
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    nt.nodes.active = tex
    activate(obj)
    bpy.ops.object.bake(type='EMIT', margin=4)
    nt.nodes.remove(tex)
    nt.nodes.remove(em)
    for a, b in old:
        nt.links.new(a, b)
    return img


def bake_position(obj, mat):
    def build(nt):
        g = nt.nodes.new("ShaderNodeNewGeometry")
        return g.outputs["Position"]
    return bake_emit(obj, mat, build, "pos")


def bake_ao(obj, mat):
    sc = bpy.context.scene
    sc.world = sc.world or bpy.data.worlds.new("World")
    sc.world.light_settings.distance = AO_DISTANCE
    nt = mat.node_tree
    img = bpy.data.images.new("ao", RES, RES, alpha=False)
    img.colorspace_settings.name = "Non-Color"
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    nt.nodes.active = tex
    activate(obj)
    sc.cycles.samples = 32
    bpy.ops.object.bake(type='AO', margin=4)
    nt.nodes.remove(tex)
    return img


# ----------------------------------------------------------------- классификация
def classify(base, pos, valid):
    r, g, b = base[..., 0], base[..., 1], base[..., 2]
    mx, mn = base.max(-1), base.min(-1)
    x, y, z = pos[..., 0], pos[..., 1], pos[..., 2]
    lab = np.zeros(base.shape[:2], np.uint8)       # 0 пусто
    RED, BRASS, SKIN, PANTS, LEATHER, TEETH, EYES = 1, 2, 3, 4, 5, 6, 7
    white = valid & (mn > 0.62)
    gold = valid & (r > 0.28) & (r - b > 0.12) & (g > 0.6 * r) & ~white
    red = valid & (r > 1.6 * g) & (r > 0.07) & ~gold & ~white
    dark = valid & ~white & ~gold & ~red
    lab[red] = RED
    lab[gold] = BRASS
    hand = (np.abs(x) > HAND_X) & (z > Z_HAND[0] - 0.05) & (z < Z_HAND[1])
    lab[dark] = PANTS
    lab[dark & (z > Z_HEM)] = RED                    # тёмные швы/подкладка пиджака
    lab[dark & (z > Z_HEAD)] = SKIN                  # голова и шея
    lab[dark & hand] = SKIN                          # кисти и когти
    lab[dark & (z < Z_SHOE)] = LEATHER               # обувь
    lab[dark & (z > Z_HAT) & (y < VISOR_Y)] = LEATHER   # козырёк
    # белое: глаза — самые яркие пятна в верхней части лица, остальное — зубы
    lab[white] = TEETH
    if white.any():
        zw = z[white]
        eye_z = np.percentile(zw, 92)
        eye = white & (z > eye_z - 0.035) & (mn > 0.8)
        lab[eye] = EYES
    names = ["empty", "RedFabric", "OldBrass", "Skin", "Pants", "Leather", "Teeth", "Eyes"]
    counts = {names[i]: int((lab == i).sum()) for i in range(1, 8)}
    log("тексели по областям:", counts)
    return lab


def blur(a, r):
    k = np.exp(-0.5 * (np.arange(-3 * r, 3 * r + 1) / r) ** 2)
    k /= k.sum()
    for ax in (0, 1):
        a = np.apply_along_axis(lambda m: np.convolve(m, k, mode="same"), ax, a)
    return a


def value_noise(shape, cell, seed):
    rng = np.random.default_rng(seed)
    h, w = shape
    gh, gw = h // cell + 2, w // cell + 2
    g = rng.random((gh, gw)).astype(np.float32)
    yy = np.linspace(0, gh - 2, h, dtype=np.float32)
    xx = np.linspace(0, gw - 2, w, dtype=np.float32)
    y0, x0 = yy.astype(int), xx.astype(int)
    ty, tx = (yy - y0)[:, None], (xx - x0)[None, :]
    ty, tx = ty * ty * (3 - 2 * ty), tx * tx * (3 - 2 * tx)
    a = g[y0][:, x0]
    b = g[y0][:, x0 + 1]
    c = g[y0 + 1][:, x0]
    d = g[y0 + 1][:, x0 + 1]
    return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


def fbm(shape, cell, seed, octaves=4):
    out, amp, tot = np.zeros(shape, np.float32), 1.0, 0.0
    for i in range(octaves):
        out += amp * value_noise(shape, max(2, cell >> i), seed + i)
        tot += amp
        amp *= 0.5
    return out / tot


# ----------------------------------------------------------------- новые карты
def build_maps(base, rough_old, normal, ao, lab):
    shape = base.shape[:2]
    n1 = fbm(shape, 64, 1)                 # крупные потёртости
    n2 = fbm(shape, 8, 7, 3)               # мелкая фактура
    weave = (np.sin(np.arange(shape[1])[None, :] * 1.9) * np.sin(np.arange(shape[0])[:, None] * 1.9)).astype(np.float32)

    color = base.copy()
    rough = rough_old.copy()
    metal = np.zeros(shape, np.float32)
    emis = np.zeros(shape + (3,), np.float32)
    sheen = np.zeros(shape, np.float32)

    m = lab == 1                                    # красная ткань: бархат, потёртости
    color[m] *= (0.72 + 0.25 * n1[m])[:, None]
    rough[m] = 0.8 + 0.12 * n2[m]
    sheen[m] = 0.3
    m = lab == 2                                    # латунь: золото, патина в «углублениях» (по AO)
    gold = np.array([0.78, 0.55, 0.22], np.float32)
    patina = np.array([0.22, 0.17, 0.08], np.float32)
    t = np.clip((ao[m] - 0.35) / 0.5, 0, 1) * (0.7 + 0.3 * n1[m])
    color[m] = 0.35 * base[m] + 0.65 * (patina[None] * (1 - t[:, None]) + gold[None] * t[:, None])
    rough[m] = 0.28 + 0.3 * (1 - t) * n2[m]
    metal[m] = 1.0
    m = lab == 3                                    # кожа головы и кистей: тёмная, полуматовая
    color[m] = color[m] * 0.8 + np.array([0.02, 0.008, 0.006]) * 0.2
    rough[m] = 0.42 + 0.15 * n2[m]
    m = lab == 4                                    # брюки: матовая тёмная ткань
    color[m] *= (0.85 + 0.3 * n1[m])[:, None]
    rough[m] = 0.86 + 0.08 * n2[m]
    sheen[m] = 0.12
    m = lab == 5                                    # кожа обуви и козырька: глянец с потёртостями
    rough[m] = 0.28 + 0.25 * n1[m]
    m = lab == 6                                    # зубы: желтизна к корням (по AO)
    tint = np.array([0.93, 0.88, 0.74], np.float32)
    color[m] = color[m] * (tint[None] * (0.75 + 0.25 * ao[m][:, None]))
    rough[m] = 0.32
    m = lab == 7                                    # глаза: свечение
    emis[m] = np.array([1.0, 0.96, 0.88]) * np.clip(base[m].mean(-1, keepdims=True) * 1.2, 0, 1)
    rough[m] = 0.3

    color *= (0.35 + 0.65 * ao)[..., None]          # AO в цвет (умеренно)
    color = np.clip(color, 0, 1)

    # плетение ткани в normal map
    nrm = normal.copy()
    fab = (lab == 1) | (lab == 4)
    dx = 0.06 * weave + 0.04 * (n2 - 0.5)
    nrm[..., 0][fab] = np.clip(nrm[..., 0][fab] + dx[fab] * 0.5, 0, 1)
    nrm[..., 1][fab] = np.clip(nrm[..., 1][fab] + np.roll(dx, 1, 0)[fab] * 0.5, 0, 1)
    return color, rough, metal, emis, sheen, nrm


# ----------------------------------------------------------------- материал
def build_material(images):
    mat = bpy.data.materials.new("M_Bellhop_Meshy")
    if bpy.app.version < (5, 0):
        mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    bsdf = nodes.get("Principled BSDF")

    def tex(key, y):
        n = nodes.new("ShaderNodeTexImage")
        n.image = images[key]
        n.location = (-600, y)
        return n
    links.new(tex("BaseColor", 300).outputs["Color"], bsdf.inputs["Base Color"])
    links.new(tex("Roughness", 0).outputs["Color"], bsdf.inputs["Roughness"])
    links.new(tex("Metallic", -250).outputs["Color"], bsdf.inputs["Metallic"])
    nm = nodes.new("ShaderNodeNormalMap")
    links.new(tex("Normal", -500).outputs["Color"], nm.inputs["Color"])
    links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    emc = "Emission Color" if "Emission Color" in bsdf.inputs else "Emission"
    links.new(tex("Emission", -750).outputs["Color"], bsdf.inputs[emc])
    bsdf.inputs["Emission Strength"].default_value = EYE_EMISSION
    sheen = "Sheen Weight" if "Sheen Weight" in bsdf.inputs else "Sheen"
    if sheen in bsdf.inputs:
        links.new(tex("Sheen", -1000).outputs["Color"], bsdf.inputs[sheen])
        if "Sheen Tint" in bsdf.inputs and bsdf.inputs["Sheen Tint"].type == 'RGBA':
            bsdf.inputs["Sheen Tint"].default_value = (0.45, 0.08, 0.08, 1)
    return mat


def main():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    src = a[0] if a else "model.glb"
    out = os.path.abspath(a[1] if len(a) > 1 else "BellhopMeshy_out")
    lod = int(a[2]) if len(a) > 2 else LOD_TRIS
    os.makedirs(os.path.join(out, "textures"), exist_ok=True)
    t0 = time.time()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=src)
    obj = next(o for o in bpy.data.objects if o.type == 'MESH')
    obj.name = obj.data.name = "Bellhop_Meshy"
    mat = obj.data.materials[0]
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = 1
    sc.render.bake.margin = 4

    # исходные карты
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")

    def src_img(socket):
        n = bsdf.inputs[socket].links[0].from_node
        while n.type != 'TEX_IMAGE':
            n = next(i for i in n.inputs if i.is_linked).links[0].from_node
        return n.image
    base_img = src_img("Base Color")
    mr_img = src_img("Roughness")
    nrm_img = src_img("Normal")
    base = img_to_np(base_img)[..., :3]
    mr = img_to_np(mr_img)
    normal = img_to_np(nrm_img)[..., :3]
    log(f"исходные карты: {base_img.size[:]} / {len(obj.data.polygons)} треугольников")

    pos = img_to_np(bake_position(obj, mat))[..., :3]
    valid = np.abs(pos).sum(-1) > 1e-6
    ao = img_to_np(bake_ao(obj, mat))[..., 0]
    ao[~valid] = 1.0
    log(f"позиции и AO запечены ({time.time() - t0:.0f} с)")

    lab = classify(base, pos, valid)
    palette = np.array([[0.2, 0.2, 0.2], [0.8, 0.05, 0.05], [1, 0.8, 0.1], [0.45, 0.28, 0.18], [0.15, 0.15, 0.45],
                        [0.5, 0.1, 0.6], [1, 1, 1], [0, 1, 1]], np.float32)
    dbg = np_to_img("debug_labels", palette[lab])
    dbg.filepath_raw = os.path.join(out, "textures", "debug_labels.png")
    dbg.file_format = 'PNG'
    dbg.save()
    color, rough, metal, emis, sheen, nrm = build_maps(base, mr[..., 1], normal, ao, lab)

    images = {
        "BaseColor": np_to_img("Bellhop_Meshy_BaseColor", color),
        "Roughness": np_to_img("Bellhop_Meshy_Roughness", rough, "Non-Color"),
        "Metallic": np_to_img("Bellhop_Meshy_Metallic", metal, "Non-Color"),
        "Normal": np_to_img("Bellhop_Meshy_Normal", nrm, "Non-Color"),
        "Emission": np_to_img("Bellhop_Meshy_Emission", emis),
        "Sheen": np_to_img("Bellhop_Meshy_Sheen", sheen, "Non-Color"),
        "AO": np_to_img("Bellhop_Meshy_AO", ao, "Non-Color"),
    }
    for k, img in images.items():
        img.filepath_raw = os.path.join(out, "textures", f"Bellhop_Meshy_{k}.png")
        img.file_format = 'PNG'
        img.save()
    new_mat = build_material(images)
    obj.data.materials.clear()
    obj.data.materials.append(new_mat)

    # игровая LOD-версия: Decimate сохраняет UV -> те же текстуры
    lod_obj = obj.copy()
    lod_obj.data = obj.data.copy()
    lod_obj.name = lod_obj.data.name = "Bellhop_Meshy_LOD"
    sc.collection.objects.link(lod_obj)
    d = lod_obj.modifiers.new("dec", 'DECIMATE')
    d.ratio = lod / len(obj.data.polygons)
    activate(lod_obj)
    bpy.ops.object.modifier_apply(modifier=d.name)
    log(f"LOD: {len(lod_obj.data.polygons)} треугольников")

    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "Bellhop_Meshy.blend"))
    for o, fname in ((obj, "Bellhop_Meshy.glb"), (lod_obj, "Bellhop_Meshy_LOD.glb")):
        activate(o)
        bpy.ops.export_scene.gltf(filepath=os.path.join(out, fname), export_format='GLB', use_selection=True)
    log(f"готово за {time.time() - t0:.0f} с -> {out}")


if __name__ == "__main__":
    main()
