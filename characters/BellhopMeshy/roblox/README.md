# Коридорный в Roblox: как импортировать

## Что скачать
1. **Roblox Studio** — бесплатно, с create.roblox.com (кнопка «Start Creating»). Войди своим аккаунтом Roblox.
2. **Этот пакет** — `Bellhop_Roblox.zip`. Распакуй его, внутри:
   - `Bellhop_Roblox.fbx` — модель: тело (19 тыс. треугольников, укладывается в лимит Roblox 20 тыс. на MeshPart) и отдельно глаза;
   - `textures/` — 4 карты 1024×1024: Color, Metalness, Roughness, Normal.

Больше ничего ставить не нужно. Blender нужен только для правок модели.

## Импорт модели
1. В Roblox Studio открой или создай место: File → New → Baseplate.
2. Вкладка **Home** (или Avatar) → **Import 3D** → выбери `Bellhop_Roblox.fbx`.
3. В окне импорта:
   - если персонаж слишком маленький или слишком большой, поменяй **Scale** (в Roblox 1 стад ≈ 0.28 м, модель ростом 1.9 м — это около 7 стадов);
   - проверь, что модель стоит прямо. Если лежит, поверни её в настройках импорта или после него.
4. Нажми **Import**. В Workspace появится модель с двумя MeshPart: `Bellhop` и `Bellhop_Eyes`.

## Текстуры (SurfaceAppearance)
1. В Explorer выбери MeshPart **Bellhop** → «+» → **SurfaceAppearance**.
2. В Properties у SurfaceAppearance загрузи карты (нажми на поле → Add Image / Import):
   - **ColorMap** ← `Bellhop_Color.png`
   - **MetalnessMap** ← `Bellhop_Metalness.png`
   - **RoughnessMap** ← `Bellhop_Roughness.png`
   - **NormalMap** ← `Bellhop_Normal.png`

   Картинки проходят модерацию Roblox, обычно это несколько минут.

## Светящиеся глаза
Отдельной карты свечения у SurfaceAppearance нет, поэтому глаза — отдельная деталь:
1. Выбери MeshPart **Bellhop_Eyes**.
2. Material = **Neon**, Color = белый или чуть тёплый (255, 245, 225).
3. Для ореола: в Lighting добавь **Bloom** (Intensity около 1, Size около 24, Threshold около 0.9).
   Можно ещё положить в глаза **PointLight** (Brightness 2, Range 6) — тогда лицо будет подсвечиваться.

## Как сделать NPC или игрового монстра
Импортированная модель статична, у неё нет скелета. Варианты:
- **Просто стоит или движется скриптом.** Сгруппируй детали в Model, задай PrimaryPart и двигай через скрипт
  (TweenService или PivotTo). Детали скрепи через WeldConstraint и сними с них Anchored.
- **С анимациями.** Нужен скелет. Его можно сделать в Blender (Rigify) или через Mixamo, а затем
  импортировать как риггованный FBX. Тогда в Roblox работают Animation Editor и Humanoid.
  Могу подготовить такую версию.

## Если что-то не так
| Проблема | Решение |
|---|---|
| «Mesh has too many triangles» | Используй этот FBX, а не полную версию на 563 тыс. |
| Модель чёрная | Не добавлен SurfaceAppearance или ColorMap ещё на модерации |
| Модель «пластиковая», латунь не блестит | Не загружены MetalnessMap и RoughnessMap |
| Глаза не светятся | У Bellhop_Eyes материал Neon, в Lighting есть Bloom |
| Тонкие тёмные трещинки на швах | Особенность упрощённой сетки, издалека в игре не видны |
