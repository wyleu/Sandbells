#!/bin/bash
# sandbells-network-select.sh — ensure local connectivity; try known WiFi SSIDs if down
#
# Config: /etc/sandbells/settings.json  (see settings.example.json)
#   networks: [ {"ssid":"...", "psk":"..."}, ... ]
#   time_hosts: [ "sandgps.local", ... ]
#
set -e

LOGTAG="sandbells-net"
SETTINGS="${SANDBELLS_SETTINGS:-/etc/sandbells/settings.json}"

log() { logger -t "$LOGTAG" "$*"; echo "$*"; }

DEFAULT_TIME_HOSTS=(
  sandgps.local sandgps1.local sandgps2.local sandgps3.local
)

load_time_hosts() {
  if [ -f "$SETTINGS" ] && command -v jq >/dev/null 2>&1; then
    mapfile -t TIME_HOSTS < <(jq -r '.time_hosts[]? // empty' "$SETTINGS" 2>/dev/null)
  fi
  if [ "${#TIME_HOSTS[@]}" -eq 0 ]; then
    TIME_HOSTS=("${DEFAULT_TIME_HOSTS[@]}")
  fi
}

load_networks() {
  NETWORKS=()
  if [ ! -f "$SETTINGS" ]; then
    log "no $SETTINGS — no WiFi fallbacks"
    return
  fi
  if ! command -v jq >/dev/null 2>&1; then
    log "jq not installed — cannot read networks from settings"
    return
  fi
  # lines: ssid<TAB>psk
  while IFS=$'\t' read -r ssid psk; do
    [ -n "$ssid" ] || continue
    NETWORKS+=("$ssid:$psk")
  done < <(jq -r '.networks[]? | "\(.ssid // "")\t\(.psk // "")"' "$SETTINGS" 2>/dev/null)
}

have_local_net() {
  local h
  for h in "${TIME_HOSTS[@]}"; do
    ping -c 1 -W 1 "$h" >/dev/null 2>&1 && return 0
  done
  ip -4 -br addr show eth0  2>/dev/null | grep -q 'UP' && return 0
  ip -4 -br addr show wlan0 2>/dev/null | grep -q 'UP' && return 0
  return 1
}

load_time_hosts
load_networks

if have_local_net; then
  log "local net OK — no action"
  exit 0
fi

log "no local net — trying configured WiFi networks"
if [ "${#NETWORKS[@]}" -eq 0 ]; then
  log "no networks configured — nothing to try"
  exit 1
fi

for entry in "${NETWORKS[@]}"; do
  ssid="${entry%%:*}"
  pass="${entry#*:}"
  # trim possible trailing comma from old-style entries
  ssid="${ssid%,}"
  pass="${pass%,}"
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
