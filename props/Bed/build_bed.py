"""
Кровать с аркой (по референсу): процедурная сборка в Blender.

Состав (отдельные объекты, каждый < 20 000 треугольников — подходит для Roblox MeshPart):
  Bed_Frame    — столбики (база, ствол, капитель), изголовье и изножье с гранёной аркой,
                 рамками и филёнками, верхние канты, боковые царги; фаски + Weighted Normals
  Bed_Mattress — матрас со скруглёнными рёбрами
  Bed_Blanket  — одеяло (драпировка: обёрнуто вокруг края матраса, свисает с раструбом и складками)
                 + отворот простыни у изголовья
  Bed_Pillow   — подушка с прошитыми краями, прислонена к изголовью

Размеры (м): ширина 1.45, длина 2.2, изголовье 1.45, изножье 0.8, верх матраса 0.62.

Запуск: blender --background --python build_bed.py -- out_dir [white|walnut]
Внутри Blender: Scripting -> Run Script (результат в коллекции "Bed").
"""

import math
import os
import random
import sys

import bpy
import bmesh
from mathutils import Matrix, Vector, noise

STYLE = "walnut"           # "walnut" — тёмное дерево, "white" — белая краска (как на референсе)

W = 1.45                   # ширина по столбикам
L = 2.20                   # длина по столбикам
POST = 0.11                # сечение столбика
HEAD_POST_H = 1.30
FOOT_POST_H = 0.80
MATT_W, MATT_BOTTOM, MATT_TOP = 1.21, 0.40, 0.62
MATT_GAP = 0.04            # зазор матраса до филёнок изголовья и изножья
PANEL_T = 0.045            # толщина филёнчатых щитов
HEAD_ARCH = (1.12, 1.42)   # высота щита у столбиков и в пике
FOOT_ARCH = (0.64, 0.76)
HEAD_PANEL_BOTTOM = 0.36
FOOT_PANEL_BOTTOM = 0.16

YH = L / 2 - POST / 2      # центр изголовья по Y (+Y — голова)
YF = -L / 2 + POST / 2     # центр изножья

random.seed(3)
PARTS = {}


def log(*a):
    print("[bed]", *a, flush=True)


def activate(o):
    for x in bpy.context.selected_objects:
        x.select_set(False)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)


def add(bm, group):
    PARTS.setdefault(group, []).append(bm)


# ----------------------------------------------------------------- примитивы
def box(bm, center, size):
    bmesh.ops.create_cube(bm, size=1.0,
                          matrix=Matrix.Translation(center) @ Matrix.Diagonal((*size, 1)))


def arch_points(half, z_side, z_peak):
    """Арка как на референсе: плоские «плечи» у столбиков, крутая грань вверх,
    пологий гранёный верх."""
    dz = z_peak - z_side
    prof = [(1.0, 0.0), (0.66, 0.0), (0.46, 0.6), (0.24, 0.9), (0.0, 1.0)]
    pts = [(-u * half, z_side + f * dz) for u, f in prof]
    pts += [(u * half, z_side + f * dz) for u, f in reversed(prof[:-1])]
    return pts


