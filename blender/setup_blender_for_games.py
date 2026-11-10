"""
Настройка Blender для создания игровых персонажей (ЧАСТЬ 6 гайда).

Что делает:
  1. Включает Rigify (встроенный аддон; в новых версиях может быть расширением).
  2. Включает полезные встроенные аддоны (Node Wrangler, если есть).
  3. Ставит метрическую систему, метры, Unit Scale = 1.0.
  4. Выбирает Eevee, включает сглаживание.
  5. Включает автосохранение и резервные копии, сохраняет настройки.

Как запустить:
  A) В Blender: вкладка Scripting -> Open -> этот файл -> Run Script.
  B) Из терминала:  blender --background --python setup_blender_for_games.py
  C) Попросить Claude: «выполни файл setup_blender_for_games.py через execute_blender_code».

Скрипт безопасен: ничего не удаляет, только меняет настройки.
"""

import addon_utils
import bpy

AUTOSAVE_MINUTES = 2
BACKUP_VERSIONS = 3


def log(msg):
    print(f"[setup] {msg}")


def enable_addon(candidates):
    """Пытается включить первый доступный модуль из списка имён."""
    available = {m.__name__ for m in addon_utils.modules()}
    for name in candidates:
        if name in available:
            try:
                addon_utils.enable(name, default_set=True, persistent=True)
                log(f"аддон включён: {name}")
                return True
            except Exception as exc:  # noqa: BLE001
                log(f"не удалось включить {name}: {exc}")
    log(f"не найден ни один из: {', '.join(candidates)} "
        "(установи через Edit -> Preferences -> Get Extensions)")
    return False


def setup_units(scene):
    us = scene.unit_settings
    us.system = 'METRIC'
    us.length_unit = 'METERS'
    us.scale_length = 1.0
    log("единицы: Metric / Meters / scale 1.0")


def setup_render(scene):
    engines = [e.identifier for e in
               bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
    # Имя Eevee менялось между версиями: BLENDER_EEVEE_NEXT (4.2-4.x) / BLENDER_EEVEE
    for eng in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE'):
        if eng in engines:
            scene.render.engine = eng
            log(f"рендер: {eng}")
            break
    eevee = getattr(scene, 'eevee', None)
    if eevee is not None:
        for attr, value in (('taa_render_samples', 64), ('taa_samples', 16),
                            ('use_gtao', True), ('use_shadows', True)):
            if hasattr(eevee, attr):
                try:
                    setattr(eevee, attr, value)
                except Exception:  # noqa: BLE001
                    pass
    scene.render.film_transparent = False
    scene.view_settings.view_transform = 'AgX' if 'AgX' in [
        i.identifier for i in
        bpy.types.ColorManagedViewSettings.bl_rna.properties['view_transform'].enum_items
    ] else scene.view_settings.view_transform


def setup_preferences():
    prefs = bpy.context.preferences
    fp = prefs.filepaths
    fp.use_auto_save_temporary_files = True
    fp.auto_save_time = AUTOSAVE_MINUTES
    fp.save_version = BACKUP_VERSIONS
    if hasattr(fp, 'use_relative_paths'):
        fp.use_relative_paths = True
    if hasattr(prefs.edit, 'undo_steps'):
        prefs.edit.undo_steps = 64
    log(f"автосохранение каждые {AUTOSAVE_MINUTES} мин, бэкапов: {BACKUP_VERSIONS}")
    try:
        bpy.ops.wm.save_userpref()
        log("настройки сохранены (Preferences)")
    except Exception as exc:  # noqa: BLE001
        log(f"настройки применены, но не сохранены автоматически: {exc}")


def main():
    log(f"Blender {bpy.app.version_string}")
    enable_addon(['rigify', 'bl_ext.blender_org.rigify'])
    enable_addon(['node_wrangler', 'bl_ext.blender_org.node_wrangler'])
    for scene in bpy.data.scenes:
        setup_units(scene)
        setup_render(scene)
    setup_preferences()
    log("готово. Перезапусти Blender, чтобы всё точно подхватилось.")


if __name__ == "__main__":
    main()
