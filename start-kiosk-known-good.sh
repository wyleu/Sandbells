#!/bin/bash
# Known Good Minimal Luakit Kiosk - Reference Point
# Works with current clean Luakit install

START_TIME=$(date +%s)
PROJECT_DIR="$HOME/Code/Sandbells"

source "$PROJECT_DIR/show_header.sh"
show_header

echo "Starting Known-Good Minimal Luakit Kiosk..."

export DISPLAY=:0

xset s off -dpms s noblank 2>/dev/null || true

matchbox-window-manager -use_titlebar no -use_cursor yes &

luakit "http://sandbells.local" 2>&1 | tee -a luakit.log &
