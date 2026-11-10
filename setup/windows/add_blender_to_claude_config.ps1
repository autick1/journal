<#
.SYNOPSIS
  Резервный способ (ЧАСТЬ 5, шаг 6): добавляет сервер "blender" в claude_desktop_config.json,
  НЕ трогая остальные MCP-серверы. Делает резервную копию .bak.

.USAGE
  powershell -ExecutionPolicy Bypass -File .\setup\windows\add_blender_to_claude_config.ps1
  powershell -ExecutionPolicy Bypass -File .\setup\windows\add_blender_to_claude_config.ps1 -Mode cmd
  powershell -ExecutionPolicy Bypass -File .\setup\windows\add_blender_to_claude_config.ps1 -SafeMode

  -Mode path   (по умолчанию) — полный путь к uvx.exe, лечит ошибку "spawn uvx ENOENT"
  -Mode plain  — просто "uvx" (как в официальном README)
  -Mode cmd    — запуск через cmd /c uvx ...
  -SafeMode    — BLENDER_MCP_SAFE_MODE=1: скрипты проверяются перед выполнением
                 (блокирует доступ к файлам вне Blender, сети, запуск программ)
#>
param(
    [ValidateSet("path", "plain", "cmd")][string]$Mode = "path",
    [string]$UvxPath = "",
    [switch]$SafeMode
)
$ErrorActionPreference = "Stop"

# Claude Desktop (обычная установка и установка из Microsoft Store)
$candidates = @(
    "$env:APPDATA\Claude\claude_desktop_config.json"
)
$store = Get-ChildItem "$env:LOCALAPPDATA\Packages" -Directory -Filter "*Claude*" -ErrorAction SilentlyContinue |
         ForEach-Object { Join-Path $_.FullName "LocalCache\Roaming\Claude\claude_desktop_config.json" }
$candidates += $store
$config = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $config) { $config = $candidates[0] }

New-Item -ItemType Directory -Force -Path (Split-Path $config) | Out-Null
if (Test-Path $config) {
    Copy-Item $config "$config.bak" -Force
    $raw = Get-Content $config -Raw
    $json = if ($raw.Trim()) { $raw | ConvertFrom-Json } else { [pscustomobject]@{} }
} else {
    $json = [pscustomobject]@{}
}

if (-not $UvxPath) { $UvxPath = (Get-Command uvx -ErrorAction SilentlyContinue).Source }
if ($Mode -eq "path" -and -not $UvxPath) {
    Write-Host "uvx не найден — использую режим 'cmd'" -ForegroundColor Yellow
    $Mode = "cmd"
}

switch ($Mode) {
    "path"  { $server = [ordered]@{ command = $UvxPath; args = @("mcp-for-blender") } }
    "plain" { $server = [ordered]@{ command = "uvx";    args = @("mcp-for-blender") } }
    "cmd"   { $server = [ordered]@{ command = "cmd";    args = @("/c", "uvx", "mcp-for-blender") } }
}
if ($SafeMode) { $server.env = [ordered]@{ BLENDER_MCP_SAFE_MODE = "1" } }

if (-not ($json.PSObject.Properties.Name -contains "mcpServers")) {
    $json | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{})
}
if ($json.mcpServers.PSObject.Properties.Name -contains "blender") {
    $json.mcpServers.blender = [pscustomobject]$server
} else {
    $json.mcpServers | Add-Member -NotePropertyName blender -NotePropertyValue ([pscustomobject]$server)
}

# UTF-8 без BOM — Claude Desktop не любит BOM
$text = $json | ConvertTo-Json -Depth 20
[System.IO.File]::WriteAllText($config, $text, (New-Object System.Text.UTF8Encoding($false)))

Write-Host "Обновлён: $config" -ForegroundColor Green
if (Test-Path "$config.bak") { Write-Host "Резервная копия: $config.bak" }
Write-Host $text
Write-Host "`nПолностью закрой Claude Desktop (трей -> Quit) и открой снова." -ForegroundColor Cyan
