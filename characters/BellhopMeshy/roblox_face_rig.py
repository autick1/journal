"""
Оживление лица коридорного: к ригу R15 (результат roblox_rig.py) добавляются лицевые кости.

  Jaw       — челюсть: рот прорезан по линии смыкания зубов (верхний и нижний ряд расходятся),
              нижняя челюсть и подбородок плавно привязаны к кости, шея не тянется;
  Mouth     — новый меш: тёмная полость рта и язык (чтобы открытый рот не просвечивал насквозь);
  LeftEye / RightEye — светящиеся глаза на своих костях (взгляд, подёргивания);
  HatBone   — фуражка (подпрыгивает, покачивается).
Шея — стандартный сустав R15 Neck (поворот/наклон головы).

Все кости — дочерние к Head, в Roblox появляются как Bone внутри части Head:
их можно анимировать в Animation Editor или скриптом (BellhopFace.client.lua).

Вход: Bellhop_R15.blend. Запуск: python roblox_face_rig.py -- Bellhop_R15.blend out_dir [pose]
"""

import math
import os
import sys

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector


# Параметры лица (вид в лицо, см. face_map.png): центр, направление «из лица», линия рта, полуширина рта, край фуражки
FACE_CENTER = (0.2, -0.8, 6.05)
FACE_VIEW = (0.25, -3.2, -1.6)
LIP_V = -0.08                 # высота линии смыкания зубов в центре
LIP_CURVE = 0.07              # насколько уголки рта выше центра
HW = 0.31                     # полуширина рта
HAT_V = 0.4                   # нижний край околыша фуражки


def log(*a):
    print("[face]", *a, flush=True)


def activate(o):
    for x in bpy.context.selected_objects:
        x.select_set(False)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)


def smooth(x, a, b):
    """0 при x<=a, 1 при x>=b (плавно)."""
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def face_colors(obj):
    me = obj.data
    mat = me.materials[0]
    img = [n.image for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image and 'BaseColor' in n.image.name][0]
    W, H = img.size
    px = np.empty(W * H * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(H, W, 4)[..., :3]
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    cols = []
    for p in me.polygons:
        c = uv[p.loop_start:p.loop_start + p.loop_total].mean(0)
        cols.append(px[min(max(int(c[1] * (H - 1)), 0), H - 1), min(max(int(c[0] * (W - 1)), 0), W - 1)])
    return np.array(cols)


def set_weights(obj, W):
    """W: dict имя группы -> массив весов на вершину. Остальные группы масштабируются, <= 4 влияния."""
    me = obj.data
    n = len(me.vertices)
    names = [g.name for g in obj.vertex_groups]
    cur = np.zeros((n, len(names)), np.float32)
    for v in me.vertices:
        for g in v.groups:
            cur[v.index, g.group] = g.weight
    add = np.zeros(n, np.float32)
    for k, w in W.items():
        add += w
    cur *= (1 - np.clip(add, 0, 1))[:, None]
    for k, w in W.items():
        if k not in names:
            obj.vertex_groups.new(name=k)
            names.append(k)
            cur = np.concatenate([cur, np.zeros((n, 1), np.float32)], 1)
        cur[:, names.index(k)] += w
    order = np.argsort(-cur, 1)
    rows = np.arange(n)[:, None]
    keep = np.zeros_like(cur)
    keep[rows, order[:, :4]] = cur[rows, order[:, :4]]
    keep[keep < 0.01] = 0
    keep /= np.maximum(keep.sum(1, keepdims=True), 1e-9)
    for gi, name in enumerate(names):
        g = obj.vertex_groups[name]
        g.remove(list(range(n)))
        idx = np.nonzero(keep[:, gi])[0]
        for vi in idx:
            g.add([int(vi)], float(keep[vi, gi]), 'REPLACE')


def ellipsoid(center, axes, radii, u=20, v=12):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=u, v_segments=v, radius=1.0)
    M = Matrix((axes[0] * radii[0], axes[1] * radii[1], axes[2] * radii[2])).transposed()
    for vert in bm.verts:
        vert.co = Vector(center) + M @ vert.co
    return bm


