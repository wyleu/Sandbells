#!/bin/bash
# Sandbells Top-Level Bootstrap Script

START_TIME=$(date +%s)

show_header() {
    clear
    ELAPSED=$(( $(date +%s) - START_TIME ))
    echo "======================================================================"
    echo "          Sandbells Church Bell Kiosk Bootstrap"
    echo "======================================================================"
    echo "Date              : $(date)"
    echo "Elapsed Time      : ${ELAPSED} seconds"
    echo "User              : $(whoami)"
    echo "Hostname          : $(hostname)"
    echo "Machine           : $(cat /proc/cpuinfo | grep Model | cut -d: -f2 || echo 'Unknown')"
    echo "Architecture      : $(uname -m) ($(getconf LONG_BIT)-bit)"
    echo "Display Server    : ${XDG_SESSION_TYPE:-Unknown}"
    echo "Git Branch        : $(git branch --show-current 2>/dev/null || echo 'Not in git repo')"
    echo ""
    echo "Project Path      : $PROJECT_DIR"
    echo "======================================================================"
}

show_header

PROJECT_DIR="$HOME/Code/Sandbells"

if [ ! -d "$PROJECT_DIR" ]; then
    echo "Sandbells project folder not found!"
    echo ""
    echo "This system is likely offline."
    echo "Please copy the full Sandbells folder to:"
    echo "   $PROJECT_DIR"
    echo ""
    echo "Then run this script again."
    exit 1
fi

echo "Project found. Launching master installer..."
cd "$PROJECT_DIR"

if [ -x "./master_install.sh" ]; then
    ./master_install.sh
else
    echo "Master installer not found."
    exit 1
fi
