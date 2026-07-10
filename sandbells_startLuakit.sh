#!/bin/sh


echo "=== Sandbells Luakit Kiosk Starting ==="

echo "############################################################################"
echo "#                                                                          #"
echo "#                          Running  luakit                                 #"
echo "#                                                                          #"
echo "############################################################################"

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
git status
pwd

luakit -u http://$HOSTNAME.local:8000
