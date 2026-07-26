#!/bin/bash
# sandbells-network-select.sh — ensure local connectivity; try known WiFi SSIDs if down
set -e

LOGTAG="sandbells-net"
log() { logger -t "$LOGTAG" "$*"; echo "$*"; }

# SSID:PASSPHRASE — edit for tower / phone hotspots
NETWORKS=(
  "Sandbells:Sandbells",
  "sandbells:Sandbells",
  # "TowerPhone:yourpassword"
)

have_local_net() {
  ping -c 1 -W 1 sandgps3.local >/dev/null 2>&1 && return 0
  ping -c 1 -W 1 sandgps.local  >/dev/null 2>&1 && return 0
  ping -c 1 -W 1 sandgps1.local >/dev/null 2>&1 && return 0
  ping -c 1 -W 1 sandgps2.local >/dev/null 2>&1 && return 0
  ip -4 -br addr show eth0  2>/dev/null | grep -q 'UP' && return 0
  ip -4 -br addr show wlan0 2>/dev/null | grep -q 'UP' && return 0
  return 1
}

if have_local_net; then
  log "local net OK — no action"
  exit 0
fi

log "no local net — trying configured WiFi networks"

for entry in "${NETWORKS[@]}"; do
  ssid="${entry%%:*}"
  pass="${entry#*:}"
  log "try SSID: $ssid"
  if nmcli device wifi connect "$ssid" password "$pass" ifname wlan0 2>/dev/null; then
    sleep 3
    if have_local_net; then
      log "connected via $ssid"
      exit 0
    fi
    log "associated $ssid but local ping still failed"
  else
    log "failed: $ssid"
  fi
done

log "no network succeeded"
exit 1
