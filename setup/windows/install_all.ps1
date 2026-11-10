<#
.SYNOPSIS
  Полная установка: Blender + uv + Claude Desktop + MCP for Blender + папки проекта
  + настройка Blender для игровых персонажей. Windows 10/11.

.USAGE
  Открой PowerShell (Win+X -> Terminal) в папке репозитория и выполни:

    powershell -ExecutionPolicy Bypass -File .\setup\windows\install_all.ps1

  Параметры:
    -ProjectRoot "D:\AI_3D_Projects"   корень проектов (если диска D: нет — возьмётся C:\AI_3D_Projects)
    -SkipClaude                         не ставить Claude Desktop (уже установлен)
    -SkipBlender                        не ставить Blender (уже установлен)

  Скрипт идемпотентный: повторный запуск ничего не ломает.
  Ничего не удаляет. Перед изменением claude_desktop_config.json делает .bak.
#>
param(
    [string]$ProjectRoot = "",
    [switch]$SkipClaude,
    [switch]$SkipBlender
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")

function Step($t)  { Write-Host "`n=== $t ===" -ForegroundColor Cyan }
function Ok($t)    { Write-Host "  [OK]   $t" -ForegroundColor Green }
function Warn($t)  { Write-Host "  [WARN] $t" -ForegroundColor Yellow }

function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User") + ";" +
                "$env:USERPROFILE\.local\bin"
}

function Winget-Install($id, $label) {
    $installed = winget list --id $id -e --accept-source-agreements 2>$null | Select-String $id
    if ($installed) { Ok "$label уже установлен"; return }
    Write-Host "  Устанавливаю $label ..."
    winget install --id $id -e --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { Warn "winget вернул код $LASTEXITCODE для $label — проверь вручную" }
    else { Ok "$label установлен" }
}

# ---------------------------------------------------------------- 0. winget
Step "0. Проверка winget"
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw "winget не найден. Установи 'App Installer' из Microsoft Store и запусти скрипт снова."
}
Ok "winget найден"

# ---------------------------------------------------------------- 1. Blender
Step "1. Blender (ЧАСТЬ 2)"
if ($SkipBlender) { Warn "пропущено (-SkipBlender)" }
else { Winget-Install "BlenderFoundation.Blender" "Blender" }

# ---------------------------------------------------------------- 2. Claude
Step "2. Claude Desktop (ЧАСТЬ 3)"
if ($SkipClaude) { Warn "пропущено (-SkipClaude)" }
else { Winget-Install "Anthropic.Claude" "Claude Desktop" }

# ---------------------------------------------------------------- 3. uv
Step "3. uv (ЧАСТЬ 4)"
Refresh-Path
if (Get-Command uvx -ErrorAction SilentlyContinue) { Ok "uv уже установлен: $(uv --version)" }
else {
    Winget-Install "astral-sh.uv" "uv"
    Refresh-Path
    if (-not (Get-Command uvx -ErrorAction SilentlyContinue)) {
        Warn "uvx не найден в PATH. Пробую официальный установщик uv..."
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        Refresh-Path
    }
}
$uvx = (Get-Command uvx -ErrorAction SilentlyContinue).Source
if (-not $uvx) { throw "uvx так и не появился. Закрой терминал, открой заново и запусти скрипт ещё раз." }
Ok "uvx: $uvx"

# ---------------------------------------------------------------- 4. Папки
Step "4. Структура папок проекта (ЧАСТЬ 2, шаг 3)"
if (-not $ProjectRoot) {
    $ProjectRoot = if (Test-Path "D:\") { "D:\AI_3D_Projects" } else { "C:\AI_3D_Projects" }
}
foreach ($sub in "Characters","Creatures","Textures","References","Exports","Backups","Assets") {
    New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot $sub) | Out-Null
}
Copy-Item -Force (Join-Path $RepoRoot "blender\*.py") (Join-Path $ProjectRoot "Assets")
New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot "Assets\Prompts") | Out-Null
Copy-Item -Force (Join-Path $RepoRoot "prompts\*.md") (Join-Path $ProjectRoot "Assets\Prompts")
Ok "создано: $ProjectRoot (скрипты Blender и промпты скопированы в Assets)"

# ---------------------------------------------------------------- 5. MCP for Blender
Step "5. MCP for Blender (ЧАСТЬ 5)"
Write-Host "  Запускаю официальный установщик: uvx mcp-for-blender setup"
Write-Host "  Он спросит, какие AI-приложения настроить — выбери Claude Desktop."
& $uvx mcp-for-blender setup
if ($LASTEXITCODE -ne 0) {
    Warn "setup завершился с кодом $LASTEXITCODE. Ставлю аддон и конфиг вручную."
    & $uvx mcp-for-blender install-addon
    & (Join-Path $PSScriptRoot "add_blender_to_claude_config.ps1") -UvxPath $uvx
} else {
    Ok "MCP for Blender настроен"
}

# ---------------------------------------------------------------- 6. Настройка Blender
Step "6. Настройка Blender для игровых персонажей (ЧАСТЬ 6)"
$blender = (Get-Command blender -ErrorAction SilentlyContinue).Source
if (-not $blender) {
    $blender = Get-ChildItem "C:\Program Files\Blender Foundation" -Recurse -Filter blender.exe -ErrorAction SilentlyContinue |
               Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
}
if ($blender) {
    & $blender --background --python (Join-Path $RepoRoot "blender\setup_blender_for_games.py")
    Ok "Rigify, единицы, Eevee и автосохранение настроены ($blender)"
} else {
    Warn "blender.exe не найден. Открой Blender и выполни blender\setup_blender_for_games.py во вкладке Scripting."
}

# ---------------------------------------------------------------- Итог
Step "Готово"
Write-Host @"
Дальше вручную (это нельзя сделать скриптом):
  1. Полностью закрой Claude Desktop (иконка в трее -> Quit) и открой снова.
  2. Открой Blender -> в 3D Viewport нажми N -> вкладка 'MCP for Blender'
     -> сервер должен быть запущен (иначе 'Start MCP Server').
  3. В Claude Desktop: Settings -> Developer — сервер 'blender' должен быть running.
  4. Создай Project в Claude, вставь prompts\system_prompt.md в Project instructions.
  5. Первая сцена:  .\setup\windows\new_character.ps1 -Name ForestGuardian -Category Creatures -Height 2.4
  6. Отправь Claude текст из prompts\first_project.md.
"@
