#!/bin/sh
echo "=== Sandbells Luakit Kiosk Starting ==="

pkill -9 luakit 2>/dev/null
pkill -9 matchbox-window-manager 2>/dev/null

export DISPLAY=:0
export XAUTHORITY=/home/wyleu/.Xauthority

xset -dpms
xset s off
xset s noblank
xsetroot -cursor_name left_ptr

matchbox-window-manager -use_titlebar no -use_cursor no &

sleep 2
cd /home/wyleu/Code/Sandbells

luakit -u http://sandbells.local:8000
