"""
Meshy-модели без текстур -> отдельные детали для Roblox.

  sofa  — резной диван (meshy-model_5.glb), пара к резному креслу props/ArmchairCarved
  chair — деревянный стул (meshy-model_6.glb)

Модель масштабируется до реальной высоты, ставится на пол, полигонаж снижается,
сетка прорезается плоскостями по границам деталей (замерены по модели), каждая деталь —
отдельный объект <= 19 500 треугольников (лимит MeshPart в Roblox — 20 000).

Запуск: python split_parts.py -- model.glb out_dir sofa|chair
"""

import os
import sys

import bpy
import bmesh
import numpy as np


# ------------------------------------------------------------------ диван
def sofa_classify(c, n):
    x, y, z = c
    ax, s = abs(x), ("L" if x < 0 else "R")
    if z < 0.15:
        if ax > 0.75 and abs(y) > 0.18:
            return f"Leg_{'F' if y < 0 else 'B'}{s}"
        return "Base"
    if z < 0.285:
        return "Base"
    if y > 0.27 and n[1] > 0.5:
        return "BackRear"
    if ax >= 0.77 and (z < 0.62 or (z < 0.68 and y < 0.21)):
        return f"ArmFront_{s}" if y < -0.22 else f"Arm_{s}"
    if z >= 0.62 or (z >= 0.46 and y >= 0.13):
        if z > 1.01 and ax < 0.32:
            return "Crest"
        if n[1] < 0.3 and y < 0.2125:
            return "BackPanel"
        return "BackFrame"
    return f"Seat_{s}"


SOFA = dict(
    prefix="Sofa", height=1.10, target=180000, classify=sofa_classify,
    planes=[((0, 0, 0.15), (0, 0, 1)), ((0, 0, 0.285), (0, 0, 1)), ((0, 0, 0.46), (0, 0, 1)),
            ((0, 0, 0.62), (0, 0, 1)), ((0, 0, 0.68), (0, 0, 1)), ((0, 0, 1.01), (0, 0, 1)),
            ((0.77, 0, 0), (1, 0, 0)), ((-0.77, 0, 0), (1, 0, 0)), ((0, 0, 0), (1, 0, 0)),
            ((0.32, 0, 0), (1, 0, 0)), ((-0.32, 0, 0), (1, 0, 0)),
            ((0, -0.22, 0), (0, 1, 0)), ((0, 0.13, 0), (0, 1, 0))],
    parts=["Leg_FL", "Leg_FR", "Leg_BL", "Leg_BR", "Base", "Seat_L", "Seat_R", "Arm_L", "Arm_R",
           "ArmFront_L", "ArmFront_R", "BackPanel", "BackFrame", "Crest", "BackRear"],
    wood={"Leg_FL", "Leg_FR", "Leg_BL", "Leg_BR", "Base", "ArmFront_L", "ArmFront_R", "BackFrame", "Crest"},
)


# ------------------------------------------------------------------ стул
def chair_classify(c, n):
    x, y, z = c
    ax, s = abs(x), ("L" if x < 0 else "R")
    if ax > 0.155 and y > 0.11:                      # задние ножки, переходящие в стойки спинки
        if z < 0.435:
            return f"Leg_B{s}"
        if z < 0.83:
            return f"BackPost_{s}"
        return "TopRail"
    if ax > 0.165 and y < -0.15 and z < 0.365:       # передние ножки
        return f"Leg_F{s}"
    if z < 0.30:
        return "Stretchers"
    if z < 0.365:
        return "Apron"
    if z < 0.435:
        return "Seat"
    if y > 0.08:
        if z >= 0.83:
            return "TopRail"
        if z < 0.515:
            return "BackRail"
        return f"Slat_{s}"
    return "Seat"


CHAIR = dict(
    prefix="Chair", height=0.95, target=90000, classify=chair_classify,
    planes=[((0, 0, 0.30), (0, 0, 1)), ((0, 0, 0.365), (0, 0, 1)), ((0, 0, 0.435), (0, 0, 1)),
            ((0, 0, 0.515), (0, 0, 1)), ((0, 0, 0.83), (0, 0, 1)),
            ((0.155, 0, 0), (1, 0, 0)), ((-0.155, 0, 0), (1, 0, 0)),
            ((0, 0.11, 0), (0, 1, 0)), ((0, -0.15, 0), (0, 1, 0))],
    parts=["Leg_FL", "Leg_FR", "Leg_BL", "Leg_BR", "Stretchers", "Apron", "Seat",
           "BackPost_L", "BackPost_R", "BackRail", "Slat_L", "Slat_R", "TopRail"],
    wood=None,                                       # стул весь деревянный
)

