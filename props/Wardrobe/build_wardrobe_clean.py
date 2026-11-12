"""
Шкаф «1 в 1» с моделью из Meshy, построенный заново из чистой геометрии.

Размеры сняты с исходной модели (сканированием поверхности) и масштабированы до высоты 2.0 м.
Без текстур — материалы назначаются в Roblox (Wood / Metal).

Объекты (каждый — отдельный MeshPart в Roblox, все < 2 000 треугольников):
  Wardrobe_Body    — цоколь с ножками, корпус (пустой внутри: стенки, задняя панель, дно, крыша),
                     трёхступенчатый карниз, фронтон с молдингом и медальоном, рамка-четверть для дверей
  Wardrobe_Door_L  — левая створка: рама, утопленные филёнки (верх/низ), origin на петле
  Wardrobe_Door_R  — правая створка
  Wardrobe_Knob_L / _R  — ручки (латунь), привязаны к створкам
  Wardrobe_Hinges  — петли (металл)

Запуск: blender --background --python build_wardrobe_clean.py -- out_dir
"""

import math
import os
import sys

import bpy
import bmesh
from mathutils import Matrix, Vector

K = 2.0 / 1.903                  # масштаб: исходник (высота 1.903) -> 2.0 м
Z0 = 0.952                       # сдвиг: низ исходника -> 0

# --- размеры в единицах исходника (лицо в -Y) ---
CARC_X, CARC_Y, CARC_Z = 0.608, (-0.35, 0.375), (-0.85, 0.75)
BASE_X, BASE_Y, BASE_Z = 0.642, (-0.383, 0.410), (-0.929, -0.85)
FOOT_X0, FOOT_DY, FOOT_Z0 = 0.47, 0.165, -0.952
CORNICE = [  # (z0, z1, полуширина, выступ вперёд, выступ назад)
    (0.738, 0.763, 0.624, -0.375, 0.404),
    (0.763, 0.800, 0.641, -0.393, 0.424),
    (0.800, 0.851, 0.650, -0.403, 0.433),
]
CROWN_X = (0.20, 0.40)           # карниз: ровно при |x|<0.2, скос до |x|=0.4, дальше ровно
CROWN_LIFT = 0.10                # насколько карниз поднят в центре
MEDAL = (0.085, -0.385)          # медальон: радиус, выступ
DOOR_X, DOOR_Z, DOOR_Y = 0.538, (-0.834, 0.727), (-0.38, -0.35)
SEAM = 0.0015
PANEL_X = (0.105, 0.432)         # |x| филёнок (от шва)
PANELS_Z = [(-0.71, -0.36), (-0.145, 0.615)]
PANEL_DEPTH = 0.016
KNOB = (0.081, -0.25, 0.042, 0.041)   # |x|, z, радиус, вылет от двери
OPEN_X, OPEN_Z = 0.518, (-0.815, 0.708)   # проём (за дверями — четверть 2 см)
WALL = 0.02


def log(*a):
    print("[wardrobe]", *a, flush=True)


def activate(o):
    for x in bpy.context.selected_objects:
        x.select_set(False)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)


def box(bm, x, y, z):
    c = Vector(((x[0] + x[1]) / 2, (y[0] + y[1]) / 2, (z[0] + z[1]) / 2))
    s = (x[1] - x[0], y[1] - y[0], z[1] - z[0])
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(c) @ Matrix.Diagonal((*s, 1)))


def prism_xz(bm, poly, y0, y1):
    f = [bm.verts.new((x, y0, z)) for x, z in poly]
    b = [bm.verts.new((x, y1, z)) for x, z in poly]
    bm.faces.new(f)
    bm.faces.new(list(reversed(b)))
    n = len(poly)
    for i in range(n):
        bm.faces.new((f[i], f[(i + 1) % n], b[(i + 1) % n], b[i]))


def obj(name, bm, bevel=0.0):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    if bevel:
        m = o.modifiers.new("Bevel", 'BEVEL')
        m.width, m.segments, m.limit_method, m.angle_limit = bevel, 2, 'ANGLE', math.radians(40)
        m.harden_normals = True
        activate(o)
        bpy.ops.object.modifier_apply(modifier=m.name)
    for p in o.data.polygons:
        p.use_smooth = True
    return o


