#!/bin/bash
# Sandbells Master Installer

QUICK_MODE=false
if [[ "$1" == "--quick" || "$1" == "-q" ]]; then
    QUICK_MODE=true
    echo "Young nephew quick mode activated!"
fi


START_TIME=$(date +%s)

# Configuration (same as before)
HOSTNAME="sandbells"
WIFI_SSID="sandbells"
TIME_SERVER="sandgps3.local"
BROWSER="luakit"

show_header() {
    clear
    ELAPSED=$(( $(date +%s) - START_TIME ))
    echo "======================================================================"
    echo "          Sandbells Church Bell Kiosk Setup - Progress"
    echo "======================================================================"
    echo "Date              : $(date)"
    echo "Elapsed Time      : ${ELAPSED} seconds"
    echo "User              : $(whoami)"
    echo "Hostname          : $(hostname)"
    echo "Machine           : $(cat /proc/cpuinfo | grep Model | cut -d: -f2 || echo 'Unknown')"
    echo "Architecture      : $(uname -m) ($(getconf LONG_BIT)-bit)"
    echo "Git Branch        : $(git branch --show-current 2>/dev/null || echo 'Not in git repo')"
    echo "Intended Browser  : $BROWSER"
    echo ""
    echo "Status:"
    echo "   Hostname     : $HOSTNAME             [$(if [ "$(hostname)" = "$HOSTNAME" ]; then echo "Set"; else echo "Pending"; fi)]"
    echo "   WiFi         : $(iwgetid -r 2>/dev/null || echo 'Not connected')"
    echo "   SSH          : $(if systemctl is-enabled ssh 2>/dev/null | grep -q enabled; then echo "Enabled"; else echo "Pending"; fi)"
    echo "   1-Wire       : [Enabled after reboot]"
    echo "   Locale       : [UK English]"
    echo "   Time Server  : $TIME_SERVER          [Configured]"
    echo "======================================================================"
}

show_header
echo "Starting installation steps..."
echo ""

STEPS_DIR="./install-steps"


for step in $STEPS_DIR/[0-9][0-9]-*.sh; do
    if [ -x "$step" ]; then
        show_header
        echo "Running: $step"
        echo "----------------------------------------------------------------------"
        "$step" "$QUICK_MODE"   # Pass the mode
        echo "----------------------------------------------------------------------"
        echo ""
    fi
done

ELAPSED=$(( $(date +%s) - START_TIME ))
echo "======================================================================"
echo "ALL STEPS COMPLETED in ${ELAPSED} seconds"
echo "You can now reboot with: sudo reboot"
echo "======================================================================"
