#!/bin/bash
# startLuakit.sh - Fixed flags + matchbox kiosk

echo "=== Running startLuakit.sh (matchbox kiosk mode) ==="

cd /home/sandbells/Code/Sandbells

# Auto venv
if [ -f "Bellvirtenv/bin/activate" ] && [ -z "$VIRTUAL_ENV" ]; then
  source Bellvirtenv/bin/activate
fi

pkill -9 luakit 2>/dev/null || true
pkill -9 matchbox-window-manager 2>/dev/null || true

export DISPLAY=:0
export XAUTHORITY=/home/sandbells/.Xauthority

xset -dpms 2>/dev/null || true
xset s off 2>/dev/null || true
xsetroot -cursor_name left_ptr 2>/dev/null || true

matchbox-window-manager -use_titlebar no -use_cursor no &

sleep 3

# Correct Luakit invocation (flags before URL)
luakit --kiosk --disable-javascript -u http://localhost:8000/ 2>&1 | tee -a luakit.log &

echo "Launched. Check: ps aux | grep luakit && cat luakit.log"