def main():
    a = sys.argv[sys.argv.index("--") + 1:]
    src, out = a[0], os.path.abspath(a[1])
    pose = "pose" in a
    os.makedirs(out, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=src)
    rig = bpy.data.objects["Armature"]
    head = bpy.data.objects["Head"]
    eyes = bpy.data.objects["Eyes"]

    # ---------------- система координат лица
    E = np.array([v.co[:] for v in eyes.data.vertices])
    mid_x = (E[:, 0].max() + E[:, 0].min()) / 2
    eL = E[E[:, 0] > mid_x].mean(0)                    # левый глаз персонажа = +X
    eR = E[E[:, 0] <= mid_x].mean(0)
    cols = face_colors(head)
    br, sat = cols.mean(1), cols.max(1) - cols.min(1)
    teeth = (br > 0.45) & (sat < 0.15)
    cen = np.array([p.center[:] for p in head.data.polygons])
    nrm = np.array([p.normal[:] for p in head.data.polygons])
    # Система координат лица — вид «в лицо» (лицо смотрит вперёд и вниз). Снята по проекционной карте лица
    # (face_map.png): R — вправо (к левому глазу персонажа), Up — вверх по лицу (к фуражке), V — из лица наружу.
    C = Vector(FACE_CENTER)
    V = Vector(FACE_VIEW).normalized()
    R = Vector((1, 0, 0))
    R = (R - V * R.dot(V)).normalized()
    Up = V.cross(R).normalized()
    if Up.z < 0:
        Up = -Up
    Rn, Un, Vn = np.array(R[:]), np.array(Up[:]), np.array(V[:])

    def local(P):
        d = P - np.array(C[:])
        return d @ Rn, d @ Un, d @ Vn

    def lip(x):                                          # линия смыкания зубов (улыбка: уголки выше)
        return LIP_V + LIP_CURVE * (np.asarray(x) / HW) ** 2

    hw = HW
    red = (sat > 0.12) & (br < 0.45)                     # красное сукно: фуражка/воротник (не челюсть)
    au, av, ad = local(cen)
    front = teeth & (np.abs(au) < 0.12) & (np.abs(av - lip(au)) < 0.1)
    d0 = float(np.median(ad[front])) if front.sum() else float(np.median(ad[teeth]))
    log(f"лицо: V={np.round(Vn, 2)}, Up={np.round(Un, 2)}; губная линия {LIP_V}, полуширина рта {HW}, глубина зубов {d0:.2f}")

    # ---------------- разрез рта и веса челюсти — для Head и UpperTorso
    # (голова опущена к груди, поэтому нижние зубы и подбородок при разбиении R15 попали в UpperTorso)
    def jaw_pass(obj):
        activate(obj)
        me = obj.data
        cols_o = face_colors(obj)
        red_o = ((cols_o.max(1) - cols_o.min(1)) > 0.12) & (cols_o.mean(1) < 0.45)
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.faces.ensure_lookup_table()

        def classify(bm):
            fc = np.array([f.calc_center_median()[:] for f in bm.faces])
            fu, fv, fd = local(fc)
            return (fv < lip(fu)) & (fd > d0 - 0.6) & (np.abs(fu) < hw + 0.3) & (fv > lip(fu) - 0.6) & ~red_o

        lower_f = classify(bm)
        rip = []
        for e in bm.edges:
            if len(e.link_faces) != 2:
                continue
            f0, f1 = e.link_faces
            if lower_f[f0.index] == lower_f[f1.index]:
                continue
            c = np.array(((e.verts[0].co + e.verts[1].co) / 2)[:])
            u, v, dd = local(c[None])
            if abs(u[0]) <= hw * 0.97 and abs(v[0] - lip(u[0])) < 0.12 and dd[0] > d0 - 0.25:
                rip.append(e)
        bmesh.ops.split_edges(bm, edges=rip)
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        lower_f = classify(bm)
        vside = np.zeros(len(bm.verts))
        vred = np.zeros(len(bm.verts), bool)
        for v in bm.verts:
            lf = [lower_f[f.index] for f in v.link_faces]
            vside[v.index] = np.mean(lf) if lf else 0
            vred[v.index] = all(red_o[f.index] for f in v.link_faces) if v.link_faces else False
        bm.to_mesh(me)
        bm.free()
        co = np.array([v.co[:] for v in me.vertices])
        u, v, dd = local(co)
        below = lip(u) - v                               # >0 — ниже линии рта
        w = np.where(vside > 0.99, 1.0, smooth(below, 0.0, 0.07))
        w = np.where(vside > 0.0, w, np.minimum(w, smooth(below, 0.03, 0.09)))
        w *= 1 - smooth(np.abs(u), hw + 0.03, hw + 0.25)          # уголки рта — плавно
        w *= smooth(dd, d0 - 0.55, d0 - 0.25)                       # вглубь головы (к шарниру) — на нет
        w *= 1 - smooth(below, 0.42, 0.62)                          # ниже подбородка (шея) — на нет
        w[vred] = 0.0                                                # сукно воротника не двигается с челюстью
        log(f"{obj.name}: разрез {len(rip)} рёбер, на челюсти {int((w > 0.5).sum())} верш.")
        return co, u, v, w.astype(np.float32)

    co_t, _, _, w_t = jaw_pass(bpy.data.objects["UpperTorso"])
    set_weights(bpy.data.objects["UpperTorso"], {"Jaw": w_t})
    co, u, v, w_jaw = jaw_pass(head)

    # фуражка: всё выше нижнего края околыша
    w_hat = (smooth(v, HAT_V, HAT_V + 0.08) * (w_jaw < 0.01)).astype(np.float32)
    set_weights(head, {"Jaw": w_jaw, "HatBone": w_hat})
    log(f"фуражка: {int((w_hat > 0.5).sum())} верш.")
    L, U, N = Rn, Un, Vn
    M = C
    eyes_mid = Vector(((eL + eR) / 2).tolist())
    zs = co[:, 2]

    # глаза — каждый на свою кость
    ev_u = (E - eyes_mid[:]) @ L
    set_weights(eyes, {"LeftEye": (ev_u > 0).astype(np.float32), "RightEye": (ev_u <= 0).astype(np.float32)})

    # ---------------- полость рта и язык
    Lv, Uv, Nv = Vector(L.tolist()), Vector(U.tolist()), Vector(N.tolist())
    lipM = M + Uv * float(lip(0)) + Nv * d0              # точка смыкания зубов в центре рта
    cav = ellipsoid(lipM - Nv * 0.3, (Lv, Uv, Nv), (hw * 0.92, 0.2, 0.24))
    tng = ellipsoid(lipM - Nv * 0.26 - Uv * 0.1, (Lv, Uv, Nv), (hw * 0.55, 0.05, 0.17), 16, 8)
    mouth_me = bpy.data.meshes.new("Mouth")
    bm = bmesh.new()
    for part in (cav, tng):
        tmp = bpy.data.meshes.new("tmp")
        part.to_mesh(tmp)
        bm.from_mesh(tmp)
        bpy.data.meshes.remove(tmp)
        part.free()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(mouth_me)
    bm.free()
    mouth = bpy.data.objects.new("Mouth", mouth_me)
    bpy.context.scene.collection.objects.link(mouth)
    mm = bpy.data.materials.new("Mouth_Dark")
    mm.use_nodes = True
    mm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.05, 0.004, 0.006, 1)
    mouth_me.materials.append(mm)
    mco = np.array([v.co[:] for v in mouth_me.vertices])
    mv = (mco - np.array(lipM[:])) @ U
    n_cav = len(mco) - 16 * 7 - 2
    wj = smooth(-mv, -0.03, 0.06).astype(np.float32)
    wj[n_cav:] = 1.0                                     # язык — целиком на челюсти
    mouth.vertex_groups.new(name="Head").add(list(range(len(mco))), 1.0, 'REPLACE')
    set_weights(mouth, {"Jaw": wj})
    mouth.parent = rig
    mouth.modifiers.new("Armature", 'ARMATURE').object = rig

    # ---------------- кости
    activate(rig)
    bpy.ops.object.mode_set(mode='EDIT')
    eb = rig.data.edit_bones
    hb = eb["Head"]
    hinge = lipM - Nv * 0.45 + Uv * 0.04
    jaw = eb.new("Jaw")
    jaw.head, jaw.tail = hinge, lipM - Uv * 0.3 + Nv * 0.05
    jaw.parent = hb
    jaw.align_roll(Nv)                                  # локальная X = поперёк лица (ось открывания рта)
    for name, c in (("LeftEye", eL), ("RightEye", eR)):
        b = eb.new(name)
        c = Vector(c.tolist())
        b.head, b.tail = c - Nv * 0.25, c
        b.align_roll(Uv)
        b.parent = hb
    hat_pts = co[(v > HAT_V) & (v < HAT_V + 0.1)]
    hc = Vector(hat_pts.mean(0).tolist())
    hat = eb.new("HatBone")
    hat.head, hat.tail = hc, hc + (Vector(hb.tail) - Vector(hb.head)).normalized() * 0.6
    hat.align_roll(Nv)
    hat.parent = hb
    bpy.ops.object.mode_set(mode='OBJECT')
    log("кости добавлены: Jaw, LeftEye, RightEye, HatBone")

    paint_eye_sockets(head, out)
    if pose:
        render_pose(rig, out)

    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "Bellhop_R15_Face.blend"))
    activate(rig)
    for o in bpy.data.objects:
        if o.type == 'MESH':
            o.select_set(True)
    bpy.ops.export_scene.fbx(filepath=os.path.join(out, "Bellhop_R15_Face.fbx"), use_selection=True,
                             apply_unit_scale=True, apply_scale_options='FBX_SCALE_NONE',
                             axis_forward='-Z', axis_up='Y', add_leaf_bones=False,
                             primary_bone_axis='Y', secondary_bone_axis='X',
                             use_armature_deform_only=False, bake_anim=False, path_mode='STRIP')
    log("готово ->", out)


