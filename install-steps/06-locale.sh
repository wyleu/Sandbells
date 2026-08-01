#!/bin/bash
# 06-locale.sh
# Sandbells Install Step – set UK English locale
#
# Args: $1 = QUICK_MODE (true/false)

QUICK_MODE=${1:-false}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/sandbells-common.sh"

echo "=================================================="
echo "Locale Setup"
echo "=================================================="

echo "Setting UK English locale..."
CURRENT_LOCALE=$(locale | grep LANG= | cut -d= -f2)

if [[ "$CURRENT_LOCALE" == *"en_GB.UTF-8"* || "$CURRENT_LOCALE" == *"en_US.UTF-8"* ]]; then
    echo "Locale is already set ($CURRENT_LOCALE)"
else
    echo "Updating locale to en_GB.UTF-8..."
    sudo locale-gen en_GB.UTF-8
    sudo update-locale LANG=en_GB.UTF-8
    sudo dpkg-reconfigure -f noninteractive locales
    echo "Locale updated"
fi

pause
