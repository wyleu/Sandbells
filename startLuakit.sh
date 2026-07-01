#!/bin/sh


echo "Running /home/"$USER"/Code/Sandbells/startMidori.sh"
xset -dpms       # disable DPMS (Energy Star) feautres.
xset s off       # disable screen saver
xset s noblank    # don't blank the video device
matchbox-window-manager &
cd /home/$USER/Code/Sandbells

pwd
# midori -e fullscreen -a http://sandbells.local/home/
# midori -a http://sandbells.local/home/
luakit -u http://sandbells.local
