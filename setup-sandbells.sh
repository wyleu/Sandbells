#!/bin/bash
# Sandbells Top-Level Bootstrap Script

START_TIME=$(date +%s)

# Parse flags
QUICK_MODE=false
DEBUG_MODE=false

for arg in "$@"; do
    case $arg in
        --quick|-q|quick)
            QUICK_MODE=true
            ;;
        --debug|-d|debug)
            DEBUG_MODE=true
            set -x
            ;;
    esac
done

# Source shared header
if [ -f show_header.sh ]; then
    source show_header.sh
else
    echo "Warning: show_header.sh not found"
fi

show_header

PROJECT_DIR="$HOME/Code/Sandbells"

if [ ! -d "$PROJECT_DIR" ]; then
    echo "Sandbells project folder not found at $PROJECT_DIR"
    echo "Please copy the full Sandbells folder there and try again."
    exit 1
fi

echo "Project found at $PROJECT_DIR"
echo "Launching master installer..."
cd "$PROJECT_DIR"

if [ -x "./master_install.sh" ]; then
    if [ "$QUICK_MODE" = true ]; then
        ./master_install.sh quick
    else
        ./master_install.sh
    fi
else
    echo "Error: master_install.sh not found."
    exit 1
fi
