#!/bin/bash
# Install the daily 10:05 job and the Raycast command for this checkout.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON=""
for candidate in /usr/local/bin/python3 /opt/homebrew/bin/python3 "$(command -v python3)"; do
  if [ -n "$candidate" ] && [ -x "$candidate" ] && "$candidate" -c "import AppKit, Quartz" >/dev/null 2>&1; then
    PYTHON="$candidate"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "找不到带 PyObjC 的 Python。请安装后重试：pip3 install pyobjc-framework-Cocoa pyobjc-framework-Quartz" >&2
  exit 1
fi

if [ ! -f "$ROOT/data/maimemo.v3.db" ] && [ ! -f "$ROOT/unpacked/assets/maimemo.v3.db" ]; then
  echo "还没有词库。请把 maimemo.v3.db 放到 $ROOT/data/ 后再安装。见 README。" >&2
  exit 1
fi

render() {
  sed -e "s#@PYTHON@#$PYTHON#g" -e "s#@ROOT@#$ROOT#g" "$1"
}

UID_NUM="$(id -u)"
AGENTS="$HOME/Library/LaunchAgents"
mkdir -p "$AGENTS"
# Replace the earlier per-user label if it is still loaded.
launchctl bootout "gui/$UID_NUM/com.stepbystep.momo-today-pin" 2>/dev/null || true
launchctl bootout "gui/$UID_NUM/com.momo.today-pin" 2>/dev/null || true
render "$ROOT/launchd/com.momo.today-pin.plist" > "$AGENTS/com.momo.today-pin.plist"
launchctl bootstrap "gui/$UID_NUM" "$AGENTS/com.momo.today-pin.plist"
echo "已安装每天 10:05 的任务。"

RAYCAST_DIR="${RAYCAST_SCRIPTS:-$HOME/Documents/commands}"
if [ -d "$RAYCAST_DIR" ]; then
  render "$ROOT/raycast/momo-today-pin.sh" > "$RAYCAST_DIR/momo-today-pin.sh"
  chmod +x "$RAYCAST_DIR/momo-today-pin.sh"
  echo "已写入 Raycast 命令：$RAYCAST_DIR/momo-today-pin.sh"
else
  echo "没有找到 Raycast 脚本目录 $RAYCAST_DIR。"
  echo "在 Raycast → Settings → Extensions → Script Commands 里添加目录后，重新执行："
  echo "  RAYCAST_SCRIPTS=/你的目录 $ROOT/install.sh"
fi
