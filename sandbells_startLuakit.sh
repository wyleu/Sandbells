#!/bin/sh
echo "=== Sandbells Luakit Kiosk Starting ==="
echo "User: $USER"
echo "Hostname: $(hostname)"
echo "Date: $(date)"
echo "Git status:"
cd /home/$USER/Code/Sandbells
git status --porcelain | head -5 || echo "No git or clean"
echo "CPU Temp: $(vcgencmd measure_temp 2>/dev/null || echo 'N/A')"
# Dynamic user for X
if [ "$(id -u)" -eq 0 ]; then
  USER="wyleu"
fi
export DISPLAY=:0
export XAUTHORITY=/home/$USER/.Xauthority
# Memory flags
export WEBKIT_DISABLE_COMPOSITING_MODE=1
export WEBKIT_FORCE_DMABUF_RENDERER=0
xset -dpms
xset s off
xset s noblank
xsetroot -cursor_name left_ptr
unclutter -idle 0.5 -root &
matchbox-window-manager -use_titlebar no -use_cursor no &
sleep 2
cd /home/$USER/Code/Sandbells
luakit --single-process -u http://sandbells.local:8000
