"""
Проверка готовности модели к игровому движку (КОНТРОЛЬ КАЧЕСТВА из системного промпта).

Проверяет все MESH-объекты (или только выделенные, если ONLY_SELECTED = True):
  * трансформации применены (scale = 1, rotation = 0)
  * количество треугольников против бюджета
  * n-gons (> 4 вершин), полюса с 6+ рёбрами
  * non-manifold рёбра, свободные вершины, дубликаты вершин
  * несогласованные нормали
  * наличие UV, UV вне 0-1, пересечение UV (приблизительно)
  * материалы назначены, нет пустых слотов
  * модификаторы не применены
  * для арматуры: имена костей, deform-кости, модель привязана, веса есть
  * габариты в метрах

Запуск: Scripting -> Run Script, или Claude через execute_blender_code.
Итог печатается в консоль и сохраняется в текстовый блок "QA_Report" внутри .blend.
Скрипт ничего не изменяет в геометрии.
"""

import bmesh
import bpy

ONLY_SELECTED = False

# Бюджет треугольников (ориентиры для современных игр; правь под свой проект)
TRI_BUDGET = {
    "mobile": 15_000,
    "pc_console_npc": 40_000,
    "pc_console_hero": 100_000,
}
TARGET = "pc_console_npc"
MERGE_DISTANCE = 0.0001

OK, WARN, FAIL = "OK  ", "WARN", "FAIL"


class Report:
    def __init__(self):
        self.lines = []
        self.counts = {OK: 0, WARN: 0, FAIL: 0}

    def add(self, level, obj_name, text):
        self.counts[level] += 1
        self.lines.append(f"[{level}] {obj_name}: {text}")

    def header(self, text):
        self.lines.append("")
        self.lines.append(f"=== {text} ===")

    def text(self):
        summary = (f"\nИТОГО: OK={self.counts[OK]}  WARN={self.counts[WARN]}  "
                   f"FAIL={self.counts[FAIL]}")
        verdict = ("Критичных проблем нет." if self.counts[FAIL] == 0 else
                   "Есть FAIL — модель НЕ готова к экспорту в игру.")
        return "\n".join(self.lines) + summary + "\n" + verdict


