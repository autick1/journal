# Резной диван и деревянный стул — разделены на детали (для Roblox)

| Диван | Стул |
|---|---|
| ![](Sofa/renders/parts_view.png) | ![](Chair/renders/parts_view.png) |

Исходники — `meshy-model_5.glb` (диван, 355 тыс. треугольников) и `meshy-model_6.glb` (стул, 149 тыс.),
без текстур. Форма сохранена, полигонаж снижен, каждая деталь < 20 000 треугольников (лимит MeshPart).

**Диван** (2.05 × 0.70 × 1.10 м, пара к `props/ArmchairCarved`) — 15 деталей:
`Leg_FL/FR/BL/BR`, `Base` (царга), `Seat_L/R` (две подушки), `Arm_L/R` (мягкие подлокотники),
`ArmFront_L/R` (резные свитки), `BackPanel` (мягкая спинка), `BackFrame` (резная рамка),
`Crest` (корона), `BackRear` (задняя стенка).

**Стул** (0.46 × 0.47 × 0.95 м) — 13 деталей:
`Leg_FL/FR/BL/BR`, `Stretchers` (перекладины между ножками), `Apron` (царга под сиденьем), `Seat`,
`BackPost_L/R` (стойки спинки), `BackRail` (нижняя планка спинки), `Slat_L/R` (вертикальные планки),
`TopRail` (верхняя перекладина).

## Как добавить
1. Studio → **Import 3D** → `Sofa_Parts_Roblox.fbx` / `Chair_Parts_Roblox.fbx` (File Dimensions = **Meters**).
2. В модель добавь **Script** и вставь `FurnitureSetup.server.lua`.
3. **Play** — мебель окрашена (дерево / бордовая ткань), закреплена, на неё можно сесть
   (на диване — два места, по одному на подушку).

Цвета — в начале скрипта. Пересборка: `python split_parts.py -- model.glb out sofa|chair`.
