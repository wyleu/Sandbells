#!/bin/sh
xset -dpms       # disable DPMS (Energy Star) feautres.
xset s off       # disable screen saver
xset s noblank    # don't blank the video device
matchbox-window-manager &
cd /home/wyleu/Sandbells
midori -e fullscreen -a http://sandbells.local
