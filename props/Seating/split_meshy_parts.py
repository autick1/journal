"""
Детализированные диван/кресло (Meshy + запечённые текстуры, props/MeshyFurniture) -> те же модели,
разрезанные на детали. Геометрия и текстуры остаются оригинальными (качество «как в Meshy»),
но каждая часть — отдельный объект / MeshPart: ножки, царга, сиденье, подлокотники, накладки,
рамка спинки, мягкая панель спинки, задняя панель.

Границы частей заданы по замерам исходных моделей (те же, что в build_seating.py).
Все части используют один набор текстур (общая UV-развёртка).

Запуск: blender --background --python split_meshy_parts.py -- Sofa.glb out_dir sofa|armchair
"""

import math
import os
import sys

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector

RULES = {
    "sofa": dict(prefix="Sofa", leg_z=0.15, base_z=0.27, seat_x=0.73, seat_top=0.47, arm_x=0.73,
                 back_y=0.125, back_x=0.80, front_y=-0.275, tilt=0.0, pivot=(0.23, 0.15), frame=0.06,
                 back_half=[(0.80, 0.15), (0.80, 0.70), (0.76, 0.745), (0.72, 0.832), (0.68, 0.887),
                            (0.64, 0.935), (0.60, 0.975), (0.56, 1.005), (0.52, 1.02), (0.40, 1.027),
                            (0.28, 1.023), (0.24, 1.04), (0.20, 1.088), (0.16, 1.108), (0.12, 1.12),
                            (0.06, 1.125), (0.0, 1.127)]),
    "armchair": dict(prefix="Armchair", leg_z=0.21, base_z=0.33, seat_x=0.28, seat_top=0.50, arm_x=0.28,
                     back_y=0.165, back_x=0.39, front_y=-0.315, tilt=8.5, pivot=(0.17, 0.47), frame=0.045, back_zmin=0.74,
                     back_half=[(0.37, 0.21), (0.37, 0.86), (0.30, 0.995), (0.24, 1.014), (0.20, 1.03),
                                (0.10, 1.10), (0.0, 1.10)]),
}
PARTS = ["Leg_FL", "Leg_FR", "Leg_BL", "Leg_BR", "Base", "Seat", "Arm_L", "Arm_R", "ArmFront_L", "ArmFront_R",
         "BackFrame", "BackPanel", "BackRear"]


def log(*a):
    print("[split]", *a, flush=True)


def outline(half):
    return list(half) + [(-x, z) for x, z in reversed(half[:-1])]


def inside(poly, x, z):
    c = False
    for i in range(len(poly)):
        x1, z1 = poly[i]
        x2, z2 = poly[(i + 1) % len(poly)]
        if (z1 > z) != (z2 > z) and x < (x2 - x1) * (z - z1) / (z2 - z1) + x1:
            c = not c
    return c


def edge_dist(poly, x, z):
    p = Vector((x, z))
    best = 1e9
    for i in range(len(poly)):
        a, b = Vector(poly[i]), Vector(poly[(i + 1) % len(poly)])
        ab = b - a
        t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.length_squared, 1e-12)))
        best = min(best, (a + ab * t - p).length)
    return best


def offset_poly(poly, d):
    n = len(poly)
    out = []
    for i in range(n):
        p0, p1, p2 = Vector(poly[i - 1]), Vector(poly[i]), Vector(poly[(i + 1) % n])
        e1, e2 = (p1 - p0).normalized(), (p2 - p1).normalized()
        n1, n2 = Vector((-e1.y, e1.x)), Vector((-e2.y, e2.x))
        bis = n1 + n2
        bis = n1 if bis.length < 1e-6 else bis.normalized()
        out.append(tuple(p1 + bis * (d / max(0.3, bis.dot(n1)))))
    area = lambda p: 0.5 * sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p)))
    return offset_poly(poly, -d) if abs(area(out)) > abs(area(poly)) else out


def cut_planes(bm, R, inner):
    """Прорезать сетку плоскостями по границам деталей -> ровные края, грани не пересекают границы."""
    t = math.radians(R["tilt"])
    py, pz = R["pivot"]
    rot = Matrix.Rotation(-t, 3, 'X')                       # выпрямленные координаты спинки -> мир
    piv = Vector((0, py, pz))
    planes = [((0, 0, R["leg_z"]), (0, 0, 1)), ((0, 0, R["base_z"]), (0, 0, 1)),
              ((R["arm_x"], 0, 0), (1, 0, 0)), ((-R["arm_x"], 0, 0), (1, 0, 0)),
              ((0, R["front_y"], 0), (0, 1, 0))]
    planes.append((tuple(piv + rot @ (Vector((0, R["back_y"], pz)) - piv)), tuple(rot @ Vector((0, 1, 0)))))
    for i in range(len(inner)):                              # стороны рамки спинки
        (x1, z1), (x2, z2) = inner[i], inner[(i + 1) % len(inner)]
        d = Vector((x2 - x1, 0, z2 - z1))
        if d.length < 1e-4:
            continue
        nrm = d.cross(Vector((0, 1, 0))).normalized()
        co = piv + rot @ (Vector((x1, py, z1)) - piv)
        planes.append((tuple(co), tuple(rot @ nrm)))
    for co, no in planes:
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-5, plane_co=co, plane_no=no)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])