def build_body():
    bm = bmesh.new()
    # цоколь + 4 ножки
    box(bm, (-BASE_X, BASE_X), BASE_Y, BASE_Z)
    for sx in (-1, 1):
        for y in ((BASE_Y[0], BASE_Y[0] + FOOT_DY), (BASE_Y[1] - FOOT_DY, BASE_Y[1])):
            box(bm, tuple(sorted((sx * FOOT_X0, sx * BASE_X))), y, (FOOT_Z0, BASE_Z[0] + 0.001))
    # корпус: боковины, задняя стенка, дно, крыша, рамка проёма
    y0, y1 = CARC_Y
    z0, z1 = CARC_Z
    for sx in (-1, 1):
        box(bm, tuple(sorted((sx * OPEN_X, sx * CARC_X))), (y0, y1), (z0, z1))          # боковина + стойка рамки
    box(bm, (-OPEN_X, OPEN_X), (y1 - WALL, y1), (z0, z1))                              # задняя стенка
    box(bm, (-OPEN_X, OPEN_X), (y0, y1 - WALL), (z0, OPEN_Z[0]))                        # дно
    box(bm, (-OPEN_X, OPEN_X), (y0, y1 - WALL), (OPEN_Z[1], z1))                        # крыша
    # карниз в три ступени, изогнутый вверх в центре (ровно у краёв, скос, ровно в середине)
    xs = sorted({-c for c in CROWN_X} | set(CROWN_X) | {-0.66, 0.66})

    def lift(x):
        ax = abs(x)
        if ax >= CROWN_X[1]:
            return 0.0
        if ax <= CROWN_X[0]:
            return CROWN_LIFT
        return CROWN_LIFT * (CROWN_X[1] - ax) / (CROWN_X[1] - CROWN_X[0])
    for cz0, cz1, hx, yf, yb in CORNICE:
        px = [x for x in xs if abs(x) < hx] + [-hx, hx]
        px = sorted(set(px))
        poly = [(x, cz0 + lift(x)) for x in px] + [(x, cz1 + lift(x)) for x in reversed(px)]
        prism_xz(bm, poly, yf, yb)
    # фриз: заполняет пространство под поднятой частью карниза
    hx = CORNICE[0][2] - 0.01
    px = sorted(set([x for x in xs if abs(x) < hx] + [-hx, hx]))
    poly = [(x, CARC_Z[1] - 0.012) for x in px] + [(x, CORNICE[0][0] + lift(x) + 0.001) for x in reversed(px)]
    prism_xz(bm, poly, CARC_Y[0], CARC_Y[1])
    # медальон: полукруг, свисающий из-под карниза по центру
    mz_top = CORNICE[0][0] + CROWN_LIFT
    mr, my = MEDAL
    pts = [(mr * math.cos(math.pi + math.pi * i / 16), mz_top + mr * math.sin(math.pi + math.pi * i / 16))
           for i in range(17)]
    prism_xz(bm, pts, my, CARC_Y[0] + 0.002)
    return obj("Wardrobe_Body", bm, bevel=0.004)


def build_door(side):
    s = -1 if side == "L" else 1
    x0, x1 = sorted((s * SEAM, s * DOOR_X))
    bm = bmesh.new()
    box(bm, (x0, x1), DOOR_Y, DOOR_Z)
    o = obj(f"Wardrobe_Door_{side}", bm)
    # утопленные филёнки (булево вычитание) с фаской по краю
    for pz in PANELS_Z:
        px0, px1 = sorted((s * PANEL_X[0], s * PANEL_X[1]))
        cb = bmesh.new()
        box(cb, (px0, px1), (DOOR_Y[0] - 0.01, DOOR_Y[0] + PANEL_DEPTH), pz)
        cut = obj("cut", cb)
        m = o.modifiers.new("b", 'BOOLEAN')
        m.operation, m.solver, m.object = 'DIFFERENCE', 'EXACT', cut
        activate(o)
        bpy.ops.object.modifier_apply(modifier=m.name)
        bpy.data.objects.remove(cut)
    m = o.modifiers.new("Bevel", 'BEVEL')
    m.width, m.segments, m.limit_method, m.angle_limit = 0.004, 2, 'ANGLE', math.radians(40)
    m.harden_normals = True
    activate(o)
    bpy.ops.object.modifier_apply(modifier=m.name)
    return o


