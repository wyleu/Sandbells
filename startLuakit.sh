#!/bin/sh
echo "=== Sandbells Luakit Kiosk Starting ==="

# Kill any existing instances
pkill -9 luakit
pkill -9 matchbox-window-manager

export DISPLAY=:0
export XAUTHORITY=/home/$USER/.Xauthority

xset -dpms
xset s off
xset s noblank
xsetroot -cursor_name left_ptr

unclutter -idle 0.5 -root &

matchbox-window-manager -use_titlebar no -use_cursor no &

sleep 2

cd /home/$USER/Code/Sandbells
luakit -u http://sandbells.local:8000
