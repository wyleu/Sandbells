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
source "$SCRIPT_DIR/sandbells-wifi.sh"
load_networks
if [ "${#NETWORKS[@]}" -eq 0 ]; then
  prompt_add_network || true
fi
ensure_nm_profiles || true
try_connect || true

echo "WiFi step completed"