def build_knob(side):
    s = -1 if side == "L" else 1
    kx, kz, kr, ky = KNOB
    bm = bmesh.new()
    y_door = DOOR_Y[0]
    # ножка + сплюснутый шар
    bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=kr * 0.35, radius2=kr * 0.5, depth=ky * 0.45,
                          matrix=Matrix.Translation((s * kx, y_door - ky * 0.225, kz)) @ Matrix.Rotation(math.pi / 2, 4, 'X'))
    bmesh.ops.create_uvsphere(bm, u_segments=20, v_segments=12, radius=kr,
                              matrix=Matrix.Translation((s * kx, y_door - ky + kr * 0.55, kz)) @ Matrix.Diagonal((1, 0.55, 1, 1)))
    return obj(f"Wardrobe_Knob_{side}", bm)


def build_hinges():
    bm = bmesh.new()
    for s in (-1, 1):
        for z in (DOOR_Z[0] + 0.18, DOOR_Z[1] - 0.18):
            bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=0.009, radius2=0.009, depth=0.07,
                                  matrix=Matrix.Translation((s * (DOOR_X + 0.006), DOOR_Y[1] - 0.006, z)))
    return obj("Wardrobe_Hinges", bm)


def main():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = os.path.abspath(a[0]) if a else None
    bpy.ops.wm.read_factory_settings(use_empty=True)
    body = build_body()
    doors = {sd: build_door(sd) for sd in ("L", "R")}
    knobs = {sd: build_knob(sd) for sd in ("L", "R")}
    hinges = build_hinges()
    allo = [body, hinges, *doors.values(), *knobs.values()]
    # масштаб в метры, на пол
    T = Matrix.Translation((0, 0, Z0 * K)) @ Matrix.Diagonal((K, K, K, 1))
    for o in allo:
        o.data.transform(T)
        o.data.update()
    # петли: origin створки и её ручки — на оси петли
    zc = (DOOR_Z[0] + DOOR_Z[1]) / 2
    for sd, d in doors.items():
        s = -1 if sd == "L" else 1
        pivot = T @ Vector((s * DOOR_X, DOOR_Y[1], zc))
        for o in (d, knobs[sd]):
            o.data.transform(Matrix.Translation(-pivot))
            o.location = pivot
        knobs[sd].parent = d
        knobs[sd].location = (0, 0, 0)
    mats = {"Wood": (0.32, 0.17, 0.08), "Brass": (0.75, 0.55, 0.22), "Metal": (0.35, 0.35, 0.35)}
    for name, col in mats.items():
        m = bpy.data.materials.new(name)
        m.diffuse_color = (*col, 1)
        m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*col, 1)
        if name != "Wood":
            m.node_tree.nodes["Principled BSDF"].inputs["Metallic"].default_value = 1.0
            m.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.35
    for o in allo:
        n = "Brass" if "Knob" in o.name else "Metal" if "Hinge" in o.name else "Wood"
        o.data.materials.clear()                    # булево вычитание оставляет пустой слот
        o.data.materials.append(bpy.data.materials[n])
        for poly in o.data.polygons:
            poly.material_index = 0
        tris = sum(len(p.vertices) - 2 for p in o.data.polygons)
        log(f"{o.name}: {tris} треугольников")
    if out:
        os.makedirs(out, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "Wardrobe.blend"))
        for o in bpy.data.objects:
            o.select_set(o.name.startswith("Wardrobe_"))
        bpy.ops.export_scene.gltf(filepath=os.path.join(out, "Wardrobe.glb"), export_format='GLB', use_selection=True)
        bpy.ops.export_scene.fbx(filepath=os.path.join(out, "Wardrobe_Roblox.fbx"), use_selection=True,
                                 axis_forward='-Z', axis_up='Y', apply_scale_options='FBX_SCALE_ALL',
                                 path_mode='STRIP')
        log(f"сохранено -> {out}")


if __name__ == "__main__":
    main()
