#!/bin/bash
echo "=== startLuakit.sh (minimal) ==="

cd ~/Code/Sandbells
[ -f Bellvirtenv/bin/activate ] && source Bellvirtenv/bin/activate

pkill -9 luakit matchbox-window-manager 2>/dev/null || true

export DISPLAY=:0
matchbox-window-manager -use_titlebar no -use_cursor no &

sleep 2

luakit --kiosk -u http://localhost:8000/ 2>&1 | tee luakit.log &
