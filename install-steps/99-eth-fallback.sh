#!/bin/bash
# 99-eth-fallback.sh
# Install eth0 DHCP-then-static recovery
#
# Args: $1 = QUICK_MODE (true/false)

QUICK_MODE=${1:-false}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/sandbells-common.sh"

echo "=== 99 eth fallback (192.168.99.2/24) ==="

ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HELPER_SRC="$SCRIPT_DIR/sandbells-eth-fallback.sh"
HELPER_DST="/usr/local/sbin/sandbells-eth-fallback.sh"
UNIT_DST="/etc/systemd/system/sandbells-eth-fallback.service"

# Ensure directories exist
sudo install -d /etc/sandbells
sudo install -d /usr/local/sbin

# Install helper script
if [ -f "$HELPER_SRC" ]; then
    sudo install -m 755 "$HELPER_SRC" "$HELPER_DST"
    echo "  installed $HELPER_DST"
else
    echo "ERROR: missing $HELPER_SRC"
    exit 1
fi

# Install systemd unit
sudo tee "$UNIT_DST" > /dev/null <<'EOF'
[Unit]
Description=Sandbells eth0 static fallback if DHCP fails
After=network-pre.target NetworkManager.service
Wants=NetworkManager.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/sandbells-eth-fallback.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

echo "  installed $UNIT_DST"

sudo systemctl daemon-reload
sudo systemctl enable sandbells-eth-fallback.service

echo ""
echo "Installed. Reboot off-LAN to test: host 192.168.99.1 ↔ Pi 192.168.99.2"
echo "To disable fallback on a managed network: sudo touch /etc/sandbells/network-enabled"

pause
