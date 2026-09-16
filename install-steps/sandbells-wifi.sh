#!/bin/bash
# =============================================================================
# sandbells-wifi.sh
#
# Shared WiFi + time-host library for Sandbells machines.
#
# PURPOSE
#   One place for “how do we get on a local network and see a time server?”
#   Install (02-wifi.sh) and runtime (sandbells-network-select.sh / systemd
#   timer) must use the same rules. Previously they did not:
#     - 02-wifi.sh used raspi-config / wpa_supplicant
#     - network-select used nmcli
#     - “local net OK” treated eth0 UP as success, so a home cable or the
#       192.168.99.2 fallback stopped the tower SSID ever being tried
#   This file is the single implementation. The other two scripts only source
#   it and call the functions below.
#
# WHEN IT RUNS
#   Install: 02-wifi.sh sources this after setting the WiFi country (GB).
#     Loads /etc/sandbells/settings.json, prompts on a tty if networks[] is
#     empty, writes NetworkManager profiles, tries to associate.
#   Boot / timer: sandbells-network-select.sh sources this. If a time host
#     already answers, it exits. Otherwise it brings the radio up, ensures
#     NM profiles exist, and walks the SSID list.
#
# WHAT “SUCCESS” MEANS
#   have_time_net: at least one name/IP in settings.json time_hosts replies
#   to ping (1 second timeout). That is the GPS / NTP box on the isolated
#   church LAN (e.g. 10.42.0.1, sandgps3.local).
#   Ethernet carrier, a DHCP address, or the recovery address 192.168.99.2
#   are NOT success. Those are for SSH when the hotspot is down; they must
#   not skip WiFi.
#
# CONFIG
#   SANDBELLS_SETTINGS or /etc/sandbells/settings.json
#     networks[]:  { "ssid": "...", "psk": "..." }
#     time_hosts[]: hostnames or IPs to ping
#   First SSID in networks[] gets NM autoconnect-priority 100, then 90, 80…
#   so the tower hotspot (usually Sandbells) wins when several APs exist.
#
# FUNCTIONS
#   load_time_hosts      fill TIME_HOSTS from JSON (or built-in defaults)
#   load_networks        fill NETWORKS as ssid<TAB>psk (psk may contain ':')
#   have_time_net        ping time_hosts only
#   ensure_radio         nmcli wifi on, wlan0 managed and up
#   ensure_nm_profiles   create/update NM connections from networks[]
#   try_connect          profiles + walk SSIDs until have_time_net
#   prompt_add_network   interactive SSID/PSK → append to settings.json
#
# NOT IN THIS FILE
#   Ethernet DHCP-then-fallback (99-eth / NetworkManager eth profile)
#   chrony / time-select (runs after a time host is reachable)
#   kiosk start (must still proceed on failure → HDMI shows NO LOCK)
#
# DEPLOY
#   Copy this file next to sandbells-network-select.sh
#   (e.g. /usr/local/sbin or /usr/local/lib/sandbells) and source it from
#   both 02-wifi.sh and the installed selector. Requires jq and nmcli.
# =============================================================================
SETTINGS="${SANDBELLS_SETTINGS:-/etc/sandbells/settings.json}"
LOGTAG="${LOGTAG:-sandbells-wifi}"

log() { logger -t "$LOGTAG" "$*"; echo "$*"; }

DEFAULT_TIME_HOSTS=(
  sandgps.local sandgps1.local sandgps2.local sandgps3.local sandmon.local
)

load_time_hosts() {
  TIME_HOSTS=()
  if [ -f "$SETTINGS" ] && command -v jq >/dev/null 2>&1; then
    mapfile -t TIME_HOSTS < <(jq -r '.time_hosts[]? // empty' "$SETTINGS" 2>/dev/null)
  fi
  if [ "${#TIME_HOSTS[@]}" -eq 0 ]; then
    TIME_HOSTS=("${DEFAULT_TIME_HOSTS[@]}")
  fi
}

