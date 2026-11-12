"""
Шкаф из Meshy -> шкаф с открывающимися дверцами и пустой внутренностью.

Исходник (GLB из Meshy) — цельная сплошная сетка без UV. Скрипт:
  1. Вырезает две створки (булево пересечение с объёмом каждой двери — филёнки и ручки сохраняются).
  2. Корпус = исходник минус двери минус полость: внутри гладкие стенки и задняя панель,
     спереди остаётся рамка-четверть, на которую закрываются двери. Ничего лишнего внутри.
  3. Ставит точку вращения каждой створки на петлю (внешнее заднее ребро).
  4. Игровые сетки (корпус ~14k, створки по ~2.5k треугольников), общая UV-развёртка,
     запекание PBR-карт (дерево + латунные ручки, нормали с исходной модели, AO с открытыми дверями).
  5. Экспорт: GLB (три узла, двери вращаются вокруг своих origin), FBX для Roblox, карты PNG.

Запуск: blender --background --python build_wardrobe.py -- model.glb out_dir [1024]
"""

import math
import os
import runpy
import sys
import time

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector

HEIGHT = 2.0                      # итоговая высота, м
# всё ниже — в координатах исходной модели Meshy (высота 1.9, центр в 0, лицо в -Y)
DOOR_X = 0.538                    # внешние кромки створок
DOOR_Z = (-0.834, 0.727)          # низ и верх створок
DOOR_Y = (-0.45, -0.351)          # от выступа ручек до плоскости корпуса
SEAM = 0.0015                     # половина зазора между створками
CAVITY_X = 0.518                  # полость: оставляет 2 см четверти за дверями
CAVITY_Z = (-0.815, 0.708)
CAVITY_Y = (-0.37, 0.352)         # задняя стенка ~2 см
KNOB_Y = -0.393                   # всё впереди — латунные ручки
VOXEL = 0.0028                   # в единицах исходника (~3 мм в реальном размере)
LOW = {"Body": 19000, "Door_L": 5000, "Door_R": 5000}   # лимит Roblox — 20k на деталь

HERE = os.path.dirname(os.path.abspath(__file__))


def log(*a):
    print("[wardrobe]", *a, flush=True)


def activate(o):
    for x in bpy.context.selected_objects:
        x.select_set(False)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)


def box_obj(name, x, y, z):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    c = Vector(((x[0] + x[1]) / 2, (y[0] + y[1]) / 2, (z[0] + z[1]) / 2))
    s = (x[1] - x[0], y[1] - y[0], z[1] - z[0])
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(c) @ Matrix.Diagonal((*s, 1)))
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    return o


def boolean(target, cutter, op):
    m = target.modifiers.new("bool", 'BOOLEAN')
    m.operation, m.solver, m.object = op, 'MANIFOLD', cutter   # EXACT спотыкается о сетку Meshy
    activate(target)
    bpy.ops.object.modifier_apply(modifier=m.name)


def copy(o, name):
    c = o.copy()
    c.data = o.data.copy()
    c.name = c.data.name = name
    bpy.context.scene.collection.objects.link(c)
    return c


def split_parts(src):
    """Вырезать створки и полость из сплошной модели."""
    doors = {}
    for name, x in (("Door_L", (-DOOR_X, -SEAM)), ("Door_R", (SEAM, DOOR_X))):
        cut = box_obj("cut", x, DOOR_Y, DOOR_Z)
        d = copy(src, name)
        boolean(d, cut, 'INTERSECT')
        bpy.data.objects.remove(cut)
        doors[name] = d
    body = copy(src, "Body")
    cut = box_obj("cut", (-DOOR_X - 0.002, DOOR_X + 0.002), DOOR_Y, (DOOR_Z[0] - 0.001, DOOR_Z[1] + 0.001))
    boolean(body, cut, 'DIFFERENCE')
    bpy.data.objects.remove(cut)
    cav = box_obj("cav", (-CAVITY_X, CAVITY_X), CAVITY_Y, CAVITY_Z)
    boolean(body, cav, 'DIFFERENCE')
    bpy.data.objects.remove(cav)
    for o in [body, *doors.values()]:
        log(f"{o.name}: {len(o.data.polygons)} граней (полная)")
    return body, doors


def set_hinges(doors):
    """Origin створки — на петле: внешнее ребро, задняя плоскость, середина по высоте."""
    zc = (DOOR_Z[0] + DOOR_Z[1]) / 2
    for name, d in doors.items():
        s = -1 if name == "Door_L" else 1
        pivot = Vector((s * DOOR_X, DOOR_Y[1], zc))
        d.data.transform(Matrix.Translation(-pivot))
        d.location = pivot