def check_mesh(obj, rep):
    name = obj.name
    rep.header(f"MESH {name}")

    # Трансформации
    if any(abs(s - 1.0) > 1e-4 for s in obj.scale):
        rep.add(FAIL, name, f"scale не применён {tuple(round(s, 3) for s in obj.scale)}"
                " -> Ctrl+A > Scale")
    else:
        rep.add(OK, name, "scale = 1")
    if any(abs(r) > 1e-4 for r in obj.rotation_euler):
        rep.add(WARN, name, "rotation не применён -> Ctrl+A > Rotation")

    # Модификаторы
    mods = [m for m in obj.modifiers if m.type != 'ARMATURE']
    if mods:
        rep.add(WARN, name, "неприменённые модификаторы: "
                + ", ".join(f"{m.name}({m.type})" for m in mods)
                + " — экспортёр применит их, проверь итоговый полигонаж")

    # Геометрия (с учётом модификаторов для подсчёта треугольников)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    eval_mesh = eval_obj.to_mesh()
    tris = sum(len(p.vertices) - 2 for p in eval_mesh.polygons)
    eval_obj.to_mesh_clear()
    budget = TRI_BUDGET[TARGET]
    level = OK if tris <= budget else (WARN if tris <= budget * 1.5 else FAIL)
    rep.add(level, name, f"треугольников: {tris:,} (бюджет {TARGET}: {budget:,})")

    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()

    ngons = sum(1 for f in bm.faces if len(f.verts) > 4)
    if ngons:
        rep.add(WARN, name, f"n-gons: {ngons} (плохо деформируются, триангулируются непредсказуемо)")
    else:
        rep.add(OK, name, "n-gons нет")

    poles = sum(1 for v in bm.verts if len(v.link_edges) >= 6)
    if poles:
        rep.add(WARN, name, f"полюсов с 6+ рёбрами: {poles} (избегать на суставах и лице)")

    non_manifold = sum(1 for e in bm.edges if not e.is_manifold and not e.is_boundary)
    boundary = sum(1 for e in bm.edges if e.is_boundary)
    if non_manifold:
        rep.add(FAIL, name, f"non-manifold рёбер: {non_manifold} -> Select > Select All by Trait > Non Manifold")
    if boundary:
        rep.add(WARN, name, f"открытых краёв: {boundary} (нормально для одежды/глаз, иначе дыры)")

    loose = sum(1 for v in bm.verts if not v.link_edges)
    if loose:
        rep.add(FAIL, name, f"свободных вершин: {loose} -> Mesh > Clean Up > Delete Loose")

    doubles = bmesh.ops.find_doubles(bm, verts=bm.verts, dist=MERGE_DISTANCE)["targetmap"]
    if doubles:
        rep.add(WARN, name, f"дубликатов вершин: {len(doubles)} -> Mesh > Clean Up > Merge by Distance")

    flipped = sum(1 for e in bm.edges if e.is_manifold and not e.is_contiguous)
    if flipped:
        rep.add(FAIL, name, f"несогласованных нормалей (рёбер): {flipped} -> Mesh > Normals > Recalculate Outside")
    else:
        rep.add(OK, name, "нормали согласованы")

    zero_faces = sum(1 for f in bm.faces if f.calc_area() < 1e-10)
    if zero_faces:
        rep.add(WARN, name, f"вырожденных граней: {zero_faces}")

    # UV
    uv_layer = bm.loops.layers.uv.active
    if uv_layer is None:
        rep.add(FAIL, name, "нет UV-развёртки")
    else:
        rep.add(OK, name, f"UV-слоёв: {len(me.uv_layers)}")
        outside = 0
        for f in bm.faces:
            for loop in f.loops:
                u, v = loop[uv_layer].uv
                if u < -1e-4 or u > 1.0001 or v < -1e-4 or v > 1.0001:
                    outside += 1
                    break
        if outside:
            rep.add(WARN, name, f"граней с UV вне 0-1: {outside} (ок для UDIM/тайлинга, иначе ошибка)")
        overlap = _uv_overlap_estimate(bm, uv_layer)
        if overlap > 0.02:
            rep.add(WARN, name, f"оценка перекрытия UV: ~{overlap:.0%} площади "
                    "(допустимо только для зеркальных/повторяющихся частей; мешает запеканию)")
    bm.free()

    # Материалы
    if not obj.material_slots:
        rep.add(FAIL, name, "нет материалов")
    else:
        empty = [i for i, s in enumerate(obj.material_slots) if s.material is None]
        if empty:
            rep.add(FAIL, name, f"пустые слоты материалов: {empty}")
        else:
            rep.add(OK, name, "материалы: " + ", ".join(s.material.name for s in obj.material_slots))

    # Габариты
    dims = obj.dimensions
    rep.add(OK, name, f"габариты X={dims.x:.2f} Y={dims.y:.2f} Z={dims.z:.2f} м")
    if dims.z > 50 or (0 < max(dims) < 0.05):
        rep.add(WARN, name, "подозрительный масштаб — проверь единицы")

    # Скиннинг
    arm_mod = next((m for m in obj.modifiers if m.type == 'ARMATURE'), None)
    if arm_mod:
        if arm_mod.object is None:
            rep.add(FAIL, name, "Armature-модификатор без скелета")
        else:
            bones = {b.name for b in arm_mod.object.data.bones if b.use_deform}
            unweighted = sum(1 for v in me.vertices
                             if not any(g.weight > 0 and obj.vertex_groups[g.group].name in bones
                                        for g in v.groups))
            if unweighted:
                rep.add(FAIL, name, f"вершин без весов: {unweighted} (останутся на месте при анимации)")
            else:
                rep.add(OK, name, "все вершины имеют веса")


