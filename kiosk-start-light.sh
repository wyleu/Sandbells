#!/bin/bash
START_TIME=$(date +%s)
PROJECT_DIR="$HOME/Code/Sandbells"

source "$PROJECT_DIR/show_header.sh"
show_header

echo "Starting Clean Luakit Kiosk..."

export DISPLAY=:0
export XAUTHORITY=/home/sandbells/.Xauthority

cd "$PROJECT_DIR"

pkill -9 luakit WebKitWebProcess 2>/dev/null || true
rm -rf ~/.cache/luakit/* 2>/dev/null || true
sleep 2

xset s off -d :0 2>/dev/null || true
xset -dpms -d :0 2>/dev/null || true
xset s noblank -d :0 2>/dev/null || true

echo "Launching Luakit..."

luakit --kiosk --single-process --no-restore \
  --config ~/.config/luakit/settings.lua \
  "http://sandbells.local" 2>&1 | tee -a luakit.log &

echo "Kiosk launched."
