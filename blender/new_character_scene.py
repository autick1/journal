"""
Создаёт стартовую сцену для нового персонажа / существа.

  * Коллекции по этапам пайплайна: 00_Reference ... 07_Export
  * Ростовой ориентир (1.80 м) и сетка-пол, чтобы с первого шага держать масштаб
  * Свет и камера для проверочных рендеров (вид спереди / сбоку)
  * Сохраняет <ROOT>/<Категория>/<Имя>/Blender/<Имя>_Blockout.blend

Запуск из терминала:
  blender --background --python new_character_scene.py -- ForestGuardian Creatures D:/AI_3D_Projects 2.4

  аргументы после "--":  имя  категория(Characters|Creatures)  корень  рост_в_метрах

Запуск внутри Blender / через Claude MCP: поменяй значения DEFAULTS ниже и выполни.
ВНИМАНИЕ: скрипт очищает ТЕКУЩУЮ сцену (это новая сцена). Сохрани открытый файл заранее.
"""

import os
import sys

import bpy

DEFAULTS = {
    "name": "ForestGuardian",
    "category": "Creatures",
    "root": "D:/AI_3D_Projects",
    "height": 2.4,  # рост существа в метрах (человек ~1.8)
}

COLLECTIONS = [
    "00_Reference",
    "01_Blockout",
    "02_HighPoly",
    "03_LowPoly",
    "04_Rig",
    "05_Bake",
    "06_Lights_Cameras",
    "07_Export",
]

SUBFOLDERS = [
    "Blender",
    "Textures/BaseColor", "Textures/Normal", "Textures/Roughness", "Textures/AO",
    "References",
    "Exports/FBX", "Exports/GLTF",
    "Backups",
]


def parse_args():
    cfg = dict(DEFAULTS)
    if "--" in sys.argv:
        extra = sys.argv[sys.argv.index("--") + 1:]
        keys = ["name", "category", "root", "height"]
        for k, v in zip(keys, extra):
            cfg[k] = float(v) if k == "height" else v
    return cfg


def clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras,
                  bpy.data.lights, bpy.data.curves):
        for item in list(block):
            if item.users == 0:
                block.remove(item)


def make_collections(scene):
    result = {}
    for name in COLLECTIONS:
        coll = bpy.data.collections.new(name)
        scene.collection.children.link(coll)
        result[name] = coll
    return result


def link_only(obj, coll):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)


def ref_material(name, rgba):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = rgba
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = rgba
        bsdf.inputs["Roughness"].default_value = 0.8
    return mat


def add_reference(colls, height):
    ref = colls["00_Reference"]

    # Ростовой ориентир человека 1.8 м (прямоугольник-силуэт)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(-1.2, 0, 0.9))
    human = bpy.context.active_object
    human.name = "REF_Human_1.80m"
    human.scale = (0.45, 0.25, 1.8)
    bpy.ops.object.transform_apply(scale=True)
    human.display_type = 'WIRE'
    human.hide_render = True
    link_only(human, ref)

    # Габарит существа
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, height / 2))
    box = bpy.context.active_object
    box.name = f"REF_Bounds_{height:.2f}m"
    box.scale = (height * 0.45, height * 0.3, height)
    bpy.ops.object.transform_apply(scale=True)
    box.display_type = 'BOUNDS'
    box.hide_render = True
    link_only(box, ref)

    # Пол
    bpy.ops.mesh.primitive_plane_add(size=10, location=(0, 0, 0))
    floor = bpy.context.active_object
    floor.name = "REF_Floor"
    floor.data.materials.append(ref_material("M_REF_Floor", (0.18, 0.18, 0.18, 1)))
    link_only(floor, ref)


def add_lights_and_cameras(colls, height):
    lc = colls["06_Lights_Cameras"]
    rigs = [
        ("LGT_Key", (3, -4, height * 1.5), 800),
        ("LGT_Fill", (-4, -2, height), 300),
        ("LGT_Rim", (0, 4, height * 1.4), 500),
    ]
    for name, loc, power in rigs:
        data = bpy.data.lights.new(name, type='AREA')
        data.energy = power
        data.size = 3
        obj = bpy.data.objects.new(name, data)
        obj.location = loc
        lc.objects.link(obj)
        # направляем свет на центр персонажа
        obj.rotation_euler = _look_at((-loc[0], -loc[1], height / 2 - loc[2]))

    dist = height * 2.6
    cams = [
        ("CAM_Front", (0, -dist, height * 0.55)),
        ("CAM_Side", (dist, 0, height * 0.55)),
        ("CAM_ThreeQuarter", (dist * 0.7, -dist * 0.7, height * 0.7)),
    ]
    first = None
    for name, loc in cams:
        data = bpy.data.cameras.new(name)
        data.lens = 50
        obj = bpy.data.objects.new(name, data)
        obj.location = loc
        obj.rotation_euler = _look_at((-loc[0], -loc[1], height * 0.5 - loc[2]))
        lc.objects.link(obj)
        first = first or obj
    bpy.context.scene.camera = first


def _look_at(direction):
    from mathutils import Vector
    return Vector(direction).to_track_quat('-Z', 'Y').to_euler()


def ensure_folders(project_dir):
    for sub in SUBFOLDERS:
        os.makedirs(os.path.join(project_dir, sub), exist_ok=True)


def main():
    cfg = parse_args()
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.length_unit = 'METERS'
    scene.unit_settings.scale_length = 1.0

    clear_scene()
    colls = make_collections(scene)
    add_reference(colls, cfg["height"])
    add_lights_and_cameras(colls, cfg["height"])

    # Пустышка-корень для будущего персонажа
    root = bpy.data.objects.new(f"{cfg['name']}_ROOT", None)
    root.empty_display_type = 'PLAIN_AXES'
    colls["01_Blockout"].objects.link(root)

    project_dir = os.path.join(cfg["root"], cfg["category"], cfg["name"])
    try:
        ensure_folders(project_dir)
        path = os.path.join(project_dir, "Blender", f"{cfg['name']}_Blockout.blend")
        bpy.ops.wm.save_as_mainfile(filepath=path)
        print(f"[scene] сохранено: {path}")
    except OSError as exc:
        print(f"[scene] сцена создана, но не сохранена ({exc}). Проверь путь root.")


if __name__ == "__main__":
    main()