def _uv_overlap_estimate(bm, uv_layer, res=256):
    """Грубая растровая оценка доли перекрывающейся UV-площади (по центрам ячеек)."""
    grid = bytearray(res * res)
    covered = overlapped = 0
    for f in bm.faces:
        uvs = [l[uv_layer].uv.copy() for l in f.loops]
        for i in range(1, len(uvs) - 1):
            a, b, c = uvs[0], uvs[i], uvs[i + 1]
            minx = max(int(min(a.x, b.x, c.x) * res), 0)
            maxx = min(int(max(a.x, b.x, c.x) * res) + 1, res)
            miny = max(int(min(a.y, b.y, c.y) * res), 0)
            maxy = min(int(max(a.y, b.y, c.y) * res) + 1, res)
            area = (b.x - a.x) * (c.y - a.y) - (c.x - a.x) * (b.y - a.y)
            if abs(area) < 1e-12:
                continue
            for y in range(miny, maxy):
                py = (y + 0.5) / res
                for x in range(minx, maxx):
                    px = (x + 0.5) / res
                    w0 = (b.x - px) * (c.y - py) - (c.x - px) * (b.y - py)
                    w1 = (c.x - px) * (a.y - py) - (a.x - px) * (c.y - py)
                    w2 = (a.x - px) * (b.y - py) - (b.x - px) * (a.y - py)
                    if (w0 >= 0 and w1 >= 0 and w2 >= 0) or (w0 <= 0 and w1 <= 0 and w2 <= 0):
                        idx = y * res + x
                        if grid[idx] == 0:
                            covered += 1
                        elif grid[idx] == 1:
                            overlapped += 1
                        grid[idx] = min(grid[idx] + 1, 2)
    return overlapped / covered if covered else 0.0


def check_armature(obj, rep):
    name = obj.name
    rep.header(f"ARMATURE {name}")
    arm = obj.data
    deform = [b for b in arm.bones if b.use_deform]
    rep.add(OK, name, f"костей: {len(arm.bones)}, deform: {len(deform)}")
    if len(deform) > 150:
        rep.add(WARN, name, "много deform-костей (>150) — тяжело для мобильных движков")
    bad = [b.name for b in arm.bones if any(ch in b.name for ch in ' ()[]{}#')]
    if bad:
        rep.add(WARN, name, f"имена костей с пробелами/спецсимволами: {bad[:5]}")
    if any(b.name.startswith(("ORG-", "MCH-")) and b.use_deform for b in arm.bones):
        rep.add(WARN, name, "ORG-/MCH- кости помечены как deform — для экспорта Rigify "
                "оставь deform только у DEF-костей")
    if any(abs(s - 1.0) > 1e-4 for s in obj.scale):
        rep.add(FAIL, name, "scale скелета не применён")
    children = [c for c in bpy.data.objects
                if c.type == 'MESH' and any(m.type == 'ARMATURE' and m.object == obj
                                            for m in c.modifiers)]
    if not children:
        rep.add(WARN, name, "к скелету не привязан ни один меш")
    else:
        # кости без весов проверяются по всему персонажу (одежда и тело — разные объекты)
        used = {g.name for c in children for g in c.vertex_groups}
        missing = sorted(b.name for b in deform if b.name not in used)
        if missing:
            rep.add(WARN, name, f"deform-кости без весов во всех мешах: {missing[:6]}")
        else:
            rep.add(OK, name, f"все deform-кости используются ({len(children)} мешей)")


def main():
    rep = Report()
    objs = bpy.context.selected_objects if ONLY_SELECTED else bpy.context.scene.objects
    objs = [o for o in objs if not o.name.startswith("REF_")]
    meshes = [o for o in objs if o.type == 'MESH']
    arms = [o for o in objs if o.type == 'ARMATURE']
    if not meshes:
        rep.add(WARN, "scene", "нет mesh-объектов для проверки")
    for o in meshes:
        check_mesh(o, rep)
    for o in arms:
        check_armature(o, rep)

    text = rep.text()
    print(text)
    block = bpy.data.texts.get("QA_Report") or bpy.data.texts.new("QA_Report")
    block.clear()
    block.write(text)
    return text


if __name__ == "__main__":
    main()
