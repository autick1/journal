"""
Пакет для Roblox из доработанной Meshy-модели.

Ограничения Roblox Studio (3D Importer / SurfaceAppearance):
  * один MeshPart — не больше 20 000 треугольников;
  * текстуры SurfaceAppearance — до 1024x1024, отдельные карты Color / Metalness / Roughness / Normal;
  * карты свечения нет — светящиеся глаза делаются отдельной деталью с материалом Neon.

Скрипт: берёт Bellhop_Meshy.blend (результат enhance_meshy.py), упрощает до 19 000 треугольников
(UV сохраняются), отделяет глаза, уменьшает карты до 1024, экспортирует FBX.

Запуск: blender --background --python roblox_export.py -- Bellhop_Meshy.blend out_dir
"""

import os
import sys

import bpy
import bmesh
import numpy as np

BODY_TRIS = 19000
TEX = 1024


def log(*a):
    print("[roblox]", *a, flush=True)


def activate(o):
    for x in bpy.context.selected_objects:
        x.select_set(False)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)


def main():
    a = sys.argv[sys.argv.index("--") + 1:]
    src, out = a[0], os.path.abspath(a[1])
    os.makedirs(os.path.join(out, "textures"), exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=src)
    for o in list(bpy.data.objects):
        if o.name != "Bellhop_Meshy":
            bpy.data.objects.remove(o, do_unlink=True)
    body = bpy.data.objects["Bellhop_Meshy"]
    mat = body.data.materials[0]
    imgs = {n.image.name.split("_")[-1]: n.image for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE'}

    # глаза: грани, где карта свечения яркая
    em = imgs["Emission"]
    E = np.empty(em.size[0] * em.size[1] * 4, np.float32)
    em.pixels.foreach_get(E)
    E = E.reshape(em.size[1], em.size[0], 4)[..., :3].mean(-1)
    me = body.data
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    eye_faces = []
    for p in me.polygons:
        c = uv[p.loop_start:p.loop_start + p.loop_total].mean(0)
        i, j = int(c[1] * (em.size[1] - 1)), int(c[0] * (em.size[0] - 1))
        if E[min(max(i, 0), em.size[1] - 1), min(max(j, 0), em.size[0] - 1)] > 0.35:
            eye_faces.append(p.index)
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    eyes_bm = bmesh.new()
    vmap = {}
    for fi in eye_faces:
        f = bm.faces[fi]
        vs = []
        for v in f.verts:
            if v.index not in vmap:
                vmap[v.index] = eyes_bm.verts.new(v.co)
            vs.append(vmap[v.index])
        try:
            eyes_bm.faces.new(vs)
        except ValueError:
            pass
    bm.free()
    eyes_me = bpy.data.meshes.new("Bellhop_Eyes")
    eyes_bm.to_mesh(eyes_me)
    eyes = bpy.data.objects.new("Bellhop_Eyes", eyes_me)
    bpy.context.scene.collection.objects.link(eyes)
    m = bpy.data.materials.new("Eyes_Neon")
    m.diffuse_color = (1, 0.97, 0.9, 1)
    eyes_me.materials.append(m)
    # чуть вперёд, чтобы не мерцали на поверхности лица
    for v in eyes_me.vertices:
        v.co += v.normal * 0.0015
    log(f"глаза: {len(eyes_me.polygons)} граней")

    # тело: до лимита Roblox
    d = body.modifiers.new("dec", 'DECIMATE')
    d.ratio = BODY_TRIS / len(me.polygons)
    activate(body)
    bpy.ops.object.modifier_apply(modifier=d.name)
    body.name = "Bellhop"
    log(f"тело: {len(body.data.polygons)} треугольников")

    # карты 1024: Color (с AO уже внутри), Metalness, Roughness, Normal
    for key, name in (("BaseColor", "Color"), ("Metallic", "Metalness"), ("Roughness", "Roughness"),
                      ("Normal", "Normal")):
        img = imgs[key].copy()
        img.scale(TEX, TEX)
        img.filepath_raw = os.path.join(out, "textures", f"Bellhop_{name}.png")
        img.file_format = 'PNG'
        img.save()
    activate(body)
    eyes.select_set(True)
    bpy.ops.export_scene.fbx(filepath=os.path.join(out, "Bellhop_Roblox.fbx"), use_selection=True,
                             apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL',
                             axis_forward='-Z', axis_up='Y', path_mode='STRIP', add_leaf_bones=False)
    log(f"готово -> {out}")


if __name__ == "__main__":
    main()
