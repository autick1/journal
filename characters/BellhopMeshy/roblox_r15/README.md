# Коридорный для Roblox: персонаж R15 с суставами

Модель разбита на 15 частей по стандарту Roblox R15 и привязана к скелету.
Roblox Studio импортирует её как персонажа с Humanoid. Работают Animation Editor,
стандартные R15-анимации и ходьба NPC.

```
Root
└ HumanoidRootPart
  └ LowerTorso
    ├ UpperTorso
    │ ├ Head                (+ Eyes — светящиеся глаза)
    │ ├ LeftUpperArm  → LeftLowerArm  → LeftHand
    │ └ RightUpperArm → RightLowerArm → RightHand
    ├ LeftUpperLeg  → LeftLowerLeg  → LeftFoot
    └ RightUpperLeg → RightLowerLeg → RightFoot
```

- 24 тыс. треугольников на всю модель, каждая часть меньше 4.8 тыс. (лимит Roblox — 20 тыс. на часть).
- Плавные веса на суставах: колени, локти и плечи сгибаются без щелей, это проверено позой.
- До 4 костей на вершину (лимит Roblox).
- Рост около 7 стадов, лицо смотрит в −Z, как у персонажей Roblox.

## Что в папке
| Файл | Зачем |
|---|---|
| `Bellhop_R15.fbx` | персонаж: 15 частей, глаза, HumanoidRootPart и скелет |
| `textures/` | Color, Metalness, Roughness, Normal (1024²) |
| `SetupInStudio.lua` | одной командой ставит текстуры на все части, глаза делает Neon и добавляет Bloom |
| `BellhopNPC.server.lua` | NPC: стоит, замечает игрока и идёт к нему с анимациями |

## Порядок действий
1. **Импорт.** Studio → вкладка Avatar (или Home) → **Import 3D** → `Bellhop_R15.fbx`.
   В настройках импорта:
   - **Rig General → Rig Type: R15** (обычно определяется сам);
   - если персонаж крошечный или огромный, поменяй **File Dimensions** или Scale (цель — около 7 стадов в высоту);
   - нажми Import. В Workspace появится модель с Humanoid.
2. **Текстуры.** Загрузи 4 PNG из `textures/` через **Asset Manager** (Bulk Import). У каждой картинки
   нажми правой кнопкой **Copy Asset ID**.
3. Открой `SetupInStudio.lua`, впиши 4 ID, вставь весь текст в **Command Bar** (View → Command Bar) и нажми Enter.
   Текстуры встанут на все 15 частей, глаза станут Neon, в Lighting появится Bloom.
4. **NPC.** Создай Script внутри модели и вставь туда `BellhopNPC.server.lua`. Запусти Play,
   и коридорный пойдёт к игроку.
5. **Свои анимации.** Avatar → **Animation Editor** → выбери модель. Анимируй, сохрани (Publish to Roblox)
   и вставь полученный ID в `IDLE_ANIM` или `WALK_ANIM` либо проигрывай через `animator:LoadAnimation`.

## Если что-то не так
| Проблема | Решение |
|---|---|
| Импорт не видит R15 | В Import 3D выбери Rig Type: R15 вручную |
| Персонаж проваливается или висит над полом | У Humanoid подправь **HipHeight** (примерно 3–3.5) |
| Стандартная ходьба выглядит странно | Это человеческая анимация на сутулом монстре с длинными руками. Сделай свою в Animation Editor |
| Чёрный персонаж | Текстуры на модерации или ID вписаны не все |
| Глаза не светятся | Проверь, что у части Eyes материал Neon и в Lighting есть Bloom |
