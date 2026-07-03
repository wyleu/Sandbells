#!/bin/sh

echo "############################################################################"
echo "#                                                                          #"
echo "#                          Running  luakit                                 #"
echo "#                                                                          #"
echo "############################################################################"

xset -dpms       # disable DPMS (Energy Star) feautres.
xset s off       # disable screen saver
xset s noblank    # don't blank the video device
matchbox-window-manager &
cd /home/$USER/Code/Sandbells
git status
pwd
# midori -e fullscreen -a http://$HOSTNAME.local/home/
# midori -a http://$HOSTNAME.local/home/
luakit -u http://$HOSTNAME.local
