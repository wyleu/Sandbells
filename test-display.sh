#!/bin/bash
START_TIME=$(date +%s)
PROJECT_DIR="$HOME/Code/Sandbells"
source "$PROJECT_DIR/show_header.sh"
show_header

echo "=== Display Diagnostics ==="
echo "Current user     : $(whoami)"
echo "DISPLAY          : ${DISPLAY:-Not set}"
echo "XAUTHORITY       : ${XAUTHORITY:-Not set}"
echo ".Xauthority file : $(ls -l /home/sandbells/.Xauthority 2>/dev/null || echo 'MISSING!')"
echo "Xorg processes   : $(pgrep -l Xorg || echo 'None')"
echo "LightDM status   :"
systemctl status lightdm --no-pager -l | head -n 12
echo ""
echo "Trying to talk to X server..."
export DISPLAY=:0
export XAUTHORITY=/home/sandbells/.Xauthority
xset q 2>&1 | head -n 6 || echo "→ xset FAILED"
echo ""
echo "matchbox test:"
matchbox-window-manager -help > /dev/null 2>&1 && echo "→ matchbox OK" || echo "→ matchbox command not found"
