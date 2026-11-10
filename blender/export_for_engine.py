"""
Экспорт персонажа в игровой движок (Этап 9 гайда): FBX и/или glTF (GLB).

Перед экспортом:
  * запусти game_asset_checker.py — экспорт с FAIL-ошибками не рекомендуется;
  * сохрани .blend (скрипт экспортирует, но исходник не трогает).

Экспортируются объекты коллекции EXPORT_COLLECTION (по умолчанию "07_Export"),
если она пуста — выделенные объекты.

Пресеты движков:
  unity   — FBX, ось -Z вперёд / Y вверх, без leaf bones
  unreal  — FBX, Z вверх, scale 1.0 (сцена в метрах), без leaf bones
  godot   — GLB
  generic — GLB + FBX

Запуск из терминала:
  blender Character_Final.blend --background --python export_for_engine.py -- unreal D:/AI_3D_Projects/Creatures/ForestGuardian/Exports
"""

import os
import sys

import bpy

ENGINE = "generic"
OUT_DIR = "//../Exports"          # "//" = рядом с .blend
EXPORT_COLLECTION = "07_Export"
EXPORT_ANIMATIONS = True


def parse_args():
    engine, out = ENGINE, OUT_DIR
    if "--" in sys.argv:
        extra = sys.argv[sys.argv.index("--") + 1:]
        if extra:
            engine = extra[0]
        if len(extra) > 1:
            out = extra[1]
    return engine.lower(), out


def select_export_objects():
    objs = []
    for cname in (EXPORT_COLLECTION, "Bellhop"):          # "Bellhop" — коллекция build_bellhop.py
        coll = bpy.data.collections.get(cname)
        if coll and coll.all_objects:
            objs = list(coll.all_objects)
            break
    objs = objs or list(bpy.context.selected_objects)
    if not objs:
        raise RuntimeError(f"Нечего экспортировать: коллекция '{EXPORT_COLLECTION}' пуста и ничего не выделено")
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    return objs


def base_name():
    if bpy.data.filepath:
        stem = os.path.splitext(os.path.basename(bpy.data.filepath))[0]
        for suffix in ("_Final", "_LowPoly", "_HighPoly", "_Blockout"):
            stem = stem.replace(suffix, "")
        return stem
    return "Character"


def export_fbx(path, engine):
    kwargs = dict(
        filepath=path,
        use_selection=True,
        apply_unit_scale=True,
        apply_scale_options='FBX_SCALE_ALL',
        use_mesh_modifiers=True,
        mesh_smooth_type='FACE',
        use_tspace=True,
        add_leaf_bones=False,
        primary_bone_axis='Y',
        secondary_bone_axis='X',
        bake_anim=EXPORT_ANIMATIONS,
        bake_anim_use_all_actions=EXPORT_ANIMATIONS,
        path_mode='COPY',
        embed_textures=True,
    )
    if engine == "unity":
        kwargs.update(axis_forward='-Z', axis_up='Y')
    else:  # unreal / generic
        kwargs.update(axis_forward='-Y', axis_up='Z')
    bpy.ops.export_scene.fbx(**kwargs)


def export_glb(path):
    kwargs = dict(
        filepath=path,
        export_format='GLB',
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_texcoords=True,
        export_normals=True,
        export_tangents=True,
        export_materials='EXPORT',
        export_skins=True,
        export_animations=EXPORT_ANIMATIONS,
    )
    # Совместимость между версиями: отбрасываем неизвестные параметры
    props = bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
    bpy.ops.export_scene.gltf(**{k: v for k, v in kwargs.items() if k in props})


def flatten_materials():
    """Процедурные ноды не экспортируются в FBX/glTF (модель стала бы белой).
    Для материалов со свойствами flat_* временно отключаем ноды от Base Color /
    Roughness / Metallic и подставляем плоские PBR-значения. Возвращает функцию отката."""
    restore = []
    for mat in bpy.data.materials:
        if "flat_color" not in mat or not mat.node_tree:
            continue
        bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if bsdf is None:
            continue
        for sock, key in (("Base Color", "flat_color"), ("Roughness", "flat_roughness"),
                          ("Metallic", "flat_metallic")):
            inp = bsdf.inputs[sock]
            old_val = tuple(inp.default_value) if hasattr(inp.default_value, "__len__") else inp.default_value
            links = [(l.from_socket, l.to_socket) for l in inp.links]
            for l in list(inp.links):
                mat.node_tree.links.remove(l)
            inp.default_value = tuple(mat[key]) if sock == "Base Color" else float(mat[key])
            restore.append((mat, inp, old_val, links))

    def undo():
        for mat, inp, old_val, links in restore:
            inp.default_value = old_val
            for a, b in links:
                mat.node_tree.links.new(a, b)
    return undo


def main():
    engine, out = parse_args()
    out = bpy.path.abspath(out)
    undo_materials = flatten_materials()
    select_export_objects()
    name = base_name()
    done = []
    if engine in ("unity", "unreal", "generic"):
        d = os.path.join(out, "FBX")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, f"{name}_{engine}.fbx")
        export_fbx(p, engine)
        done.append(p)
    if engine in ("godot", "generic"):
        d = os.path.join(out, "GLTF")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, f"{name}.glb")
        export_glb(p)
        done.append(p)
    undo_materials()
    if not done:
        raise ValueError(f"Неизвестный пресет '{engine}'. Варианты: unity, unreal, godot, generic")
    for p in done:
        print(f"[export] {p}")


if __name__ == "__main__":
    main()