KINDS = {"sofa": SOFA, "chair": CHAIR}
MAX_TRIS = 19500


def log(*a):
    print("[split]", *a, flush=True)


def main():
    a = sys.argv[sys.argv.index("--") + 1:]
    src, out, K = a[0], os.path.abspath(a[1]), KINDS[a[2]]
    os.makedirs(out, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=src)
    obj = next(o for o in bpy.data.objects if o.type == 'MESH')
    for o in list(bpy.data.objects):
        if o != obj:
            bpy.data.objects.remove(o, do_unlink=True)
    obj.parent = None
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    me = obj.data                                    # масштаб, центр, на пол
    v = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", v)
    v = v.reshape(-1, 3)
    v *= K["height"] / (v[:, 2].max() - v[:, 2].min())
    v[:, 0] -= (v[:, 0].max() + v[:, 0].min()) / 2
    v[:, 1] -= (v[:, 1].max() + v[:, 1].min()) / 2
    v[:, 2] -= v[:, 2].min()
    me.vertices.foreach_set("co", v.ravel())
    me.update()
    log("исходно треугольников:", len(me.polygons), "размер:", (v.max(0) - v.min(0)).round(3))

    m = obj.modifiers.new("dec", 'DECIMATE')
    m.ratio = min(1.0, K["target"] / max(1, len(me.polygons)))
    bpy.ops.object.modifier_apply(modifier=m.name)

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    for co, no in K["planes"]:
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-5, plane_co=co, plane_no=no)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    bm.to_mesh(obj.data)
    bm.free()
    me = obj.data
    cen = np.empty(len(me.polygons) * 3)
    me.polygons.foreach_get("center", cen)
    nrm = np.empty(len(me.polygons) * 3)
    me.polygons.foreach_get("normal", nrm)
    lab = [K["classify"](c, n) for c, n in zip(cen.reshape(-1, 3), nrm.reshape(-1, 3))]

    def mat(name, rgb, rough):
        mt = bpy.data.materials.new(name)
        b = mt.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (*rgb, 1)
        b.inputs["Roughness"].default_value = rough
        return mt
    m_wood = mat("Wood", (0.16, 0.07, 0.03), 0.45)
    m_fab = mat("Fabric", (0.30, 0.03, 0.04), 0.85)

    P = K["prefix"]
    made = []
    for part in K["parts"]:
        ids = {i for i, l in enumerate(lab) if l == part}
        if not ids:
            log("!! пустая деталь", part)
            continue
        o = obj.copy()
        o.data = obj.data.copy()
        o.name = o.data.name = f"{P}_{part}"
        bpy.context.scene.collection.objects.link(o)
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bm.faces.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in ids], context='FACES')
        bm.to_mesh(o.data)
        bm.free()
        o.data.materials.clear()
        o.data.materials.append(m_wood if K["wood"] is None or part in K["wood"] else m_fab)
        bpy.context.view_layer.objects.active = o
        for x in bpy.context.selected_objects:
            x.select_set(False)
        o.select_set(True)
        if len(o.data.polygons) > MAX_TRIS:
            d = o.modifiers.new("dec", 'DECIMATE')
            d.ratio = MAX_TRIS / len(o.data.polygons) * 0.98
            bpy.ops.object.modifier_apply(modifier=d.name)
        bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
        made.append(o)
        log(f"{o.name}: {len(o.data.polygons)} треугольников")
    bpy.data.objects.remove(obj, do_unlink=True)
    log("всего:", sum(len(o.data.polygons) for o in made))

    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, f"{P}_Parts.blend"))
    for o in made:
        o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=os.path.join(out, f"{P}_Parts.glb"), export_format='GLB', use_selection=True)
    bpy.ops.export_scene.fbx(filepath=os.path.join(out, f"{P}_Parts_Roblox.fbx"), use_selection=True,
                             axis_forward='-Z', axis_up='Y', apply_scale_options='FBX_SCALE_ALL', path_mode='STRIP')
    log("готово ->", out)


if __name__ == "__main__":
    main()
