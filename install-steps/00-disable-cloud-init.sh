#!/bin/bash
# 00-disable-cloud-init.sh
# Cloud-init is for cloud VMs. This is an offline kiosk — remove it so it
# cannot delay or block boot (graphical.target, multi-user.target, etc.).
set -euo pipefail

echo "==> Disabling cloud-init (offline kiosk)"

# Ask for the password once up front
sudo -v

UNITS=(
  cloud-init.service
  cloud-init-local.service
  cloud-config.service
  cloud-final.service
)

for unit in "${UNITS[@]}"; do
  sudo systemctl disable --now "$unit" 2>/dev/null || true
  sudo systemctl mask "$unit" 2>/dev/null || true
done

sudo systemctl disable cloud-init.target 2>/dev/null || true

echo "==> cloud-init disabled and masked"
