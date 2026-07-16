#!/bin/bash
# Sandbells Lightweight Kiosk Starter

START_TIME=$(date +%s)
PROJECT_DIR="$HOME/Code/Sandbells"

source "$PROJECT_DIR/show_header.sh"
show_header

echo "Starting Ultra-Clean Single-Tab Luakit Kiosk..."

export DISPLAY=:0
export XAUTHORITY=/home/sandbells/.Xauthority

cd "$PROJECT_DIR"

# Aggressive cleanup
pkill -9 luakit WebKitWebProcess 2>/dev/null || true
rm -rf ~/.cache/luakit/* ~/.local/share/luakit/* 2>/dev/null || true
sleep 2

# Disable screen blanking
xset s off -d :0 2>/dev/null || true
xset -dpms -d :0 2>/dev/null || true
xset s noblank -d :0 2>/dev/null || true

echo "Launching Luakit (single tab, clean session)..."

luakit \
  --kiosk \
  --single-process \
  --config ~/.config/luakit/settings.lua \
  --no-restore \
  "http://sandbells.local" 2>&1 | tee -a luakit.log &

echo "Kiosk started (session cleared)."
