"""
Двуспальная кровать «1 в 1» с моделью Meshy (props/MeshyFurniture/Bed), построенная заново
из чистой геометрии и разделённая на детали. Размеры сняты с исходной модели.

Детали (каждая — отдельный объект / MeshPart в Roblox):
  Bed_Post_HL, Bed_Post_HR, Bed_Post_FL, Bed_Post_FR   — столбики (база, цоколь, ствол, капитель, навершие)
  Bed_Headboard        — щит изголовья с тремя филёнками и полкой
  Bed_Headboard_Cap    — арочный карниз изголовья с замковым камнем
  Bed_Footboard        — щит изножья с тремя филёнками и нижней тягой
  Bed_Footboard_Cap    — арочный карниз изножья с замковым камнем
  Bed_Rail_L, Bed_Rail_R — боковые царги
  Bed_Mattress, Bed_Sheet, Bed_Duvet, Bed_Duvet_Cuff, Bed_Pillow_L, Bed_Pillow_R

Без текстур (материалы ставятся в Roblox). Габарит 2.2 x 2.2 м, высота 1.43 м.
Изголовье — со стороны +Y.

Запуск: blender --background --python build_bed_king.py -- out_dir
"""

import math
import os
import sys

import bpy
import bmesh
from mathutils import Matrix, Vector, noise

POST_C = 1.01                     # центр столбика по |x| и |y|
HEAD_POST = dict(top=1.295, cap=(1.12, 1.22), shaft=0.135)
FOOT_POST = dict(top=0.787, cap=(0.60, 0.74), shaft=0.14)
BOARD_X = 0.93                    # щиты заходят в столбики (без щелей)
HEAD_Y = (0.955, 1.062)
FOOT_Y = (-1.065, -0.952)
HEAD_ARCH = [(0.93, 1.195), (0.50, 1.205), (0.45, 1.237), (0.40, 1.276), (0.30, 1.324),
             (0.20, 1.368), (0.10, 1.407), (0.0, 1.434)]
FOOT_ARCH = [(0.93, 0.655), (0.25, 0.668), (0.20, 0.684), (0.15, 0.706), (0.10, 0.721),
             (0.05, 0.732), (0.0, 0.738)]
RAIL = dict(x=(0.95, 1.035), z=(0.20, 0.35))
MATT = dict(x=0.93, y=(-0.93, 0.93), z=(0.32, 0.69))
DUVET = dict(top=0.722, y=(-0.90, 0.60), drop=0.36, out=1.045)   # край над царгой, не задевает столбики
CUFF_Y = (0.42, 0.60)
SHEET_Y = (0.50, 0.915)


def log(*a):
    print("[bed]", *a, flush=True)


def activate(o):
    for x in bpy.context.selected_objects:
        x.select_set(False)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)


def box(bm, x, y, z):
    c = Vector(((x[0] + x[1]) / 2, (y[0] + y[1]) / 2, (z[0] + z[1]) / 2))
    s = (x[1] - x[0], y[1] - y[0], z[1] - z[0])
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(c) @ Matrix.Diagonal((*s, 1)))


def cbox(bm, cx, cy, half, z):
    box(bm, (cx - half, cx + half), (cy - half, cy + half), z)


def prism_xz(bm, poly, y0, y1):
    f = [bm.verts.new((x, y0, z)) for x, z in poly]
    b = [bm.verts.new((x, y1, z)) for x, z in poly]
    bm.faces.new(f)
    bm.faces.new(list(reversed(b)))
    n = len(poly)
    for i in range(n):
        bm.faces.new((f[i], f[(i + 1) % n], b[(i + 1) % n], b[i]))


def arch(profile, dz=0.0):
    """Полная линия арки слева направо из половины профиля [(|x|, z)]."""
    right = [(x, z + dz) for x, z in sorted(profile)]
    left = [(-x, z) for x, z in reversed(right[1:])]
    return left + right


def make(name, bm, bevel=0.0, smooth=False):
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
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
        p.use_smooth = smooth                       # дерево — плоское затенение (квадратные столбики)
    return o


def subtract(o, boxes):
    for x, y, z in boxes:
        cb = bmesh.new()
        box(cb, x, y, z)
        me = bpy.data.meshes.new("cut")
        cb.to_mesh(me)
        cb.free()
        cut = bpy.data.objects.new("cut", me)
        bpy.context.scene.collection.objects.link(cut)
        m = o.modifiers.new("b", 'BOOLEAN')
        m.operation, m.solver, m.object = 'DIFFERENCE', 'EXACT', cut
        activate(o)
        bpy.ops.object.modifier_apply(modifier=m.name)
        bpy.data.objects.remove(cut)


