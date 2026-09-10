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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# installed copy:
# SCRIPT_DIR=/usr/local/lib/sandbells   # if you install it there
source "$SCRIPT_DIR/sandbells-wifi.sh"
LOGTAG="sandbells-net"
if have_time_net; then
  log "time host reachable — no action"
  exit 0
fi
log "no time host — trying WiFi"
try_connect && exit 0
log "no network succeeded"
exit 1