def scale_all(objs, k):
    for o in objs:
        o.data.transform(Matrix.Diagonal((k, k, k, 1)))
        o.location = o.location * k
        o.data.update()


def decimate(o, tris):
    d = o.modifiers.new("dec", 'DECIMATE')
    o.data.calc_loop_triangles()
    d.ratio = min(1.0, tris / max(1, len(o.data.loop_triangles)))   # считаем треугольники, не квады
    d.use_collapse_triangulate = True
    activate(o)
    bpy.ops.object.modifier_apply(modifier=d.name)
    for p in o.data.polygons:
        p.use_smooth = True


def join_with_tag(objs, name):
    """Склеить в один меш (общая UV и текстуры), сохранив номер части в атрибуте 'part'."""
    parts = []
    for i, o in enumerate(objs):
        c = copy(o, f"{name}_{i}")
        c.data.transform(c.matrix_world)
        c.matrix_world = Matrix()
        a = c.data.attributes.new("part", 'INT', 'FACE')
        a.data.foreach_set("value", np.full(len(c.data.polygons), i, np.int32))
        parts.append(c)
    activate(parts[0])
    for c in parts[1:]:
        c.select_set(True)
    bpy.ops.object.join()
    j = parts[0]
    j.name = j.data.name = name
    return j


def move_part(o, part_ids, offset):
    me = o.data
    part = np.empty(len(me.polygons), np.int32)
    me.attributes["part"].data.foreach_get("value", part)
    verts = set()
    for p in me.polygons:
        if part[p.index] in part_ids:
            verts.update(p.vertices)
    for v in verts:
        me.vertices[v].co += offset
    me.update()


def flatten_normals(arr, low, k, zmin, apart):
    """Внутренние стенки и тыльные стороны створок — плоские: заливаем их тексели нейтральной нормалью
    (в исходнике сквозная щель-шов, которая иначе рисуется полосами внутри шкафа)."""
    me = low.data
    me.calc_loop_triangles()
    part = np.empty(len(me.polygons), np.int32)
    me.attributes["part"].data.foreach_get("value", part)
    uv = me.uv_layers.active.data
    H, W = arr.shape[:2]
    lo = Vector((-CAVITY_X * k - 0.01, CAVITY_Y[0] * k - 0.01, CAVITY_Z[0] * k - zmin - 0.01))
    hi = Vector((CAVITY_X * k + 0.01, CAVITY_Y[1] * k + 0.01, CAVITY_Z[1] * k - zmin + 0.01))
    n = 0
    for t in me.loop_triangles:
        pid = part[t.polygon_index]
        c = t.center - apart.get(pid, Vector())
        if pid == 0:
            ok = all(lo[i] < c[i] < hi[i] for i in range(3))
        else:
            ok = t.normal.y > 0.7                        # тыльная сторона створки (двери закрыты)
        if not ok:
            continue
        n += 1
        p = np.array([uv[l].uv[:] for l in t.loops]) * (W, H)
        mn = np.floor(p.min(0)).astype(int) - 2
        mx = np.ceil(p.max(0)).astype(int) + 2
        xs, ys = np.meshgrid(np.arange(max(mn[0], 0), min(mx[0], W)), np.arange(max(mn[1], 0), min(mx[1], H)))
        q = np.stack([xs.ravel() + 0.5, ys.ravel() + 0.5], 1)
        a_, b_, c_ = p
        d = (b_[0] - a_[0]) * (c_[1] - a_[1]) - (c_[0] - a_[0]) * (b_[1] - a_[1])
        if abs(d) < 1e-9:
            continue
        w1 = ((q[:, 0] - a_[0]) * (c_[1] - a_[1]) - (c_[0] - a_[0]) * (q[:, 1] - a_[1])) / d
        w2 = ((b_[0] - a_[0]) * (q[:, 1] - a_[1]) - (q[:, 0] - a_[0]) * (b_[1] - a_[1])) / d
        tol = 2.5 / max(abs(d) ** 0.5, 1.0)
        m = (w1 >= -tol) & (w2 >= -tol) & (w1 + w2 <= 1 + tol)
        arr[ys.ravel()[m], xs.ravel()[m], :3] = (0.5, 0.5, 1.0)
    log(f"плоские нормали: {n} треугольников (внутренность и тыльные стороны дверей)")


