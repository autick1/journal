"""
Подвижное тело коридорного: к ригу R15 добавляются кости пальцев и носков.

  {Left|Right}Finger{N}_{1..3} — каждый когтистый палец (их находит сам скрипт) получает цепочку
                                  из 3 костей по осевой линии пальца, веса плавно переходят по длине;
  {Left|Right}Toe              — носок ботинка (перекат стопы при шаге).

Все остальные суставы — стандартные R15 (Root, Waist, Neck, плечи, локти, запястья, бёдра, колени,
голеностопы): их двигает скрипт BellhopBody.client.lua. Кости лица (Jaw, глаза, фуражка) остаются
в модели, но не анимируются.

Вход: Bellhop_R15_Face.blend (результат roblox_face_rig.py).
Запуск: python roblox_body_rig.py -- Bellhop_R15_Face.blend out_dir [pose]
"""

import os
import sys
from collections import deque

import bpy
import numpy as np
from mathutils import Matrix, Vector

FINGER_CUT = 0.66      # где по длине кисти пальцы отделяются от ладони (0 — запястье, 1 — кончик)
MIN_FINGER = 30        # меньше вершин — не палец (шипы, обрывки)
TOE_START = 0.42       # носок — передние 42 % ботинка


def log(*a):
    print("[body]", *a, flush=True)


def activate(o):
    for x in bpy.context.selected_objects:
        x.select_set(False)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)


def smooth(x, a, b):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def adjacency(me):
    adj = [[] for _ in me.vertices]
    for e in me.edges:
        i, j = e.vertices
        adj[i].append(j)
        adj[j].append(i)
    return adj


def components(sel, adj):
    seen = np.zeros(len(sel), bool)
    comps = []
    for s in np.nonzero(sel)[0]:
        if seen[s]:
            continue
        q, comp = deque([s]), []
        seen[s] = True
        while q:
            v = q.popleft()
            comp.append(v)
            for u in adj[v]:
                if sel[u] and not seen[u]:
                    seen[u] = True
                    q.append(u)
        comps.append(np.array(comp))
    return comps


def geodesic(comp, co, adj, starts):
    """Расстояние по сетке внутри пальца от его основания."""
    inside = set(comp.tolist())
    dist = {int(s): 0.0 for s in starts}
    q = deque(int(s) for s in starts)
    while q:                                             # упрощённый Дейкстра (BFS с релаксацией)
        v = q.popleft()
        for u in adj[v]:
            if u in inside:
                d = dist[v] + float(np.linalg.norm(co[u] - co[v]))
                if d < dist.get(u, 1e9) - 1e-9:
                    dist[u] = d
                    q.append(u)
    return np.array([dist.get(int(v), 0.0) for v in comp])


def get_weights(obj):
    n = len(obj.data.vertices)
    names = [g.name for g in obj.vertex_groups]
    W = np.zeros((n, len(names)), np.float32)
    for v in obj.data.vertices:
        for g in v.groups:
            W[v.index, g.group] = g.weight
    return names, W


def put_weights(obj, names, W):
    n = W.shape[0]
    order = np.argsort(-W, 1)
    rows = np.arange(n)[:, None]
    keep = np.zeros_like(W)
    keep[rows, order[:, :4]] = W[rows, order[:, :4]]            # не больше 4 влияний (лимит Roblox)
    keep[keep < 0.01] = 0
    keep /= np.maximum(keep.sum(1, keepdims=True), 1e-9)
    for gi, name in enumerate(names):
        g = obj.vertex_groups.get(name) or obj.vertex_groups.new(name=name)
        g.remove(list(range(n)))
        for vi in np.nonzero(keep[:, gi])[0]:
            g.add([int(vi)], float(keep[vi, gi]), 'REPLACE')


def add_column(names, W, name):
    if name in names:
        return names, W
    return names + [name], np.concatenate([W, np.zeros((W.shape[0], 1), np.float32)], 1)


