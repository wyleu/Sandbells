#!/bin/bash
# Shared Sandbells Header

show_header() {
    clear
    ELAPSED=$(( $(date +%s) - START_TIME ))
    echo "======================================================================"
    echo "          Sandbells Church Bell Kiosk"
    echo "======================================================================"
    echo "Date              : $(date)"
    echo "Elapsed Time      : ${ELAPSED} seconds"
    echo "User              : $(whoami)"
    echo "Hostname          : $(hostname)"
    echo "Machine           : $(cat /proc/cpuinfo | grep Model | cut -d: -f2 | xargs || echo 'Unknown')"
    echo "Architecture      : $(uname -m) ($(getconf LONG_BIT)-bit)"
    echo "Display Server    : ${XDG_SESSION_TYPE:-Unknown}  [${DISPLAY:-None}]"
    echo "Git Branch        : $(git branch --show-current 2>/dev/null || echo 'Not in git repo')"
    echo "Project Path      : ${PROJECT_DIR:-Unknown}"
    
    # zram status
    if swapon --show | grep -q zram; then
        ZRAM_SIZE=$(zramctl | grep zram0 | awk '{print $3}')
        echo "zram Swap         : Active (${ZRAM_SIZE})"
    else
        echo "zram Swap         : Not active"
    fi
    
    echo "======================================================================"
    echo ""
}