# ----------------------------------------------------------------- каркас
def post(name, sx, sy, p):
    cx, cy = sx * POST_C, sy * POST_C
    bm = bmesh.new()
    cbox(bm, cx, cy, 0.072, (0.0, 0.17))               # база
    cbox(bm, cx, cy, 0.085, (0.17, 0.33))              # цоколь
    cbox(bm, cx, cy, 0.078, (0.33, 0.36))              # пояс
    cbox(bm, cx, cy, p["shaft"] / 2, (0.36, p["cap"][0]))   # ствол
    cbox(bm, cx, cy, 0.082, (p["cap"][0], p["cap"][0] + 0.03))
    cbox(bm, cx, cy, 0.095, (p["cap"][0] + 0.03, p["cap"][1]))   # капитель
    cbox(bm, cx, cy, 0.085, (p["cap"][1], p["top"] - 0.02))      # навершие
    cbox(bm, cx, cy, 0.07, (p["top"] - 0.02, p["top"]))
    return make(name, bm, bevel=0.006)


def headboard():
    y0, y1 = HEAD_Y
    bm = bmesh.new()
    top = arch(HEAD_ARCH, dz=-0.07)
    prism_xz(bm, [(-BOARD_X, 0.17)] + top + [(BOARD_X, 0.17)], y0, y1)
    box(bm, (-BOARD_X, BOARD_X), (y0 - 0.006, y1 + 0.006), (0.17, 0.31))      # нижняя тяга
    box(bm, (-BOARD_X, BOARD_X), (0.85, y0 + 0.001), (0.84, 0.875))    # полка над матрасом
    o = make("Bed_Headboard", bm)
    d = 0.022                                                           # глубина филёнок (со стороны кровати)
    cuts = []
    for s in (-1, 1):
        cuts.append((tuple(sorted((s * 0.50, s * 0.76))), (y0 - 0.01, y0 + d), (0.90, 1.07)))
        cuts.append((tuple(sorted((s * 0.50, s * 0.76))), (y0 - 0.01, y0 + d), (1.12, 1.15)))
    cuts.append(((-0.32, 0.32), (y0 - 0.01, y0 + d), (0.90, 1.17)))
    subtract(o, cuts)
    finish_bevel(o)
    # карниз-арка + замковый камень
    bm = bmesh.new()
    line = arch(HEAD_ARCH)
    band = [(x, z - 0.075) for x, z in reversed(line)]
    prism_xz(bm, line + band, 0.915, 1.10)
    key = [(-0.07, 1.30), (0.07, 1.30), (0.05, 1.44), (-0.05, 1.44)]
    prism_xz(bm, key, 0.895, 0.93)
    cap = make("Bed_Headboard_Cap", bm, bevel=0.005)
    return o, cap


def footboard():
    y0, y1 = FOOT_Y
    bm = bmesh.new()
    top = arch(FOOT_ARCH, dz=-0.06)
    prism_xz(bm, [(-BOARD_X, 0.17)] + top + [(BOARD_X, 0.17)], y0, y1)
    box(bm, (-BOARD_X, BOARD_X), (-1.071, y1), (0.17, 0.31))            # нижняя тяга
    o = make("Bed_Footboard", bm)
    d = 0.018
    cuts = [((x0, x1), (y0 - 0.01, y0 + d), (0.36, 0.52))
            for x0, x1 in ((-0.77, -0.33), (-0.23, 0.23), (0.33, 0.77))]
    subtract(o, cuts)
    finish_bevel(o)
    bm = bmesh.new()
    line = arch(FOOT_ARCH)
    band = [(x, z - 0.065) for x, z in reversed(line)]
    prism_xz(bm, line + band, -1.08, -0.92)
    key = [(-0.06, 0.64), (0.06, 0.64), (0.045, 0.745), (-0.045, 0.745)]
    prism_xz(bm, key, -1.10, -1.07)
    cap = make("Bed_Footboard_Cap", bm, bevel=0.005)
    return o, cap


def finish_bevel(o):
    m = o.modifiers.new("Bevel", 'BEVEL')
    m.width, m.segments, m.limit_method, m.angle_limit = 0.005, 2, 'ANGLE', math.radians(40)
    m.harden_normals = True
    activate(o)
    bpy.ops.object.modifier_apply(modifier=m.name)


def rails():
    out = []
    for s, n in ((-1, "L"), (1, "R")):
        bm = bmesh.new()
        box(bm, tuple(sorted((s * RAIL["x"][0], s * RAIL["x"][1]))), (FOOT_Y[1], HEAD_Y[0]), RAIL["z"])   # до щитов
        out.append(make(f"Bed_Rail_{n}", bm, bevel=0.006))
    return out


# ----------------------------------------------------------------- постель
def mattress():
    bm = bmesh.new()
    box(bm, (-MATT["x"], MATT["x"]), MATT["y"], MATT["z"])
    bmesh.ops.bevel(bm, geom=bm.edges[:], offset=0.04, segments=4, profile=0.5, affect='EDGES')
    return make("Bed_Mattress", bm, smooth=True)


