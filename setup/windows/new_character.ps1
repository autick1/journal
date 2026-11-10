<#
.SYNOPSIS
  Создаёт папку нового персонажа (ЧАСТЬ 6, шаг 4) и стартовую .blend-сцену
  с коллекциями по этапам, ростовым ориентиром, светом и камерами.

.USAGE
  .\setup\windows\new_character.ps1 -Name ForestGuardian -Category Creatures -Height 2.4
  .\setup\windows\new_character.ps1 -Name Knight -Category Characters -Height 1.85 -ProjectRoot "E:\AI_3D_Projects"
#>
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[A-Za-z0-9_]+$')][string]$Name,
    [ValidateSet("Characters", "Creatures")][string]$Category = "Characters",
    [double]$Height = 1.8,
    [string]$ProjectRoot = ""
)
$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
if (-not $ProjectRoot) {
    $ProjectRoot = if (Test-Path "D:\AI_3D_Projects") { "D:\AI_3D_Projects" } else { "C:\AI_3D_Projects" }
}

$blender = (Get-Command blender -ErrorAction SilentlyContinue).Source
if (-not $blender) {
    $blender = Get-ChildItem "C:\Program Files\Blender Foundation" -Recurse -Filter blender.exe -ErrorAction SilentlyContinue |
               Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $blender) { throw "blender.exe не найден. Укажи путь в PATH или установи Blender." }

$root = $ProjectRoot -replace '\\', '/'
$heightStr = $Height.ToString([System.Globalization.CultureInfo]::InvariantCulture)
& $blender --background --python (Join-Path $RepoRoot "blender\new_character_scene.py") -- $Name $Category $root $heightStr

$blend = Join-Path $ProjectRoot "$Category\$Name\Blender\${Name}_Blockout.blend"
if (Test-Path $blend) {
    Write-Host "`nГотово: $blend" -ForegroundColor Green
    Write-Host "Открой этот файл в Blender, запусти MCP-сервер и отправь Claude prompts\first_project.md"
} else {
    Write-Host "Файл не создан — смотри вывод Blender выше." -ForegroundColor Red
}
