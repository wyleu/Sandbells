#!/bin/bash
# start-kiosk-safe.sh
# Persistent Kiosk with better X management

echo "=== Starting Persistent Sandbells Kiosk ==="
echo "= = =  This is a  working version with browser to  to HDMI screen using lightdm & Luakit = = ="
pkill -9 luakit 2>/dev/null
pkill -9 matchbox-window-manager 2>/dev/null

export DISPLAY=:0

# Start X and keep it alive with a simple client
# if ! pgrep -x Xorg > /dev/null; then
#    echo "Starting X server..."
#    sudo xinit /dev/null -- :0 &
#    sleep 5
# fi

# Start window manager
#   A choice between  matchbox * startdm 
# startdm seesms easier at the moment .

# Start Mathbox
# echo "Starting matchbox -window-manager"
# matchbox-window-manager -use_titlebar no -use_cursor no &

# Start lightdm
echo "Start lightdm"
sudo systemctl restart lightdm
# sudo systemctl start lightdm


sleep 3

# Start Luakit with restart loop
echo "Launching Luakit kiosk with 20 second restart on sandbells.local:8000 ..."
while true; do
    luakit -Uu "http://sandbells.local:8000" 2>&1 | tee -a luakit.log
    echo "Luakit exited. Restarting in 20 seconds..."
    sleep 20
done &
