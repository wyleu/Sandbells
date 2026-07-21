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
# xsetroot -cursor_name left_ptr

# Hide cursor when it's not moving
# unclutter -idle 0.5 -root &

#  USE lightdm
# matchbox-window-manager -use_titlebar no &
sudo systemctl restart lightdm

# matchbox-window-manager &

sleep 2

cd /home/$USER/Code/Sandbells
# git status
# pwd
# echo $HOSTNAME

luakit -Uu http://sandbells.local:8000 --display=:0
#luakit -vUu "http://sandbells.local:8000" --display=:0
