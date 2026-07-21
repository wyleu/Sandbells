#!/bin/bash
# master_install.sh
# Sandbells Master Installer - Orchestrates the numbered install steps

START_TIME=$(date +%s)

# Configuration
TIME_SERVER="sandgps3.local"
BROWSER="luakit"

# Source shared header
if [ -f show_header.sh ]; then
    source show_header.sh
else
    echo "Warning: show_header.sh not found"
fi

QUICK_MODE=false
if [[ "$1" == "--quick" || "$1" == "-q" ]]; then
    QUICK_MODE=true
    echo "Quick mode activated!"
fi

echo "Starting installation steps..."
echo ""

STEPS_DIR="./install-steps"
for step in $STEPS_DIR/[0-9][0-9]-*.sh; do
    if [ -x "$step" ]; then
        show_header
        echo "Running: $step"
        echo "----------------------------------------------------------------------"
        "$step" "$QUICK_MODE"
        EXIT_CODE=$?
        if [ $EXIT_CODE -ne 0 ]; then
            echo "Step cancelled or failed (exit code $EXIT_CODE)"
            exit 1
        fi
        echo "----------------------------------------------------------------------"
        echo ""
    fi
done

ELAPSED=$(( $(date +%s) - START_TIME ))
echo "======================================================================"
echo "ALL STEPS COMPLETED in ${ELAPSED} seconds"
echo "You can now reboot with: sudo reboot"
echo "======================================================================"
