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
    
    # Better Display detection
    if [ -n "$DISPLAY" ]; then
        DISPLAY_INFO="${XDG_SESSION_TYPE:-X11} [${DISPLAY}]"
    else
        DISPLAY_INFO="${XDG_SESSION_TYPE:-Unknown}"
    fi
    echo "Display Server    : $DISPLAY_INFO"
    
    echo "Git Branch        : $(git branch --show-current 2>/dev/null || echo 'Not in git repo')"
    echo "Project Path      : ${PROJECT_DIR:-Unknown}"
    echo "======================================================================"
    echo ""
}
