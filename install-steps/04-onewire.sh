#!/bin/bash
# 04-onewire.sh
# Sandbells Install Step – enable 1-Wire
#
# Args: $1 = QUICK_MODE (true/false)

QUICK_MODE=${1:-false}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/sandbells-common.sh"

echo "=================================================="
echo "1-Wire Setup"
echo "=================================================="

echo "Enabling 1-Wire support..."
sudo raspi-config nonint do_onewire 0
echo "1-Wire enabled (active after reboot)"

pause
