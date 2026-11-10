"""
Роблокс-риг коридорного (R15): модель разбита на 15 частей по суставам и привязана к скелету.

Результат — FBX, который Roblox Studio (Import 3D) распознаёт как персонажа R15:
  * кости и меши названы по стандарту R15 (Head, UpperTorso, LowerTorso, LeftUpperArm, ...),
    иерархия Root -> HumanoidRootPart -> LowerTorso -> ...;
  * каждая часть — отдельный MeshPart (< 20 000 треугольников), все вместе ~24 000;
  * части скиннятся к костям с плавными весами на суставах — сгибы без щелей;
  * глаза — отдельный меш "Eyes" на кости Head (в Roblox ставится материал Neon);
  * HumanoidRootPart — невидимый бокс в тазу (нужен Humanoid для ходьбы и физики);
  * масштаб: 1 единица Blender = 1 стад (рост ~7 стадов), лицо смотрит в -Z (как в Roblox).

Вход: Bellhop_Meshy.blend (результат enhance_meshy.py).
Запуск: blender --background --python roblox_rig.py -- Bellhop_Meshy.blend out_dir
"""

import heapq
import os
import sys

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector

TOTAL_TRIS = 24000
HEIGHT_STUDS = 7.0
TEX = 1024
SMOOTH_ITERS = 8         # ширина плавного перехода весов на суставах (итерации по рёбрам сетки)

# Суставы в координатах исходной модели (метры; лицо в -Y; Left персонажа = +X).
# Сняты по срезам сетки Meshy-модели.
J = {
    "root":       (-0.04, 0.15, 0.17),
    "waist":      (-0.03, 0.12, 0.38),
    "neck":       (0.03, -0.06, 0.70),
    "head_top":   (0.08, -0.20, 0.93),
    "L_shoulder": (0.27, 0.05, 0.58), "R_shoulder": (-0.25, 0.00, 0.60),
    "L_elbow":    (0.35, 0.16, 0.27), "R_elbow":    (-0.41, 0.12, 0.27),
    "L_wrist":    (0.49, 0.03, -0.13), "R_wrist":   (-0.50, -0.10, -0.13),
    "L_hand_end": (0.56, -0.05, -0.45), "R_hand_end": (-0.56, -0.18, -0.45),
    "L_hip":      (0.05, 0.16, 0.17), "R_hip":      (-0.12, 0.14, 0.17),
    "L_knee":     (0.18, 0.06, -0.17), "R_knee":    (-0.21, 0.01, -0.17),
    "L_ankle":    (0.26, 0.17, -0.78), "R_ankle":   (-0.25, 0.06, -0.78),
    "L_toe":      (0.27, -0.05, -0.93), "R_toe":     (-0.26, -0.08, -0.93),
}

# кость: (начало, конец, родитель)
BONES = {
    "HumanoidRootPart": ("root", "waist", "Root"),
    "LowerTorso":    ("root", "waist", "HumanoidRootPart"),
    "UpperTorso":    ("waist", "neck", "LowerTorso"),
    "Head":          ("neck", "head_top", "UpperTorso"),
}
for side, s in (("Left", "L"), ("Right", "R")):
    BONES.update({
        f"{side}UpperArm": (f"{s}_shoulder", f"{s}_elbow", "UpperTorso"),
        f"{side}LowerArm": (f"{s}_elbow", f"{s}_wrist", f"{side}UpperArm"),
        f"{side}Hand":     (f"{s}_wrist", f"{s}_hand_end", f"{side}LowerArm"),
        f"{side}UpperLeg": (f"{s}_hip", f"{s}_knee", "LowerTorso"),
        f"{side}LowerLeg": (f"{s}_knee", f"{s}_ankle", f"{side}UpperLeg"),
        f"{side}Foot":     (f"{s}_ankle", f"{s}_toe", f"{side}LowerLeg"),
    })
DEFORM = [b for b in BONES if b != "HumanoidRootPart"]


def log(*a):
    print("[rig]", *a, flush=True)


def activate(o):
    for x in bpy.context.selected_objects:
        x.select_set(False)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)


def seg_dist(P, a, b):
    ab = b - a
    t = np.clip(((P - a) @ ab) / (ab @ ab), 0, 1)
    return np.linalg.norm(a + t[:, None] * ab - P, axis=1), t


