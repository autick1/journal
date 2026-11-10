#!/usr/bin/env bash
# Установка для macOS: Blender + Claude Desktop + uv + MCP for Blender + папки проекта.
# Запуск:  bash setup/macos/install_all.sh  [корень_проектов]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PROJECT_ROOT="${1:-$HOME/AI_3D_Projects}"

step() { printf '\n=== %s ===\n' "$1"; }

step "Homebrew"
if ! command -v brew >/dev/null; then
  echo "Homebrew не найден. Установи с https://brew.sh и запусти снова."; exit 1
fi

step "Blender / Claude / uv"
brew list --cask blender >/dev/null 2>&1 || brew install --cask blender
brew list --cask claude  >/dev/null 2>&1 || brew install --cask claude
command -v uvx >/dev/null || brew install uv

step "Папки проекта: $PROJECT_ROOT"
mkdir -p "$PROJECT_ROOT"/{Characters,Creatures,Textures,References,Exports,Backups,Assets/Prompts}
cp "$REPO_ROOT"/blender/*.py "$PROJECT_ROOT/Assets/"
cp "$REPO_ROOT"/prompts/*.md "$PROJECT_ROOT/Assets/Prompts/"

step "MCP for Blender"
uvx mcp-for-blender setup || {
  echo "setup не прошёл — ставлю аддон вручную"
  uvx mcp-for-blender install-addon
  echo "Добавь в ~/Library/Application Support/Claude/claude_desktop_config.json содержимое config/claude_desktop_config.macos.json"
}

step "Настройка Blender"
BLENDER="/Applications/Blender.app/Contents/MacOS/Blender"
if [ -x "$BLENDER" ]; then
  "$BLENDER" --background --python "$REPO_ROOT/blender/setup_blender_for_games.py"
else
  echo "Blender не найден в /Applications — выполни blender/setup_blender_for_games.py во вкладке Scripting."
fi

step "Готово"
echo "Закрой Claude (Cmd+Q), открой снова; открой Blender -> N -> вкладка 'MCP for Blender'."
