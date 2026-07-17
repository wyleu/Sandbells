#!/bin/bash
# 02-wifi.sh
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


echo "Setting WiFi country and attempting tower network..."
sudo raspi-config nonint do_wifi_country GB
sudo raspi-config nonint do_wifi_ssid_passphrase sandbells Sandbells || true
echo "WiFi step completed"

pause
