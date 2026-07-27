#!/bin/bash
# 99-eth-fallback.sh — install eth0 DHCP-then-static recovery
set -e

echo "=== 99 eth fallback (192.168.99.2/24) ==="

install -d /etc/sandbells
install -d /usr/local/sbin

# Helper (path relative to repo root when run from master_install)
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ -f "$ROOT/install-steps/sandbells-eth-fallback.sh" ]; then
  install -m 755 "$ROOT/install-steps/sandbells-eth-fallback.sh" /usr/local/sbin/sandbells-eth-fallback.sh
else
  # inline copy if you keep helper text only in this step
  echo "Place sandbells-eth-fallback.sh beside this script or in install-steps/"
  exit 1
fi

cat >/etc/systemd/system/sandbells-eth-fallback.service <<'EOF'
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

systemctl daemon-reload
systemctl enable sandbells-eth-fallback.service

echo "Installed. Reboot off-LAN to test: host 192.168.99.1 ↔ Pi 192.168.99.2"
echo "To disable fallback on a managed network:  sudo touch /etc/sandbells/network-enabled"
