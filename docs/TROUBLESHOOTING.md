# Если что-то не работает (ЧАСТЬ 11, расширенная)

| Симптом | Причина | Решение |
|---|---|---|
| Claude не видит инструменты Blender | Claude Desktop не перезапущен | Трей → Quit, открыть заново (закрыть окно недостаточно) |
| `spawn uvx ENOENT` в логах Claude | GUI-приложения не видят PATH терминала | `.\setup\windows\add_blender_to_claude_config.ps1` (полный путь к uvx.exe) или `-Mode cmd` |
| `uv` / `uvx` не распознаётся | Терминал открыт до установки | Закрыть и открыть терминал. Путь: `%USERPROFILE%\.local\bin` |
| Ошибка установки зависимостей / не та версия Python | conda, pyenv или слишком новый Python | Конфиг `config/claude_desktop_config.windows-fullpath.json` (Python 3.11, `only-managed`) и `uv cache clean mcp-for-blender` |
| Сервер `blender` running, но команды висят / Connection refused | В Blender не запущен сокет-сервер аддона | Blender → N → вкладка **MCP for Blender** → **Start MCP Server**, порт 9876 |
| Нет вкладки MCP for Blender | Аддон не включён | Edit → Preferences → Add-ons → **Interface: MCP for Blender** ✓, или `uvx mcp-for-blender install-addon` |
| Работало, потом сломалось | Запущены два MCP-клиента на один Blender | Оставь один клиент (Claude Desktop **или** Cursor/Claude Code), либо разные порты (`--port 9877`) |
| Порт занят | Второй экземпляр Blender | Закрой лишний Blender или смени порт в панели аддона и в конфиге |
| Claude выдаёт ошибки Python | API Blender меняется между версиями | Напиши: «прочитай ошибку, проверь версию Blender через bpy.app.version и исправь код» |
| Модель не сохраняется | Нет папки / нет прав / OneDrive блокирует | Сохраняй в `D:\AI_3D_Projects`, не в «Документы» под OneDrive |
| Текстуры розовые | Сломанные пути к файлам | File → External Data → Find Missing Files; храни пути относительными |
| Blender зависает | Слишком много полигонов | См. `docs/HARDWARE.md`; попроси Claude назвать полигонаж до операции |
| Скрипт заблокирован в Safe Mode | Скрипт пишет файлы/сеть вне разрешённого | Ожидаемо: Claude получит причину и перепишет код. Для экспорта/сохранения Safe Mode не мешает |

## Логи
- Claude Desktop (Windows): `%APPDATA%\Claude\logs\mcp-server-blender.log`
- Claude Desktop (macOS): `~/Library/Logs/Claude/mcp-server-blender.log`
- Blender: Window → Toggle System Console (Windows)

Не отправляй посторонним `claude_desktop_config.json` и логи целиком — там могут быть ключи API и пути с именем пользователя.

## Безопасность
- Сокет-сервер аддона **без пароля и шифрования**: любой, кто достучится до порта 9876, может выполнить Python в Blender. Не пробрасывай порт наружу, не открывай его в брандмауэре.
- Claude может выполнять любой Python в Blender. Если открываешь чужие .blend или работаешь с важными файлами — включи Safe Mode (`config/claude_desktop_config.safe-mode.json` или `add_blender_to_claude_config.ps1 -SafeMode`).
- Делай бэкапы: скрипт настройки включает автосохранение и 3 версии `.blend1/.blend2/.blend3`.
