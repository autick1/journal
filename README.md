# Claude Desktop + Blender: набор для создания игровых персонажей

Готовый набор по гайду «Claude Desktop + Blender для создания игровых персонажей и существ»:
скрипты установки, конфиги, скрипты для Blender и промпты. Всё, что можно автоматизировать, автоматизировано.
Шаги, которые требуют твоих рук (вход в аккаунт, перезапуск приложений), перечислены ниже.

## Что внутри

```
setup/windows/install_all.ps1              ЧАСТИ 2–6 одной командой: Blender, Claude, uv, MCP, папки, настройка Blender
setup/windows/add_blender_to_claude_config.ps1   резервное подключение MCP в claude_desktop_config.json (с .bak)
setup/windows/new_character.ps1            папка нового персонажа + стартовая .blend-сцена
setup/macos/install_all.sh                 то же для macOS (Homebrew)

config/claude_desktop_config*.json         варианты конфига: стандартный, полный путь, cmd, safe mode, macOS

blender/setup_blender_for_games.py         Rigify, метры, Eevee, автосохранение и бэкапы
blender/new_character_scene.py             коллекции 00_Reference…07_Export, ростовой ориентир, свет, камеры
blender/game_asset_checker.py              проверка перед экспортом: трансформации, полигонаж, n-gons,
                                           non-manifold, нормали, UV, материалы, веса, кости
blender/export_for_engine.py               FBX/GLB с пресетами unity / unreal / godot / generic

prompts/system_prompt.md                   ЧАСТЬ 9: инструкции для Claude Project
prompts/first_project.md                   ЧАСТЬ 10: первый тестовый проект
prompts/stage_prompts.md                   готовые промпты для каждого из 9 этапов

docs/HARDWARE.md                           настройки под RTX / GTX / AMD и 16 / 32 / 64 ГБ RAM
docs/TROUBLESHOOTING.md                    ЧАСТЬ 11: ошибки, логи, безопасность
```

## Быстрый старт (Windows 10/11)

**1.** Скачай репозиторий (Code → Download ZIP) и распакуй, например, в `D:\claude-blender`.

**2.** Открой PowerShell (`Win + X` → Terminal) в этой папке и выполни:

```bash
powershell -ExecutionPolicy Bypass -File .\setup\windows\install_all.ps1
```

Скрипт поставит Blender, Claude Desktop и uv через `winget`, создаст `D:\AI_3D_Projects\…`,
запустит официальный `uvx mcp-for-blender setup` (выбери в нём **Claude Desktop**), включит Rigify и настроит Blender.

**3.** Вручную:
1. Войди в аккаунт в Claude Desktop.
2. Полностью закрой Claude Desktop (иконка в трее → Quit) и открой снова.
3. Открой Blender → в 3D Viewport нажми `N` → вкладка **MCP for Blender**. Аддон сам запускает сервер при старте Blender; если нет — **Start MCP Server**.
4. Claude Desktop → Settings → Developer: сервер `blender` в статусе running.
5. Claude Desktop → Projects → New project → вставь `prompts/system_prompt.md` в инструкции проекта.

**4.** Создай сцену первого персонажа:

```bash
.\setup\windows\new_character.ps1 -Name ForestGuardian -Category Creatures -Height 2.4
```

**5.** Открой созданный `.blend`, в чате проекта отправь текст из `prompts/first_project.md`.
Дальше работай по `prompts/stage_prompts.md` — по одному этапу за раз.

### macOS

```bash
bash setup/macos/install_all.sh
```

## Если автоустановка MCP не сработала

```bash
uvx mcp-for-blender install-addon
```

```bash
powershell -ExecutionPolicy Bypass -File .\setup\windows\add_blender_to_claude_config.ps1
```

Второй скрипт добавляет только сервер `blender`, не трогая остальные серверы, и сохраняет `.bak`.
Конфиги для ручной вставки лежат в `config/`. Остальное — в `docs/TROUBLESHOOTING.md`.

## Уточнения к исходному гайду

Проверено по актуальному README проекта MCP for Blender (PyPI `mcp-for-blender` 2.2.7):

- Пакет раньше назывался `blender-mcp`. Старые конфиги с `uvx blender-mcp` продолжают работать. Для новой установки используется `mcp-for-blender`, как и в гайде.
- Аддон в Blender называется **Interface: MCP for Blender**, порт по умолчанию **9876**, сервер стартует вместе с Blender.
- Генерация моделей через Hunyuan3D, Meshy, Tripo и Hyper3D Rodin, а также ассеты Poly Haven и Sketchfab доступны прямо из MCP. Включаются в панели аддона, для генераторов нужен свой API-ключ или Premium.
- Частая ошибка на Windows — `spawn uvx ENOENT`. Её лечит конфиг с полным путём к `uvx.exe`, именно так по умолчанию работает `add_blender_to_claude_config.ps1`.
- Есть **Safe Mode** (`BLENDER_MCP_SAFE_MODE=1`): Claude не сможет выполнить скрипт, который работает с файлами вне Blender, сетью или запускает программы.
- Rigify входит в состав Blender, его нужно только включить. Скрипт делает это сам.
- Системный промпт удобнее хранить в **Claude Project**, а не вставлять в каждый чат.
- Номер версии Blender в гайде (5.2.4 LTS) не проверялся. `winget` ставит последнюю стабильную версию. Если аддон с ней несовместим, поставь LTS-версию с blender.org.

## Чего этот набор не делает

Claude через MCP хорошо справляется с блокаутом, процедурной детализацией, автоматической ретопологией,
UV, запеканием, материалами, Rigify и экспортом. Финальный скульпт лица, ручную ретопологию лица и
художественную покраску текстур лучше делать вручную. Claude по системному промпту сам скажет, где это нужно,
и даст пошаговую инструкцию.

Модель не считается готовой для игры, пока `game_asset_checker.py` выдаёт FAIL.
