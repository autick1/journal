"""
Резное кресло (meshy-model_4.glb, без текстур) -> отдельные детали для Roblox.

Модель масштабируется до высоты 1.10 м, ставится на пол, полигонаж снижается
(468k -> ~150k), затем сетка прорезается плоскостями по границам деталей и
каждая деталь становится отдельным объектом (каждый <= 19 500 треугольников —
лимит MeshPart в Roblox 20 000).

Детали: Leg_FL/FR/BL/BR, Base (царга), Seat (подушка), Arm_L/R (подлокотники),
ArmFront_L/R (резные свитки спереди), BackPanel (мягкая вставка спинки),
BackFrame (резная рамка), Crest (корона-резьба сверху), BackRear (задняя стенка).

Запуск: python split_armchair.py -- model.glb out_dir
"""

import os
import sys

import bpy
import bmesh
import numpy as np

H = 1.10                       # высота кресла, м
LEG_Z = 0.165                  # низ царги
BASE_Z = 0.29                  # верх царги / низ подушки
SEAT_Z = 0.455                 # верх подушки = низ мягкой вставки спинки
ARM_X = 0.27                   # внутренняя сторона подлокотника
ARM_TOP = 0.67                 # верх валика подлокотника (сзади выше 0.62 — стойки рамки)
ARM_POST = (0.62, 0.21)        # z, y: за валиком выше z=0.62 начинается стойка рамки спинки
FRONT_Y = -0.24                # перед подлокотника: резной свиток
BACK_Y = 0.10                  # плоскость спинки у сиденья
REAR_Y = 0.27                  # задняя стенка
CREST = (0.18, 0.995)          # корона: |x| < 0.18, z > 0.995
# контур мягкой вставки спинки (x, z), правая половина — замерено по карте глубины
PANEL_HALF = [(0.325, 0.44), (0.325, 0.88), (0.30, 0.915), (0.24, 0.94), (0.14, 0.958), (0.0, 0.968)]
MAX_TRIS = 19500
WOOD = {"Leg_FL", "Leg_FR", "Leg_BL", "Leg_BR", "Base", "ArmFront_L", "ArmFront_R", "BackFrame", "Crest"}
PARTS = ["Leg_FL", "Leg_FR", "Leg_BL", "Leg_BR", "Base", "Seat", "Arm_L", "Arm_R", "ArmFront_L", "ArmFront_R",
         "BackPanel", "BackFrame", "Crest", "BackRear"]


def log(*a):
    print("[armchair]", *a, flush=True)


def panel_z(x):
    """Верхняя граница мягкой вставки при данном |x| (None — вне вставки по ширине)."""
    ax = abs(x)
    pts = sorted(PANEL_HALF[1:], key=lambda p: p[0])
    if ax > pts[-1][0]:
        return None
    for (x1, z1), (x2, z2) in zip(pts, pts[1:]):
        if x1 <= ax <= x2:
            return z1 + (z2 - z1) * (ax - x1) / (x2 - x1)
    return pts[0][1]


def classify(c, n):
    x, y, z = c
    ax, s = abs(x), ("L" if x < 0 else "R")
    if z < LEG_Z:
        if ax > 0.25 and abs(y) > 0.17:          # точёные ножки по углам
            return f"Leg_{'F' if y < 0 else 'B'}{s}"
        return "Base"                             # днище царги
    if z < BASE_Z:
        return "Base"
    if y > REAR_Y and n[1] > 0.5:
        return "BackRear"
    if ax >= ARM_X and (z < ARM_POST[0] or (z < ARM_TOP and y < ARM_POST[1])):
        return f"ArmFront_{s}" if y < FRONT_Y else f"Arm_{s}"
    if z >= ARM_POST[0] or (z >= SEAT_Z and y >= BACK_Y):
        if z > CREST[1] and ax < CREST[0]:
            return "Crest"
        top = panel_z(x)
        if top is not None and z <= top and n[1] < 0.3:
            return "BackPanel"
        return "BackFrame"
    return "Seat"


