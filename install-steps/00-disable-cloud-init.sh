#!/bin/bash
# 00-disable-cloud-init.sh
# Cloud-init is for cloud VMs. This is an offline kiosk — remove it so it
# cannot delay or block boot.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/sandbells-common.sh"

echo "==> Disabling cloud-init (offline kiosk)"

sudo -v

UNITS=(
  cloud-init.service
  cloud-init-local.service
  cloud-config.service
  cloud-final.service
)

for unit in "${UNITS[@]}"; do
  echo "  Processing $unit ..."
  stop_and_disable "$unit"
  sudo systemctl mask "$unit" 2>/dev/null || true
done

stop_and_disable cloud-init.target
sudo systemctl daemon-reload 2>/dev/null || true

echo "==> cloud-init disabled and masked"