def prism(bm, poly_xz, y0, y1):
    """Призма из многоугольника в плоскости XZ, толщина по Y."""
    front = [bm.verts.new((x, y0, z)) for x, z in poly_xz]
    back = [bm.verts.new((x, y1, z)) for x, z in poly_xz]
    f0 = bm.faces.new(front)
    f1 = bm.faces.new(list(reversed(back)))
    n = len(poly_xz)
    for i in range(n):
        bm.faces.new((front[i], front[(i + 1) % n], back[(i + 1) % n], back[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return f0, f1


def panel_face_detail(bm, face, frame=0.055, recess=0.012, raised_inset=0.03, raised=0.009):
    """Рамка + утопленное поле + приподнятая филёнка на грани щита."""
    r = bmesh.ops.inset_region(bm, faces=[face], thickness=frame, depth=0.0)
    inner = [face]
    bmesh.ops.inset_region(bm, faces=inner, thickness=0.004, depth=-recess)   # фаска рамки внутрь
    bmesh.ops.inset_region(bm, faces=inner, thickness=raised_inset, depth=0.0)
    bmesh.ops.inset_region(bm, faces=inner, thickness=0.012, depth=raised)    # скошенная филёнка


def arch_board(bm, half, z_bottom, z_side, z_peak, y_center):
    top = arch_points(half, z_side, z_peak)
    poly = [(-half, z_bottom)] + top + [(half, z_bottom)]
    y0, y1 = y_center - PANEL_T / 2, y_center + PANEL_T / 2
    f0, f1 = prism(bm, poly, y0, y1)
    for f in (f0, f1):
        panel_face_detail(bm, f)
    return top


def arch_cap(bm, top, y_center, height=0.075, depth=0.095, lip=0.012):
    """Толстый верхний кант по арке (двухступенчатый профиль)."""
    for h, d, dz in ((height, depth, 0.0), (0.022, depth + 2 * lip, 0.004)):
        prev = None
        quads = []
        for x, z in top:
            ring = [bm.verts.new((x, y_center - d / 2, z + dz)), bm.verts.new((x, y_center + d / 2, z + dz)),
                    bm.verts.new((x, y_center + d / 2, z - h + dz)), bm.verts.new((x, y_center - d / 2, z - h + dz))]
            if prev:
                for k in range(4):
                    bm.faces.new((prev[k], prev[(k + 1) % 4], ring[(k + 1) % 4], ring[k]))
            else:
                bm.faces.new(list(reversed(ring)))
            prev = ring
        bm.faces.new(prev)


def post(bm, x, y, height):
    p = POST
    box(bm, Vector((x, y, 0.07)), (p + 0.035, p + 0.035, 0.14))            # база
    box(bm, Vector((x, y, 0.155)), (p + 0.018, p + 0.018, 0.03))           # пояс базы
    box(bm, Vector((x, y, height / 2)), (p, p, height))                    # ствол
    box(bm, Vector((x, y, height - 0.09)), (p + 0.016, p + 0.016, 0.03))   # пояс капители
    box(bm, Vector((x, y, height + 0.02)), (p + 0.03, p + 0.03, 0.04))     # капитель
    box(bm, Vector((x, y, height + 0.055)), (p + 0.008, p + 0.008, 0.03))  # верх


def build_frame():
    bm = bmesh.new()
    hx = W / 2 - POST / 2
    for sx in (-1, 1):
        post(bm, sx * hx, YH, HEAD_POST_H)
        post(bm, sx * hx, YF, FOOT_POST_H)
    half = hx - POST / 2 + 0.005
    top = arch_board(bm, half, HEAD_PANEL_BOTTOM, *HEAD_ARCH, YH)
    arch_cap(bm, top, YH)
    top = arch_board(bm, half, FOOT_PANEL_BOTTOM, *FOOT_ARCH, YF)
    arch_cap(bm, top, YF, height=0.06, depth=0.085)
    # нижние планки щитов и боковые царги
    box(bm, Vector((0, YH, HEAD_PANEL_BOTTOM - 0.03)), (2 * half, PANEL_T + 0.02, 0.06))
    box(bm, Vector((0, YF, FOOT_PANEL_BOTTOM - 0.03)), (2 * half, PANEL_T + 0.02, 0.06))
    rail_len = L - POST
    for sx in (-1, 1):
        box(bm, Vector((sx * (MATT_W / 2 - 0.035), 0, MATT_BOTTOM - 0.08)), (0.035, rail_len, 0.14))
    # реечное основание под матрасом
    for i in range(9):
        y = -rail_len / 2 + 0.15 + i * (rail_len - 0.3) / 8
        box(bm, Vector((0, y, MATT_BOTTOM - 0.025)), (MATT_W - 0.1, 0.07, 0.02))
    add(bm, "Bed_Frame")


def build_mattress():
    bm = bmesh.new()
    length = L - POST - PANEL_T - 2 * MATT_GAP
    box(bm, Vector((0, (YH + YF) / 2, (MATT_BOTTOM + MATT_TOP) / 2)),
        (MATT_W, length, MATT_TOP - MATT_BOTTOM))
    bmesh.ops.bevel(bm, geom=bm.edges[:], offset=0.035, segments=4, profile=0.5, affect='EDGES')
    add(bm, "Bed_Mattress")


def build_pillow():
    """Подушка: верх/низ — «пухлые» сетки, края прошиты (сходятся в шов)."""
    a, b, T = 0.40, 0.24, 0.09
    n, m = 28, 18
    bm = bmesh.new()
    grid = {}
    for side in (1, -1):
        for i in range(n + 1):
            for j in range(m + 1):
                u, v = -1 + 2 * i / n, -1 + 2 * j / m
                edge = i in (0, n) or j in (0, m)
                key = (i, j, 0 if edge else side)
                if key in grid:
                    continue
                puff = max(0.0, 1 - abs(u) ** 3.5) ** 0.55 * max(0.0, 1 - abs(v) ** 3.5) ** 0.55
                # морщинки и прижатый центр
                wr = 0.006 * noise.noise(Vector((u * 3, v * 3, side * 2.0)))
                dent = 0.18 * math.exp(-(u * u + v * v) * 3) if side > 0 else 0
                x = u * a * (1 - 0.06 * puff)
                y = v * b * (1 - 0.06 * puff)
                z = side * (T * puff * (1 - dent) + wr * puff)
                grid[key] = bm.verts.new((x, y, z))
    for side in (1, -1):
        def V(i, j):
            edge = i in (0, n) or j in (0, m)
            return grid[(i, j, 0 if edge else side)]
        for i in range(n):
            for j in range(m):
                q = (V(i, j), V(i + 1, j), V(i + 1, j + 1), V(i, j + 1))
                bm.faces.new(q if side > 0 else tuple(reversed(q)))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    rot = Matrix.Rotation(math.radians(-18), 4, 'X')                # приподнята к изголовью
    loc = Matrix.Translation((0, YH - PANEL_T / 2 - 0.25, MATT_TOP + 0.085))
    bmesh.ops.transform(bm, matrix=loc @ rot, verts=bm.verts)
    add(bm, "Bed_Pillow")


# ----------------------------------------------------------------- объекты
def to_object(name, bms):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    for part in bms:
        tmp = bpy.data.meshes.new("tmp")
        part.to_mesh(tmp)
        bm.from_mesh(tmp)
        bpy.data.meshes.remove(tmp)
        part.free()
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    collection().objects.link(o)
    return o


def collection():
    c = bpy.data.collections.get("Bed")
    if c is None:
        c = bpy.data.collections.new("Bed")
        bpy.context.scene.collection.children.link(c)
    return c


def finish_hard(o, bevel=0.006):
    activate(o)
    b = o.modifiers.new("Bevel", 'BEVEL')
    b.width, b.segments, b.limit_method, b.angle_limit = bevel, 2, 'ANGLE', math.radians(30)
    b.harden_normals = True
    bpy.ops.object.modifier_apply(modifier=b.name)
    for p in o.data.polygons:
        p.use_smooth = True
    wn = o.modifiers.new("WN", 'WEIGHTED_NORMAL')
    wn.keep_sharp = True
    bpy.ops.object.modifier_apply(modifier=wn.name)


def finish_soft(o):
    for p in o.data.polygons:
        p.use_smooth = True


# ----------------------------------------------------------------- одеяло (драпировка)
BLANKET_DROP = 0.40        # насколько свисает с боков (м)
EDGE_R = 0.035             # радиус обёртки вокруг края матраса
FOLD_AMP = 0.016           # глубина складок на свисающей части
FOLD_STEP = 0.22           # шаг складок


def _wrap(s, flare_k):
    """Длина s за краем -> (смещение наружу, опускание): дуга радиуса EDGE_R, потом свес с раструбом."""
    arc = EDGE_R * math.pi / 2
    if s <= arc:
        a = s / EDGE_R
        return EDGE_R * math.sin(a), EDGE_R * (1 - math.cos(a))
    d = s - arc
    return EDGE_R + flare_k * (d / BLANKET_DROP) ** 1.6, EDGE_R + d


def build_blanket(colliders=None):
    length = L - POST - PANEL_T - 2 * MATT_GAP
    m_foot = (YH + YF) / 2 - length / 2
    m_foot = max(m_foot, YF + 0.085 / 2 + 0.012 + 0.012)   # не заходить под нависающий кант изножья
    foot_gap = (m_foot - (YF + PANEL_T / 2)) - 0.012          # щель до изножья
    y_head = YH - PANEL_T / 2 - 0.42                          # начало одеяла (под подушкой)
    hw = MATT_W / 2 + 0.004
    top = MATT_TOP + 0.004
    side_len = EDGE_R * math.pi / 2 + BLANKET_DROP
    foot_len = 0.0                                          # в ногах одеяло заканчивается у канта изножья
    nx, ny = 56, 62                                        # ~18k треугольников с отворотом (лимит Roblox 20k)
    bm = bmesh.new()
    grid = []
    for j in range(ny + 1):
        Y = (m_foot - foot_len) + (y_head - m_foot + foot_len) * j / ny
        row = []
        for i in range(nx + 1):
            X = -(hw + side_len) + 2 * (hw + side_len) * i / nx
            sx, sy = max(0.0, abs(X) - hw), max(0.0, m_foot - Y)
            ox, dzs = _wrap(sx, 0.07)
            fy, dzf = _wrap(sy, 0.0)
            fy = min(fy, foot_gap)                             # в ногах ткань уходит в щель
            dz = max(dzs, dzf) + 0.45 * min(dzs, dzf)          # угол свисает «уголком»
            post_in = W / 2 - POST - 0.012                       # внутренняя грань столбиков (с учётом толщины ткани)
            near_post = min(1.0, max(0.0, (Y - (YF + POST / 2 + 0.01)) / 0.15))  # у столбиков изножья ткань подоткнута
            x = math.copysign(min(abs(X), hw) + ox * near_post, X)
            if near_post < 1.0:
                x = math.copysign(min(abs(x), post_in + (hw + 0.2 - post_in) * near_post), x)
            y = m_foot - fy if sy > 0 else Y
            z = max(top - dz, 0.21)                            # выше базы столбиков
            # складки на свисающих частях + лёгкая мятость сверху
            hang = max(dzs, dzf) / BLANKET_DROP
            along = Y if dzs >= dzf else X
            fold = FOLD_AMP * min(1.0, hang) * math.sin(along / FOLD_STEP * 2 * math.pi
                                                         + 2.5 * noise.noise(Vector((X * 2, Y * 2, 0.3))))
            wr = 0.004 * noise.noise(Vector((X * 6, Y * 6, 1.7)))
            if dzs >= dzf and sx > 0:
                x += math.copysign(fold * near_post, X)
            elif sy > 0:
                y -= fold * 0.5
            z += wr * (1 - min(1.0, hang))
            row.append(bm.verts.new((x, y, z)))
        grid.append(row)
    for j in range(ny):
        for i in range(nx):
            bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bm.faces:                       # нормали наружу (вверх)
        if f.normal.z < -0.5 and abs(f.calc_center_median().x) < hw:
            bmesh.ops.reverse_faces(bm, faces=bm.faces)
            break
    me = bpy.data.meshes.new("Bed_Blanket")
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new("Bed_Blanket", me)
    collection().objects.link(o)

    # отворот простыни у изголовья: копия полосы ткани чуть выше, с толщиной
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bm.normal_update()
    cuff_from = y_head - 0.40
    drop = [f for f in bm.faces if f.calc_center_median().y < cuff_from]
    bmesh.ops.delete(bm, geom=drop, context='FACES')
    for v in bm.verts:
        v.co += v.normal * 0.012
    cuff = bpy.data.meshes.new("cuff")
    bm.to_mesh(cuff)
    bm.free()
    cuff_o = bpy.data.objects.new("Bed_Cuff", cuff)
    collection().objects.link(cuff_o)
    for obj, t in ((o, 0.008), (cuff_o, 0.006)):
        activate(obj)
        sol = obj.modifiers.new("Solidify", 'SOLIDIFY')
        sol.thickness, sol.offset = t, 1.0
        bpy.ops.object.modifier_apply(modifier=sol.name)
        finish_soft(obj)
    activate(o)
    cuff_o.select_set(True)
    bpy.ops.object.join()
    return o


# ----------------------------------------------------------------- материалы
def material(name, color, rough, kind):
    mat = bpy.data.materials.new(name)
    if bpy.app.version < (5, 0):
        mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = rough
    mat.diffuse_color = (*color, 1)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    if kind == "wood":
        wave = nt.nodes.new("ShaderNodeTexWave")
        wave.wave_type = 'BANDS'
        wave.bands_direction = 'Z'
        wave.inputs["Scale"].default_value = 22
        wave.inputs["Distortion"].default_value = 3
        wave.inputs["Detail"].default_value = 4
        nt.links.new(coord.outputs["Object"], wave.inputs["Vector"])
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = tuple(c * 0.8 for c in color) + (1,)
        ramp.color_ramp.elements[1].color = tuple(min(1, c * 1.12) for c in color) + (1,)
        nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        ccw = "Coat Weight" if "Coat Weight" in bsdf.inputs else "Clearcoat"
        if ccw in bsdf.inputs:
            bsdf.inputs[ccw].default_value = 0.3 if STYLE == "walnut" else 0.1
    else:
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = 900
        nt.links.new(coord.outputs["Object"], nz.inputs["Vector"])
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.15
        bump.inputs["Distance"].default_value = 0.0005
        nt.links.new(nz.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
        sh = "Sheen Weight" if "Sheen Weight" in bsdf.inputs else "Sheen"
        if sh in bsdf.inputs:
            bsdf.inputs[sh].default_value = 0.3
    return mat


def main():
    global STYLE
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = os.path.abspath(args[0]) if args else None
    if len(args) > 1:
        STYLE = args[1]
    for o in list(bpy.data.objects):
        if o.name.startswith("Bed_"):
            bpy.data.objects.remove(o, do_unlink=True)
    PARTS.clear()
    build_frame()
    build_mattress()
    build_pillow()
    frame = to_object("Bed_Frame", PARTS["Bed_Frame"])
    mattress = to_object("Bed_Mattress", PARTS["Bed_Mattress"])
    pillow = to_object("Bed_Pillow", PARTS["Bed_Pillow"])
    finish_hard(frame)
    finish_soft(mattress)
    finish_soft(pillow)
    blanket = build_blanket()

    wood = material("M_Bed_Wood", (0.045, 0.022, 0.012) if STYLE == "walnut" else (0.8, 0.79, 0.76),
                    0.38 if STYLE == "walnut" else 0.5, "wood")
    linen = material("M_Bed_Linen", (0.80, 0.77, 0.70), 0.85, "linen")
    pillow_m = material("M_Bed_Pillow", (0.86, 0.84, 0.79), 0.8, "linen")
    for o, m in ((frame, wood), (mattress, linen), (blanket, linen), (pillow, pillow_m)):
        o.data.materials.append(m)
        activate(o)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.003)
        bpy.ops.object.mode_set(mode='OBJECT')
    for o in (frame, mattress, blanket, pillow):
        log(f"{o.name}: {sum(len(p.vertices) - 2 for p in o.data.polygons)} треугольников")

    if out:
        os.makedirs(out, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "Bed.blend"))
        for o in bpy.data.objects:
            o.select_set(o.name.startswith("Bed_"))
        bpy.ops.export_scene.gltf(filepath=os.path.join(out, "Bed.glb"), export_format='GLB', use_selection=True)
        # Roblox: метры, Y вверх, -Z вперёд (при импорте File Dimensions = Meters -> ~7.8 стадов в длину)
        bpy.ops.export_scene.fbx(filepath=os.path.join(out, "Bed_Roblox.fbx"), use_selection=True,
                                 axis_forward='-Z', axis_up='Y', apply_scale_options='FBX_SCALE_ALL',
                                 path_mode='STRIP')
        log(f"сохранено -> {out}")


if __name__ == "__main__":
    main()