def rig_fingers(rig, side):
    obj = bpy.data.objects[f"{side}Hand"]
    me = obj.data
    hb = rig.data.bones[f"{side}Hand"]
    a, c = np.array(hb.head_local[:]), np.array(hb.tail_local[:])
    L = np.linalg.norm(c - a)
    ax = (c - a) / L
    co = np.array([v.co[:] for v in me.vertices])
    t = (co - a) @ ax / L
    adj = adjacency(me)
    comps = [cp for cp in components(t > FINGER_CUT, adj) if len(cp) >= MIN_FINGER]
    # порядок пальцев — по углу вокруг оси кисти
    ref = np.cross(ax, [0, 0, 1.0])
    ref /= np.linalg.norm(ref)
    ref2 = np.cross(ax, ref)
    ang = []
    for cp in comps:
        d = co[cp].mean(0) - a
        ang.append(np.arctan2(d @ ref2, d @ ref))
    comps = [comps[i] for i in np.argsort(ang)]
    names, W = get_weights(obj)
    hand_i = names.index(f"{side}Hand")
    chains = []
    for fi, cp in enumerate(comps, 1):
        tb = t[cp]
        base = cp[tb < tb.min() + 0.025]                 # вершины у разреза = основание пальца
        g = geodesic(cp, co, adj, base)
        s = g / max(g.max(), 1e-6)
        pts = []
        for lo, hi in ((0.0, 0.07), (0.3, 0.38), (0.62, 0.7), (0.93, 1.01)):
            m = (s >= lo) & (s < hi)
            pts.append(co[cp][m].mean(0) if m.any() else co[cp][np.argmin(np.abs(s - (lo + hi) / 2))])
        bnames = [f"{side}Finger{fi}_{k}" for k in (1, 2, 3)]
        for bn in bnames:
            names, W = add_column(names, W, bn)
        # веса вдоль пальца: кисть -> 1-я -> 2-я -> 3-я фаланга, переходы плавные
        w_hand = 1 - smooth(s, 0.0, 0.12)
        w1 = smooth(s, 0.0, 0.12) * (1 - smooth(s, 0.28, 0.4))
        w2 = smooth(s, 0.28, 0.4) * (1 - smooth(s, 0.6, 0.72))
        w3 = smooth(s, 0.6, 0.72)
        total = W[cp].sum(1)
        W[cp] = 0
        W[cp, hand_i] = w_hand * total
        for bn, w in zip(bnames, (w1, w2, w3)):
            W[cp, names.index(bn)] = w * total
        chains.append((bnames, pts))
        log(f"{side}: палец {fi} — {len(cp)} верш., длина {g.max():.2f}")
    put_weights(obj, names, W)
    return chains


def rig_toe(rig, side):
    obj = bpy.data.objects[f"{side}Foot"]
    me = obj.data
    co = np.array([v.co[:] for v in me.vertices])
    sole = co[:, 2] < co[:, 2].min() + 0.35              # ботинок (ниже голенища)
    y_front, y_back = co[sole, 1].min(), co[sole, 1].max()   # лицом в -Y: перед — меньший Y
    f = (y_back - co[:, 1]) / (y_back - y_front)        # 0 — пятка, 1 — носок
    w_toe = smooth(f, 1 - TOE_START - 0.08, 1 - TOE_START + 0.08) * (1 - smooth(co[:, 2], co[:, 2].min() + 0.3, co[:, 2].min() + 0.45))
    names, W = get_weights(obj)
    bn = f"{side}Toe"
    names, W = add_column(names, W, bn)
    total = W.sum(1)
    W *= (1 - w_toe)[:, None]
    W[:, names.index(bn)] += w_toe * total
    put_weights(obj, names, W)
    xc = co[sole, 0].mean()
    pivot = Vector((xc, y_back - (1 - TOE_START) * (y_back - y_front), co[:, 2].min() + 0.08))
    tip = Vector((xc, y_front, co[:, 2].min() + 0.08))
    log(f"{side}: носок — {int((w_toe > 0.5).sum())} верш.")
    return bn, pivot, tip


def main():
    a = sys.argv[sys.argv.index("--") + 1:]
    src, out = a[0], os.path.abspath(a[1])
    pose = "pose" in a
    os.makedirs(out, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=src)
    rig = bpy.data.objects["Armature"]
    fingers = {s: rig_fingers(rig, s) for s in ("Left", "Right")}
    toes = {s: rig_toe(rig, s) for s in ("Left", "Right")}

    activate(rig)
    bpy.ops.object.mode_set(mode='EDIT')
    eb = rig.data.edit_bones
    for side, chains in fingers.items():
        for bnames, pts in chains:
            parent = eb[f"{side}Hand"]
            for k, bn in enumerate(bnames):
                b = eb.new(bn)
                b.head, b.tail = Vector(pts[k].tolist()), Vector(pts[k + 1].tolist())
                b.parent = parent
                b.use_connect = False
                parent = b
    for side, (bn, pivot, tip) in toes.items():
        b = eb.new(bn)
        b.head, b.tail = pivot, tip
        b.parent = eb[f"{side}Foot"]
    bpy.ops.object.mode_set(mode='OBJECT')
    n_f = sum(len(c) for c in fingers.values())
    log(f"кости: {n_f} пальцев x 3 фаланги, 2 носка")

    if pose:
        render_pose(rig, fingers, out)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "Bellhop_R15_Body.blend"))
    activate(rig)
    for o in bpy.data.objects:
        if o.type == 'MESH':
            o.select_set(True)
    bpy.ops.export_scene.fbx(filepath=os.path.join(out, "Bellhop_R15_Body.fbx"), use_selection=True,
                             apply_unit_scale=True, apply_scale_options='FBX_SCALE_NONE',
                             axis_forward='-Z', axis_up='Y', add_leaf_bones=False,
                             primary_bone_axis='Y', secondary_bone_axis='X',
                             use_armature_deform_only=False, bake_anim=False, path_mode='STRIP')
    log("готово ->", out)