def label_vertices(co, edges):
    """Метки костей: «ядра» у осей костей + распространение по рёбрам сетки (Dijkstra).
    Так когти не прилипают к ноге, даже если в пространстве они ближе к ней."""
    nb = len(DEFORM)
    D = np.empty((len(co), nb))
    T = np.empty((len(co), nb))
    for i, b in enumerate(DEFORM):
        h, t, _ = BONES[b]
        D[:, i], T[:, i] = seg_dist(co, np.array(J[h]), np.array(J[t]))
    near = D.argmin(1)
    inner = T[np.arange(len(co)), near]
    seed = (D.min(1) < 0.09) & (inner > 0.12) & (inner < 0.88)
    # Dijkstra
    adj = [[] for _ in range(len(co))]
    for a, b in edges:
        w = float(np.linalg.norm(co[a] - co[b]))
        adj[a].append((b, w))
        adj[b].append((a, w))
    dist = np.full(len(co), np.inf)
    lab = np.full(len(co), -1)
    heap = []
    for v in np.nonzero(seed)[0]:
        dist[v] = 0.0
        lab[v] = near[v]
        heap.append((0.0, int(v)))
    heapq.heapify(heap)
    while heap:
        d, v = heapq.heappop(heap)
        if d > dist[v]:
            continue
        for u, w in adj[v]:
            nd = d + w
            if nd < dist[u]:
                dist[u] = nd
                lab[u] = lab[v]
                heapq.heappush(heap, (nd, u))
    orphan = lab < 0                      # оторванные кусочки — по ближайшей кости
    lab[orphan] = near[orphan]
    log(f"метки: ядер {int(seed.sum())}, без связи с ядром {int(orphan.sum())}")
    return lab


def smooth_weights(lab, edges, n):
    W = np.zeros((len(lab), len(DEFORM)), np.float32)
    W[np.arange(len(lab)), lab] = 1.0
    e = np.asarray(edges)
    for _ in range(SMOOTH_ITERS):
        acc = np.zeros_like(W)
        cnt = np.zeros(n)
        np.add.at(acc, e[:, 0], W[e[:, 1]])
        np.add.at(acc, e[:, 1], W[e[:, 0]])
        np.add.at(cnt, e[:, 0], 1)
        np.add.at(cnt, e[:, 1], 1)
        W = 0.5 * W + 0.5 * acc / np.maximum(cnt, 1)[:, None]
    # не больше 4 влияний (лимит Roblox), нормировка
    order = np.argsort(-W, axis=1)
    W2 = np.zeros_like(W)
    rows = np.arange(len(W))[:, None]
    W2[rows, order[:, :4]] = W[rows, order[:, :4]]
    W2[W2 < 0.02] = 0
    W2 /= np.maximum(W2.sum(1, keepdims=True), 1e-9)
    return W2