def drape(name, y_range, top, drop_to, out_x, foot_drop=False, nx=60, ny=50, thick=0.012):
    """Ткань: ровный верх, по бокам огибает край и свисает до drop_to (слегка расширяясь),
    в ногах (foot_drop) — опускается к изножью."""
    hw = MATT["x"] + 0.01
    side = (top - drop_to) + 0.06
    bm = bmesh.new()
    grid = []
    y0, y1 = y_range
    for j in range(ny + 1):
        y = y0 + (y1 - y0) * j / ny
        row = []
        for i in range(nx + 1):
            u = -1 + 2 * i / nx
            X = u * (hw + side)
            sx = max(0.0, abs(X) - hw)
            r = 0.04
            if sx <= r * math.pi / 2:
                a = sx / r
                ox, dz = r * math.sin(a), r * (1 - math.cos(a))
            else:
                d = sx - r * math.pi / 2
                ox, dz = r + (out_x - hw - r) * min(1.0, d / (top - drop_to)) ** 0.6, r + d
            dz = min(dz, top - drop_to)
            x = math.copysign(min(abs(X), hw) + ox, X)
            z = top - dz
            if foot_drop:
                t = max(0.0, (y0 + 0.06 - y) / 0.06)
                z -= 0.04 * t
            wr = 0.004 * noise.noise(Vector((x * 4, y * 4, 0.3)))
            fold = 0.003 * math.sin(y * 7 + 2 * noise.noise(Vector((y, x, 1.1)))) * min(1.0, dz / 0.2)
            row.append(bm.verts.new((x + math.copysign(fold, x), y, z + wr * (1 - min(1.0, dz / 0.1)))))
        grid.append(row)
    for j in range(ny):
        for i in range(nx):
            bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))
    o = make(name, bm, smooth=True)
    m = o.modifiers.new("Solidify", 'SOLIDIFY')
    m.thickness, m.offset = thick, 1.0
    activate(o)
    bpy.ops.object.modifier_apply(modifier=m.name)
    return o


def pillow(name, cx):
    a, b, T = 0.37, 0.20, 0.08
    n, m = 24, 14
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
                wr = 0.005 * noise.noise(Vector((u * 3 + cx, v * 3, side * 2.0)))
                grid[key] = bm.verts.new((u * a * (1 - 0.05 * puff), v * b * (1 - 0.05 * puff),
                                          side * (T * puff + wr * puff)))
    for side in (1, -1):
        def V(i, j):
            return grid[(i, j, 0 if (i in (0, n) or j in (0, m)) else side)]
        for i in range(n):
            for j in range(m):
                q = (V(i, j), V(i + 1, j), V(i + 1, j + 1), V(i, j + 1))
                bm.faces.new(q if side > 0 else tuple(reversed(q)))
    M = Matrix.Translation((cx, 0.735, 0.84)) @ Matrix.Rotation(math.radians(-48), 4, 'X')   # прислонены к изголовью
    bmesh.ops.transform(bm, matrix=M, verts=bm.verts)
    return make(name, bm, smooth=True)


def main():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = os.path.abspath(a[0]) if a else None
    bpy.ops.wm.read_factory_settings(use_empty=True)
    wood, fabric = [], []
    for sy, p, tag in ((1, HEAD_POST, "H"), (-1, FOOT_POST, "F")):
        for sx, side in ((-1, "L"), (1, "R")):
            wood.append(post(f"Bed_Post_{tag}{side}", sx, sy, p))
    wood += [*headboard(), *footboard(), *rails()]
    fabric.append(mattress())
    fabric.append(drape("Bed_Sheet", SHEET_Y, DUVET["top"] - 0.004, DUVET["drop"] + 0.03, DUVET["out"] - 0.01))
    fabric.append(drape("Bed_Duvet", DUVET["y"], DUVET["top"], DUVET["drop"], DUVET["out"], foot_drop=True))
    fabric.append(drape("Bed_Duvet_Cuff", CUFF_Y, DUVET["top"] + 0.018, DUVET["drop"] + 0.02, DUVET["out"] + 0.012,
                        ny=12, thick=0.015))
    fabric += [pillow("Bed_Pillow_L", -0.43), pillow("Bed_Pillow_R", 0.43)]
    cols = {"Wood": (0.30, 0.15, 0.08), "Duvet": (0.35, 0.03, 0.05), "Linen": (0.85, 0.83, 0.78)}
    mats = {}
    for n, c in cols.items():
        m = bpy.data.materials.new(n)
        m.diffuse_color = (*c, 1)
        m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*c, 1)
        m.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.6 if n == "Wood" else 0.85
        mats[n] = m
    for o in wood + fabric:
        n = "Wood" if o in wood else "Duvet" if "Duvet" in o.name else "Linen"
        o.data.materials.clear()
        o.data.materials.append(mats[n])
        for p in o.data.polygons:
            p.material_index = 0
        log(f"{o.name}: {sum(len(p.vertices) - 2 for p in o.data.polygons)} треугольников")
    if out:
        os.makedirs(out, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "BedKing.blend"))
        for o in bpy.data.objects:
            o.select_set(o.name.startswith("Bed_"))
        bpy.ops.export_scene.gltf(filepath=os.path.join(out, "BedKing.glb"), export_format='GLB', use_selection=True)
        bpy.ops.export_scene.fbx(filepath=os.path.join(out, "BedKing_Roblox.fbx"), use_selection=True,
                                 axis_forward='-Z', axis_up='Y', apply_scale_options='FBX_SCALE_ALL',
                                 path_mode='STRIP')
        log(f"сохранено -> {out}")


if __name__ == "__main__":
    main()