def finger_palm(rig, chain_names):
    p = [rig.data.bones[n].head_local for n in chain_names] + [rig.data.bones[chain_names[-1]].tail_local]
    return (p[0] + p[2]) / 2 - p[1]                     # пальцы изогнуты к ладони -> вектор к ладони


def hand_palm(rig, chains):
    """Общее направление ладони кисти: по изогнутым пальцам (почти прямой палец не определяет сторону)."""
    acc = Vector((0, 0, 0))
    for bnames, _ in chains:
        acc += finger_palm(rig, bnames)                  # длина = кривизна -> изогнутые пальцы весят больше
    return acc.normalized()


def render_pose(rig, fingers, out):
    """Проверка: покой / пальцы сжаты в когти / пальцы растопырены + носок."""
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.samples = 24
    sc.cycles.device = 'CPU'
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 600, 600
    w = bpy.data.worlds.new("w")
    sc.world = w
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.6, 0.6, 0.6, 1)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.lens = 50
    pb = rig.pose.bones
    hand = bpy.data.objects["RightHand"]
    co = np.array([(hand.matrix_world @ v.co)[:] for v in hand.data.vertices])
    c = Vector(co.mean(0).tolist())
    foot = bpy.data.objects["RightFoot"]
    cf = Vector(np.array([(foot.matrix_world @ v.co)[:] for v in foot.data.vertices]).mean(0).tolist())

    def set_fingers(amount):
        for side, chains in fingers.items():
            palm = hand_palm(rig, chains)
            for bnames, _ in chains:
                for bn in bnames:
                    bone = rig.data.bones[bn]
                    d = (bone.tail_local - bone.head_local).normalized()
                    axis_w = d.cross(palm).normalized()               # +угол: палец к ладони
                    axis_l = bone.matrix_local.to_3x3().inverted() @ axis_w
                    p = pb[bn]
                    p.rotation_mode = 'AXIS_ANGLE'
                    p.rotation_axis_angle = (amount, *axis_l)

    shots = []
    for i, (amt, toe, target, off) in enumerate([(0.0, 0.0, c, (-0.4, -3.6, 0.4)), (0.55, 0.0, c, (-0.4, -3.6, 0.4)),
                                                (-0.3, 0.0, c, (-0.4, -3.6, 0.4)), (0.0, -0.6, cf, (2.6, -2.2, 0.8))]):
        set_fingers(amt)
        for s in ("Left", "Right"):
            p = pb[f"{s}Toe"]
            p.rotation_mode = 'XYZ'
            p.rotation_euler = (toe, 0, 0)
        bpy.context.view_layer.update()
        cam.location = target + Vector(off)
        cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
        p = os.path.join(out, f"_b{i}.png")
        sc.render.filepath = p
        bpy.ops.render.render(write_still=True)
        shots.append(p)
    set_fingers(0.0)
    for s in ("Left", "Right"):
        pb[f"{s}Toe"].rotation_euler = (0, 0, 0)
    S = np.zeros((1200, 1200, 4), np.float32)
    for i, p in enumerate(shots):
        r, cc = divmod(i, 2)
        S[(1 - r) * 600:(2 - r) * 600, cc * 600:(cc + 1) * 600] = np.array(bpy.data.images.load(p).pixels[:]).reshape(600, 600, 4)
        os.remove(p)
    img = bpy.data.images.new("poses", 1200, 1200)
    img.pixels = S.ravel()
    img.filepath_raw = os.path.join(out, "body_poses.png")
    img.file_format = 'PNG'
    img.save()


if __name__ == "__main__":
    main()