def classify(c, n, R, poly, inner):
    x, y, z = c
    ax, sx = abs(x), ("L" if x < 0 else "R")
    # спинка: переводим в «выпрямленные» координаты (снимаем наклон)
    py, pz = R["pivot"]
    t = math.radians(R["tilt"])
    yu = py + (y - py) * math.cos(t) - (z - pz) * math.sin(t)
    zu = pz + (y - py) * math.sin(t) + (z - pz) * math.cos(t)
    nyu = n[1] * math.cos(t) - n[2] * math.sin(t)
    if z < R["leg_z"]:
        return f"Leg_{'F' if y < 0 else 'B'}{sx}"
    in_back = yu > R["back_y"] and ax <= R["back_x"] + 0.02 and zu > R["base_z"] - 0.02
    if z > R.get("back_zmin", 9.0) and y > 0.0:          # всё выше подлокотников сзади — спинка
        in_back = True
    if in_back:
        if not inside(inner, x, zu):
            return "BackFrame"
        return "BackRear" if nyu > 0.3 else "BackPanel"
    if z < R["base_z"]:
        return "Base"
    if ax >= R["arm_x"]:
        return f"ArmFront_{sx}" if y < R["front_y"] else f"Arm_{sx}"
    return "Seat"


def main():
    a = sys.argv[sys.argv.index("--") + 1:]
    src, out, kind = a[0], os.path.abspath(a[1]), a[2]
    R = RULES[kind]
    poly = outline(R["back_half"])
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
    inner = offset_poly(poly, R["frame"])
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    cut_planes(bm, R, inner)
    bm.to_mesh(obj.data)
    bm.free()
    me = obj.data
    cen = np.empty(len(me.polygons) * 3)
    me.polygons.foreach_get("center", cen)
    cen = cen.reshape(-1, 3)
    nrm = np.empty(len(me.polygons) * 3)
    me.polygons.foreach_get("normal", nrm)
    nrm = nrm.reshape(-1, 3)
    lab = [classify(c, n, R, poly, inner) for c, n in zip(cen, nrm)]
    P = R["prefix"]
    os.makedirs(out, exist_ok=True)
    made = []
    for part in PARTS:
        ids = {i for i, l in enumerate(lab) if l == part}
        if not ids:
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
        made.append(o)
        log(f"{o.name}: {len(o.data.polygons)} треугольников")
    bpy.data.objects.remove(obj, do_unlink=True)
    # текстуры для Roblox (SurfaceAppearance): Color / Roughness / Normal / Metalness
    mat = made[0].data.materials[0]
    os.makedirs(os.path.join(out, "textures"), exist_ok=True)
    nodes = mat.node_tree.nodes
    b = next(nd for nd in nodes if nd.type == 'BSDF_PRINCIPLED')

    def src_img(sock):
        if not b.inputs[sock].is_linked:
            return None
        nd = b.inputs[sock].links[0].from_node
        while nd.type != 'TEX_IMAGE':
            nd = next(i for i in nd.inputs if i.is_linked).links[0].from_node
        return nd.image
    for sock, key in (("Base Color", "Color"), ("Roughness", "Roughness"), ("Normal", "Normal")):
        img = src_img(sock)
        if img is not None:
            c = img.copy()
            c.filepath_raw = os.path.join(out, "textures", f"{P}_{key}.png")
            c.file_format = 'PNG'
            c.save()
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, f"{P}_Parts.blend"))
    for o in made:
        o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=os.path.join(out, f"{P}_Parts.glb"), export_format='GLB', use_selection=True)
    bpy.ops.export_scene.fbx(filepath=os.path.join(out, f"{P}_Parts_Roblox.fbx"), use_selection=True,
                             axis_forward='-Z', axis_up='Y', apply_scale_options='FBX_SCALE_ALL',
                             path_mode='COPY', embed_textures=True)   # текстуры внутри FBX -> Roblox сам создаст SurfaceAppearance
    log(f"готово -> {out}")


if __name__ == "__main__":
    main()
