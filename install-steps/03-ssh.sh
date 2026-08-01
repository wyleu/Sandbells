#!/bin/bash
# 03-ssh.sh
# Sandbells Install Step – ensure SSH is enabled
#
# Args: $1 = QUICK_MODE (true/false)

QUICK_MODE=${1:-false}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/sandbells-common.sh"

echo "=================================================="
echo "SSH Setup"
echo "=================================================="

echo "Enabling SSH access..."
sudo raspi-config nonint do_ssh 0

echo "SSH enabled"
pause