def paint_eye_sockets(head, out, tex=1024):
    """На текстуре под светящимися глазами нарисованы белые пятна — закрашиваем их цветом маски,
    чтобы при движении глаз и моргании под ними была чёрная маска. Сохраняем текстуры для Roblox."""
    mat = head.data.materials[0]
    imgs = {n.image.name.split("_")[-1]: n.image for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image}
    col, em = imgs["BaseColor"].copy(), imgs["Emission"].copy()
    col.scale(tex, tex)
    em.scale(tex, tex)
    C = np.empty(tex * tex * 4, np.float32)
    col.pixels.foreach_get(C)
    C = C.reshape(tex, tex, 4)
    Em = np.empty(tex * tex * 4, np.float32)
    em.pixels.foreach_get(Em)
    mask = Em.reshape(tex, tex, 4)[..., :3].mean(-1) > 0.2
    for _ in range(4):                                   # чуть расширить пятна
        m2 = mask.copy()
        m2[1:] |= mask[:-1]
        m2[:-1] |= mask[1:]
        m2[:, 1:] |= mask[:, :-1]
        m2[:, :-1] |= mask[:, 1:]
        mask = m2
    C[mask, :3] = (0.025, 0.022, 0.024)
    col.pixels.foreach_set(C.ravel())
    os.makedirs(os.path.join(out, "textures"), exist_ok=True)
    col.filepath_raw = os.path.join(out, "textures", "Bellhop_Color.png")
    col.file_format = 'PNG'
    col.save()
    # и в превью-материале тоже
    for n in mat.node_tree.nodes:
        if n.type == 'TEX_IMAGE' and n.image and n.image.name.endswith("BaseColor"):
            n.image = col
    for key, name in (("Metallic", "Metalness"), ("Roughness", "Roughness"), ("Normal", "Normal")):
        im = imgs[key].copy()
        im.scale(tex, tex)
        im.filepath_raw = os.path.join(out, "textures", f"Bellhop_{name}.png")
        im.file_format = 'PNG'
        im.save()
    log(f"текстуры: глазные пятна закрашены ({int(mask.sum())} пикс.)")