load_networks() {
  NETWORKS=()
  if [ ! -f "$SETTINGS" ] || ! command -v jq >/dev/null 2>&1; then
    return
  fi
  while IFS=$'\t' read -r ssid psk; do
    [ -n "$ssid" ] || continue
    NETWORKS+=("$ssid"$'\t'"$psk")
  done < <(jq -r '.networks[]? | "\(.ssid // "")\t\(.psk // "")"' "$SETTINGS" 2>/dev/null)
}

# Success = a configured time host answers. Ethernet-up is not enough.
have_time_net() {
  local h
  load_time_hosts
  for h in "${TIME_HOSTS[@]}"; do
    [ -n "$h" ] || continue
    ping -c 1 -W 1 "$h" >/dev/null 2>&1 && return 0
  done
  return 1
}

ensure_radio() {
  command -v nmcli >/dev/null 2>&1 || return 1
  nmcli radio wifi on 2>/dev/null || true
  nmcli device set wlan0 managed yes 2>/dev/null || true
  ip link set wlan0 up 2>/dev/null || true
}

# NETWORKS entries are ssid<TAB>psk so passwords may contain ':'
ensure_nm_profiles() {
  local ssid psk pri
  command -v nmcli >/dev/null 2>&1 || return 1
  load_networks
  pri=100
  for entry in "${NETWORKS[@]}"; do
    ssid="${entry%%$'\t'*}"
    psk="${entry#*$'\t'}"
    [ -n "$ssid" ] || continue
    if nmcli -t -f NAME connection show | grep -Fxq "$ssid"; then
      nmcli connection modify "$ssid" \
        wifi.ssid "$ssid" \
        wifi-sec.key-mgmt wpa-psk \
        wifi-sec.psk "$psk" \
        connection.autoconnect yes \
        connection.autoconnect-priority "$pri" \
        connection.interface-name wlan0 2>/dev/null || true
    else
      nmcli connection add type wifi con-name "$ssid" ifname wlan0 ssid "$ssid" \
        wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$psk" \
        connection.autoconnect yes \
        connection.autoconnect-priority "$pri" >/dev/null
    fi
    pri=$((pri - 10))
  done
}

try_connect() {
  local ssid psk
  ensure_radio
  ensure_nm_profiles
  load_networks
  if have_time_net; then
    return 0
  fi
  for entry in "${NETWORKS[@]}"; do
    ssid="${entry%%$'\t'*}"
    psk="${entry#*$'\t'}"
    [ -n "$ssid" ] || continue
    log "try SSID: $ssid"
    if nmcli connection up "$ssid" ifname wlan0 2>/dev/null || \
       nmcli device wifi connect "$ssid" password "$psk" ifname wlan0 2>/dev/null; then
      sleep 3
      if have_time_net; then
        log "connected via $ssid"
        return 0
      fi
      log "associated $ssid but no time host"
    else
      log "failed: $ssid"
    fi
  done
  return 1
}

prompt_add_network() {
  [ -t 0 ] || return 1
  local ssid psk
  echo "No WiFi networks in $SETTINGS"
  read -r -p "SSID (blank to skip): " ssid
  [ -n "$ssid" ] || return 1
  read -r -s -p "Password: " psk
  echo
  command -v jq >/dev/null 2>&1 || return 1
  sudo mkdir -p "$(dirname "$SETTINGS")"
  if [ ! -f "$SETTINGS" ]; then
    echo '{"networks":[],"time_hosts":[]}' | sudo tee "$SETTINGS" >/dev/null
  fi
  tmp=$(mktemp)
  jq --arg s "$ssid" --arg p "$psk" \
    '.networks += [{"ssid":$s,"psk":$p}]' "$SETTINGS" > "$tmp"
  sudo mv "$tmp" "$SETTINGS"
  log "added SSID $ssid to $SETTINGS"
}
