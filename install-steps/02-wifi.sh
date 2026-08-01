#!/bin/bash
# 02-wifi.sh
# Sandbells Install Step – set WiFi country and try known networks
#
# Args: $1 = QUICK_MODE (true/false)

QUICK_MODE=${1:-false}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/sandbells-common.sh"

echo "=================================================="
echo "WiFi Setup"
echo "=================================================="

echo "Setting WiFi country to GB..."
sudo raspi-config nonint do_wifi_country GB

# Try networks from settings.json if available, otherwise fall back
load_networks

if [ ${#NETWORKS[@]} -gt 0 ]; then
    echo "Trying networks from settings.json..."
    for entry in "${NETWORKS[@]}"; do
        ssid="${entry%%:*}"
        pass="${entry#*:}"
        echo "  Attempting SSID: $ssid"
        sudo raspi-config nonint do_wifi_ssid_passphrase "$ssid" "$pass" && break
    done
else
    echo "No networks in settings — trying default..."
    sudo raspi-config nonint do_wifi_ssid_passphrase sandbells Sandbells || true
fi

echo "WiFi step completed"
pause
