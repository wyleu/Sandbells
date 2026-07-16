#!/bin/bash
START_TIME=$(date +%s)
PROJECT_DIR="$HOME/Code/Sandbells"

source "$PROJECT_DIR/show_header.sh"
show_header

echo "Starting Optimized Lightweight Luakit Kiosk..."

export DISPLAY=:0
export XAUTHORITY=/home/sandbells/.Xauthority

cd "$PROJECT_DIR"

# Clean slate
pkill -9 luakit 2>/dev/null || true
sleep 2

# No blanking
xset s off -d :0 2>/dev/null || true
xset -dpms -d :0 2>/dev/null || true
xset s noblank -d :0 2>/dev/null || true

# Simple WM
matchbox-window-manager -use_titlebar no -use_cursor yes -d :0 &

sleep 2.5

echo "Launching Luakit with optimized settings..."

luakit \
  --kiosk \
  --single-process \
  --config ~/.config/luakit/settings.lua \
  "http://sandbells.local" 2>&1 | tee -a luakit.log &

echo "Kiosk started in optimized mode."