def render_pose(rig, out):
    """Проверка: 4 кадра — покой, рот открыт + взгляд, крик + поворот головы, наклон головы."""
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.samples = 24
    sc.cycles.device = 'CPU'
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 600, 600
    w = bpy.data.worlds.new("w")
    sc.world = w
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.55, 0.55, 1)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.lens = 55
    pb = rig.pose.bones
    for b in pb:
        b.rotation_mode = 'XYZ'
    head = bpy.data.objects["Head"]
    co = np.array([(head.matrix_world @ v.co)[:] for v in head.data.vertices if v.co.z > 6.0])
    c = Vector(co.mean(0).tolist())
    poses = [
        {},
        {"Jaw": (-0.45, 0, 0), "LeftEye": (0, 0, 0.25), "RightEye": (0, 0, 0.25)},
        {"Jaw": (-0.8, 0, 0), "Head": (0.0, 0.0, 0.35), "HatBone": (0.3, 0, 0)},
        {"Jaw": (-0.2, 0, 0), "Head": (0, 0.45, 0)},
    ]
    paths = []
    for i, ps in enumerate(poses):
        for b in pb:
            b.rotation_euler = (0, 0, 0)
        for k, r in ps.items():
            pb[k].rotation_euler = r
        bpy.context.view_layer.update()
        cam.location = c + Vector((0.25, -3.2, -1.6))
        cam.rotation_euler = (c - cam.location).to_track_quat('-Z', 'Y').to_euler()
        p = os.path.join(out, f"_pose{i}.png")
        sc.render.filepath = p
        bpy.ops.render.render(write_still=True)
        paths.append(p)
    for b in pb:
        b.rotation_euler = (0, 0, 0)
    S = np.zeros((1200, 1200, 4), np.float32)
    for i, p in enumerate(paths):
        r, cc = divmod(i, 2)
        S[(1 - r) * 600:(2 - r) * 600, cc * 600:(cc + 1) * 600] = np.array(bpy.data.images.load(p).pixels[:]).reshape(600, 600, 4)
        os.remove(p)
    img = bpy.data.images.new("poses", 1200, 1200)
    img.pixels = S.ravel()
    img.filepath_raw = os.path.join(out, "face_poses.png")
    img.file_format = 'PNG'
    img.save()


if __name__ == "__main__":
    main()