def main():
    a = sys.argv[sys.argv.index("--") + 1:]
    src, out = a[0], os.path.abspath(a[1])
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

    # масштаб и постановка на пол
    me = obj.data
    v = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", v)
    v = v.reshape(-1, 3)
    v *= H / (v[:, 2].max() - v[:, 2].min())
    v[:, 0] -= (v[:, 0].max() + v[:, 0].min()) / 2
    v[:, 1] -= (v[:, 1].max() + v[:, 1].min()) / 2
    v[:, 2] -= v[:, 2].min()
    me.vertices.foreach_set("co", v.ravel())
    me.update()

    # снижение полигонажа до разумного (форма и резьба сохраняются)
    log("исходно треугольников:", len(me.polygons))
    m = obj.modifiers.new("dec", 'DECIMATE')
    m.ratio = min(1.0, 150000 / max(1, len(me.polygons)))
    bpy.ops.object.modifier_apply(modifier=m.name)

    # прорезать плоскостями -> ровные края деталей
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    planes = [((0, 0, LEG_Z), (0, 0, 1)), ((0, 0, BASE_Z), (0, 0, 1)), ((0, 0, SEAT_Z), (0, 0, 1)),
              ((0, 0, ARM_TOP), (0, 0, 1)), ((0, 0, ARM_POST[0]), (0, 0, 1)), ((ARM_X, 0, 0), (1, 0, 0)), ((-ARM_X, 0, 0), (1, 0, 0)),
              ((0, FRONT_Y, 0), (0, 1, 0)), ((0, BACK_Y, 0), (0, 1, 0)),
              ((0, 0, CREST[1]), (0, 0, 1)), ((CREST[0], 0, 0), (1, 0, 0)), ((-CREST[0], 0, 0), (1, 0, 0))]
    for co, no in planes:
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-5, plane_co=co, plane_no=no)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    bm.to_mesh(obj.data)
    bm.free()
    me = obj.data
    cen = np.empty(len(me.polygons) * 3)
    me.polygons.foreach_get("center", cen)
    nrm = np.empty(len(me.polygons) * 3)
    me.polygons.foreach_get("normal", nrm)
    lab = [classify(c, n) for c, n in zip(cen.reshape(-1, 3), nrm.reshape(-1, 3))]

    # материалы (для превью; в Roblox цвет/материал ставит скрипт)
    def mat(name, rgb, rough):
        mt = bpy.data.materials.new(name)
        b = mt.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (*rgb, 1)
        b.inputs["Roughness"].default_value = rough
        return mt
    m_wood = mat("Wood", (0.16, 0.07, 0.03), 0.45)
    m_fab = mat("Fabric", (0.30, 0.03, 0.04), 0.85)

    made = []
    for part in PARTS:
        ids = {i for i, l in enumerate(lab) if l == part}
        if not ids:
            continue
        o = obj.copy()
        o.data = obj.data.copy()
        o.name = o.data.name = f"Armchair_{part}"
        bpy.context.scene.collection.objects.link(o)
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bm.faces.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in ids], context='FACES')
        bm.to_mesh(o.data)
        bm.free()
        o.data.materials.clear()
        o.data.materials.append(m_wood if part in WOOD else m_fab)
        bpy.context.view_layer.objects.active = o
        for x in bpy.context.selected_objects:
            x.select_set(False)
        o.select_set(True)
        if len(o.data.polygons) > MAX_TRIS:                       # лимит MeshPart
            d = o.modifiers.new("dec", 'DECIMATE')
            d.ratio = MAX_TRIS / len(o.data.polygons) * 0.98
            bpy.ops.object.modifier_apply(modifier=d.name)
        # начало координат детали — в её центре (удобно в Roblox)
        bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
        made.append(o)
        log(f"{o.name}: {len(o.data.polygons)} треугольников")
    bpy.data.objects.remove(obj, do_unlink=True)
    log("всего:", sum(len(o.data.polygons) for o in made))

    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "Armchair_Carved.blend"))
    for o in made:
        o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=os.path.join(out, "Armchair_Carved.glb"), export_format='GLB', use_selection=True)
    bpy.ops.export_scene.fbx(filepath=os.path.join(out, "Armchair_Carved_Roblox.fbx"), use_selection=True,
                             axis_forward='-Z', axis_up='Y', apply_scale_options='FBX_SCALE_ALL', path_mode='STRIP')
    log("готово ->", out)


if __name__ == "__main__":
    main()