def main():
    a = sys.argv[sys.argv.index("--") + 1:]
    src_path, out = a[0], os.path.abspath(a[1])
    res = int(a[2]) if len(a) > 2 else 1024
    os.makedirs(os.path.join(out, "textures"), exist_ok=True)
    tf = runpy.run_path(os.path.join(HERE, "..", "MeshyFurniture", "texture_furniture.py"), run_name="lib")
    t0 = time.time()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=src_path)
    src = next(o for o in bpy.data.objects if o.type == 'MESH')
    activate(src)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    src.parent = None

    # вокселизация: убирает внутренние перепонки Meshy (иначе после разреза видны тёмные зигзаги)
    src.data.remesh_voxel_size = VOXEL
    activate(src)
    bpy.ops.object.voxel_remesh()
    log(f"вокселизация: {len(src.data.polygons)} граней")
    body, doors = split_parts(src)
    bpy.data.objects.remove(src)
    set_hinges(doors)
    k = HEIGHT / 1.903
    objs = [body, doors["Door_L"], doors["Door_R"]]
    scale_all(objs, k)
    # стоять на полу
    zmin = min((o.matrix_world @ v.co).z for o in objs for v in o.data.vertices)
    for o in objs:
        o.location.z -= zmin

    # high (для нормалей) и low (игровые)
    high = join_with_tag(objs, "High")
    lows = []
    for o in objs:
        lo = copy(o, o.name + "_low")
        decimate(lo, LOW[o.name])
        lows.append(lo)
    low = join_with_tag(lows, "Wardrobe")
    for o in lows:
        bpy.data.objects.remove(o)
    tf["unwrap"](low, res)

    # материалы: дерево + латунь (ручки — самые выступающие части створок)
    wood = tf["material"]("Wood", "wood")
    ramp = next(n for n in wood.node_tree.nodes if n.type == 'VALTORGB')   # тёплый орех без пятен
    ramp.color_ramp.elements[0].color = (0.16, 0.065, 0.028, 1)
    ramp.color_ramp.elements[1].color = (0.24, 0.10, 0.045, 1)
    wave = next(n for n in wood.node_tree.nodes if n.type == 'TEX_WAVE')    # волокна дерева
    wave.inputs["Scale"].default_value = 30
    wave.inputs["Distortion"].default_value = 6
    mix = next(n for n in wood.node_tree.nodes if n.type == 'MIX')
    mix.inputs["Factor"].default_value = 0.45
    wood.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.55
    brass = bpy.data.materials.new("Brass")
    bsdf = brass.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.62, 0.43, 0.17, 1)
    bsdf.inputs["Roughness"].default_value = 0.35
    bsdf.inputs["Metallic"].default_value = 1.0
    low.data.materials.clear()
    low.data.materials.append(wood)
    low.data.materials.append(brass)
    knob_y = (KNOB_Y) * k
    part = np.empty(len(low.data.polygons), np.int32)
    low.data.attributes["part"].data.foreach_get("value", part)
    cen = np.empty(len(low.data.polygons) * 3)
    low.data.polygons.foreach_get("center", cen)
    cen = cen.reshape(-1, 3)
    idx = ((part > 0) & (cen[:, 1] < knob_y)).astype(np.int32)
    low.data.polygons.foreach_set("material_index", idx)
    log(f"ручки: {int(idx.sum())} граней")

    # запекание (AO — с «открытыми» дверями: створки временно уносим, чтобы внутренность не почернела)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = 16
    sc.render.bake.use_pass_direct = sc.render.bake.use_pass_indirect = False
    sc.render.bake.use_pass_color = True
    img = tf["new_image"]
    base = img("BaseColor", res)
    tf["bake"](low, 'DIFFUSE', base, pass_filter={'COLOR'})
    rough = img("Roughness", res, "Non-Color")
    tf["bake"](low, 'ROUGHNESS', rough)
    metal = img("Metalness", res, "Non-Color")
    # metallic: подаём через emission
    saved = []
    for m, v in ((wood, 0.0), (brass, 1.0)):
        b = m.node_tree.nodes["Principled BSDF"]
        ec = b.inputs["Emission Color"] if "Emission Color" in b.inputs else b.inputs["Emission"]
        saved.append((ec, tuple(ec.default_value), b.inputs["Emission Strength"], b.inputs["Emission Strength"].default_value))
        ec.default_value = (v, v, v, 1)
        b.inputs["Emission Strength"].default_value = 1.0
    tf["bake"](low, 'EMIT', metal)
    for ec, c, es, s in saved:
        ec.default_value, es.default_value = c, s
    # нормали и AO — каждую часть отдельно: створки и корпус разнесены, чтобы лучи не цепляли соседей
    apart = {1: Vector((0, -20, 0)), 2: Vector((0, -40, 0))}
    for pid, off in apart.items():
        move_part(low, {pid}, off)
        move_part(high, {pid}, off)
    normal = img("Normal", res, "Non-Color")
    # короткие лучи: в исходнике есть сквозная щель-шов на уровне ручек, длинные лучи её «рисуют» на стенках
    tf["bake"](low, 'NORMAL', normal, high=high, cage=0.004, dist=0.008, normal_space='TANGENT')
    arr = tf["img_np"](normal)
    back = arr[..., 2] < 0.5
    arr[back, :3] = 1 - arr[back, :3]
    flatten_normals(arr, low, k, zmin, apart)
    normal.pixels.foreach_set(arr.ravel())
    sc.world = sc.world or bpy.data.worlds.new("World")
    sc.world.light_settings.distance = 0.15
    sc.cycles.samples = 48
    ao = img("AO", res, "Non-Color")
    tf["bake"](low, 'AO', ao, high=high)              # AO с детальной сетки — без фасеток
    for pid, off in apart.items():
        move_part(low, {pid}, -off)
        move_part(high, {pid}, -off)
    B, A = tf["img_np"](base), tf["img_np"](ao)
    col = B.copy()
    col[..., :3] = B[..., :3] * (0.4 + 0.6 * A[..., :1])
    color = img("Color", res)
    color.pixels.foreach_set(col.ravel())
    maps = {"Color": color, "Roughness": rough, "Metalness": metal, "Normal": normal, "AO": ao}
    for key, im in maps.items():
        im.filepath_raw = os.path.join(out, "textures", f"Wardrobe_{key}.png")
        im.file_format = 'PNG'
        im.save()

    # итоговый материал
    fm = bpy.data.materials.new("M_Wardrobe")
    nt = fm.node_tree
    b = nt.nodes["Principled BSDF"]

    def tex(key):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = maps[key]
        return n
    nt.links.new(tex("Color").outputs["Color"], b.inputs["Base Color"])
    nt.links.new(tex("Roughness").outputs["Color"], b.inputs["Roughness"])
    nt.links.new(tex("Metalness").outputs["Color"], b.inputs["Metallic"])
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tex("Normal").outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    low.data.materials.clear()
    low.data.materials.append(fm)

    # обратно на три объекта; у створок origin = петля
    bpy.data.objects.remove(high)
    hinge = {1: objs[1].location.copy(), 2: objs[2].location.copy()}
    for o in objs:
        bpy.data.objects.remove(o)
    names = {0: "Wardrobe_Body", 1: "Wardrobe_Door_L", 2: "Wardrobe_Door_R"}
    finals = {}
    for pid, name in names.items():
        o = copy(low, name)
        bm = bmesh.new()
        bm.from_mesh(o.data)
        layer = bm.faces.layers.int.get("part")
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f[layer] != pid], context='FACES')
        bm.to_mesh(o.data)
        bm.free()
        o.rotation_mode = 'XYZ'                     # импорт glTF ставит кватернионы — двери крутим по Z
        o.rotation_euler = (0, 0, 0)
        if pid in hinge:
            o.data.transform(Matrix.Translation(-hinge[pid]))
            o.location = hinge[pid]
        finals[pid] = o
        log(f"{name}: {len(o.data.polygons)} треугольников")
    bpy.data.objects.remove(low)
    for pid in (1, 2):
        finals[pid].parent = finals[0]
        finals[pid].matrix_parent_inverse = finals[0].matrix_world.inverted()
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "Wardrobe.blend"))
    for o in bpy.data.objects:
        o.select_set(o.name.startswith("Wardrobe_"))
    bpy.ops.export_scene.gltf(filepath=os.path.join(out, "Wardrobe.glb"), export_format='GLB', use_selection=True)
    bpy.ops.export_scene.fbx(filepath=os.path.join(out, "Wardrobe_Roblox.fbx"), use_selection=True,
                             axis_forward='-Z', axis_up='Y', apply_scale_options='FBX_SCALE_ALL',
                             path_mode='STRIP')
    log(f"готово за {time.time() - t0:.0f} с -> {out}")


if __name__ == "__main__":
    main()
