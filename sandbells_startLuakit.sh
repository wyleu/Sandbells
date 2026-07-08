#!/bin/bash
# Sandbells - Luakit Kiosk Starter
# Description: Starts Luakit in full kiosk mode pointing to local Sandbells app
# Version: 1.0
# Usage: ./sandbells_startLuakit.sh [-v]

VERBOSE=false
if [ "$1" = "-v" ] || [ "$1" = "--verbose" ]; then
    VERBOSE=true
fi

echo "############################################################################"
echo "# Sandbells Luakit Kiosk"
echo "############################################################################"

if [ "$VERBOSE" = true ]; then
    echo "System Info:"
    echo "  Hostname : $(hostname)"
    echo "  Pi Model : $(cat /proc/device-tree/model 2>/dev/null || echo 'Unknown')"
    echo "  OS       : $(cat /etc/os-release | grep PRETTY_NAME | cut -d'"' -f2)"
    echo "  Arch     : $(uname -m)"
    echo "  User     : $(whoami)"
    echo "  Display  : $DISPLAY"
fi

# Disable power saving
xset -dpms
xset s off
xset s noblank

# Window manager
matchbox-window-manager &

# Start Luakit full screen
cd /home/$USER/Code/Sandbells
luakit -u "http://$(hostname).local" --profile kiosk

echo "Luakit started."
