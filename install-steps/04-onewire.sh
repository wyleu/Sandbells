#!/bin/bash
# 04-onewire.sh
# Sandbells Install Step
# Command line arguments:
#   $1 = QUICK_MODE (true/false)

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
        exit 1
    fi
}


echo "Enabling 1-Wire support..."
sudo raspi-config nonint do_onewire 0
echo "1-Wire enabled (active after reboot)"
pause