def main():
    a = sys.argv[sys.argv.index("--") + 1:]
    src, out = a[0], os.path.abspath(a[1])
    os.makedirs(os.path.join(out, "textures"), exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=src)
    for o in list(bpy.data.objects):
        if o.name != "Bellhop_Meshy":
            bpy.data.objects.remove(o, do_unlink=True)
    body = bpy.data.objects["Bellhop_Meshy"]
    activate(body)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    mat = body.data.materials[0]
    imgs = {n.image.name.split("_")[-1]: n.image for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE'}

    # глаза (по карте свечения) — отдельно, до упрощения
    em = imgs["Emission"]
    E = np.empty(em.size[0] * em.size[1] * 4, np.float32)
    em.pixels.foreach_get(E)
    E = E.reshape(em.size[1], em.size[0], 4)[..., :3].mean(-1)
    me = body.data
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    eyes_bm = bmesh.new()
    vmap = {}
    for p in me.polygons:
        c = uv[p.loop_start:p.loop_start + p.loop_total].mean(0)
        i = min(max(int(c[1] * (em.size[1] - 1)), 0), em.size[1] - 1)
        j = min(max(int(c[0] * (em.size[0] - 1)), 0), em.size[0] - 1)
        if E[i, j] > 0.35:
            vs = []
            for vi in p.vertices:
                if vi not in vmap:
                    v = me.vertices[vi]
                    vmap[vi] = eyes_bm.verts.new(v.co + v.normal * 0.0015)
                vs.append(vmap[vi])
            try:
                eyes_bm.faces.new(vs)
            except ValueError:
                pass

    # glTF режет сетку по швам UV — свариваем (UV остаются на углах граней)
    bm = bmesh.new()
    bm.from_mesh(me)
    n0 = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    log(f"сварка швов: {n0} -> {len(bm.verts)} вершин")
    bm.to_mesh(me)
    bm.free()

    # упрощение до игрового бюджета (UV сохраняются)
    d = body.modifiers.new("dec", 'DECIMATE')
    d.ratio = TOTAL_TRIS / len(me.polygons)
    bpy.ops.object.modifier_apply(modifier=d.name)
    me = body.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    edges = [tuple(e.vertices) for e in me.edges]
    lab = label_vertices(co, edges)
    W = smooth_weights(lab, edges, len(co))
    for b in DEFORM:
        body.vertex_groups.new(name=b)
    for i, b in enumerate(DEFORM):
        idx = np.nonzero(W[:, i])[0]
        g = body.vertex_groups[b]
        for v in idx:
            g.add([int(v)], float(W[v, i]), 'REPLACE')

    # разбиение на 15 частей по доминирующей кости граней
    dom = W.argmax(1)
    face_part = np.array([np.bincount(dom[list(p.vertices)], minlength=len(DEFORM)).argmax() for p in me.polygons])
    parts = {}
    for i, b in enumerate(DEFORM):
        sel = face_part == i
        if not sel.any():
            continue
        o = body.copy()
        o.data = body.data.copy()
        o.name = o.data.name = b
        bpy.context.scene.collection.objects.link(o)
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bm.faces.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if not sel[f.index]], context='FACES')
        bm.to_mesh(o.data)
        bm.free()
        parts[b] = o
    bpy.data.objects.remove(body, do_unlink=True)
    log("части: " + ", ".join(f"{k} {len(v.data.polygons)}" for k, v in parts.items()))

    eyes_me = bpy.data.meshes.new("Eyes")
    eyes_bm.to_mesh(eyes_me)
    eyes = bpy.data.objects.new("Eyes", eyes_me)
    bpy.context.scene.collection.objects.link(eyes)
    m = bpy.data.materials.new("Eyes_Neon")
    m.diffuse_color = (1, 0.97, 0.9, 1)
    eyes_me.materials.append(m)
    eyes.vertex_groups.new(name="Head").add(list(range(len(eyes_me.vertices))), 1.0, 'REPLACE')
    parts["Eyes"] = eyes

    # HumanoidRootPart — бокс в тазу
    hrp_me = bpy.data.meshes.new("HumanoidRootPart")
    bm = bmesh.new()
    c = Vector(J["root"]) + Vector((0, 0, 0.1))
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(c) @ Matrix.Diagonal((0.3, 0.2, 0.3, 1)))
    bm.to_mesh(hrp_me)
    bm.free()
    hrp = bpy.data.objects.new("HumanoidRootPart", hrp_me)
    bpy.context.scene.collection.objects.link(hrp)
    hrp.vertex_groups.new(name="HumanoidRootPart").add(list(range(8)), 1.0, 'REPLACE')
    hm = bpy.data.materials.new("HumanoidRootPart")
    hm.diffuse_color = (1, 1, 1, 0)
    hrp_me.materials.append(hm)
    parts["HumanoidRootPart"] = hrp

    # скелет
    arm = bpy.data.armatures.new("Armature")
    rig = bpy.data.objects.new("Armature", arm)
    bpy.context.scene.collection.objects.link(rig)
    activate(rig)
    bpy.ops.object.mode_set(mode='EDIT')
    eb = {}
    root = arm.edit_bones.new("Root")
    root.head, root.tail = Vector(J["root"]) * Vector((1, 1, 0)) + Vector((0, 0, -0.955)), \
        Vector(J["root"]) * Vector((1, 1, 0)) + Vector((0, 0, -0.855))
    eb["Root"] = root
    for name, (h, t, parent) in BONES.items():
        b = arm.edit_bones.new(name)
        b.head, b.tail = Vector(J[h]), Vector(J[t])
        eb[name] = b
    for name, (h, t, parent) in BONES.items():
        eb[name].parent = eb[parent]
    bpy.ops.object.mode_set(mode='OBJECT')
    for o in parts.values():
        o.parent = rig
        o.modifiers.new("Armature", 'ARMATURE').object = rig

    # стоп на земле, масштаб в стады (1 BU = 1 стад), unit scale 0.01 — как требует Roblox
    k = HEIGHT_STUDS / 1.906
    rig.location = (0, 0, 0.955 * k)
    rig.scale = (k, k, k)
    activate(rig)
    for o in parts.values():
        o.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.context.scene.unit_settings.scale_length = 0.01

    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "Bellhop_R15.blend"))
    for key, name in (("BaseColor", "Color"), ("Metallic", "Metalness"), ("Roughness", "Roughness"),
                      ("Normal", "Normal")):
        img = imgs[key].copy()
        img.scale(TEX, TEX)
        img.filepath_raw = os.path.join(out, "textures", f"Bellhop_{name}.png")
        img.file_format = 'PNG'
        img.save()
    activate(rig)
    for o in parts.values():
        o.select_set(True)
    bpy.ops.export_scene.fbx(filepath=os.path.join(out, "Bellhop_R15.fbx"), use_selection=True,
                             apply_unit_scale=True, apply_scale_options='FBX_SCALE_NONE',
                             axis_forward='-Z', axis_up='Y', add_leaf_bones=False,
                             primary_bone_axis='Y', secondary_bone_axis='X',
                             use_armature_deform_only=False, bake_anim=False, path_mode='STRIP')
    log(f"готово -> {out}")


if __name__ == "__main__":
    main()
