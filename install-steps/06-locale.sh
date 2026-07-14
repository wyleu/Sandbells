#!/bin/bash
QUICK_MODE=${1:-false}
pause() {
    if [ "$QUICK_MODE" = true ]; then
        sleep 1.5
        return
    fi
    echo ""
    read -p "Press Enter to continue (or Q to stop) > " choice
    if [[ "$choice" =~ ^[Qq]$ ]]; then
        echo "Setup stopped safely."
        exit 0
    fi
}


# Locale step with debug option

DEBUG=${1:-false}

if [ "$DEBUG" = true ]; then
    echo "DEBUG MODE ENABLED"
    set -x
fi

echo "[6/8] Setting UK English locale..."

CURRENT_LOCALE=$(locale | grep LANG= | cut -d= -f2)

if [[ "$CURRENT_LOCALE" == *"en_US.UTF-8"* || "$CURRENT_LOCALE" == *"en_GB.UTF-8"* ]]; then
    echo "Locale is already correctly set to UK English ($CURRENT_LOCALE)"
else
    echo "Updating locale to en_US.UTF-8..."
    sudo locale-gen en_US.UTF-8
    sudo update-locale LANG=en_US.UTF-8
    sudo dpkg-reconfigure -f noninteractive locales
    echo "Locale updated to en_US.UTF-8"
fi

if [ "$DEBUG" = true ]; then
    set +x
fi
pause
