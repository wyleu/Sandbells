#!/bin/bash
# sandbells-early-status.sh
# Console status before LightDM — NETWORK / SERVER / HARDWARE / TIME
# Env: SANDBELLS_EARLY_STATUS_DELAY (default 10), SANDBELLS_EARLY_STATUS_TTY (default /dev/tty1)

set -e
DELAY="${SANDBELLS_EARLY_STATUS_DELAY:-10}"
TTY="${SANDBELLS_EARLY_STATUS_TTY:-/dev/tty1}"

run() { timeout 3 "$@" 2>/dev/null || true; }
iface_state() { [ -r /sys/class/net/$1/operstate ] && cat /sys/class/net/$1/operstate || echo missing; }
iface_ipv4() { ip -4 -o addr show dev "$1" 2>/dev/null | awk '/inet / {print $4; exit}'; }
wifi_ssid() { iwgetid -r 2>/dev/null || true; }
svc() { systemctl is-active "$1" 2>/dev/null || echo unknown; }

chrony_label() {
  local out src=""
  out=$(run chronyc sources) || { echo "NO LOCK"; return; }
  while IFS= read -r line; do
    if [[ "$line" =~ ^.\* ]]; then
      src=$(echo "$line" | awk '{print $2}')
      echo "${src:-synced}"; return
    fi
  done <<< "$out"
  echo "NO LOCK"
}

git_info() {
  for repo in /home/sandbells/Code/Sandbells /home/pi/Code/Sandbells "$HOME/Code/Sandbells"; do
    if [ -d "$repo/.git" ]; then
      echo "$(run git -C "$repo" branch --show-current) @ $(run git -C "$repo" rev-parse --short HEAD)"
      return
    fi
  done
  echo "unknown @ unknown"
}

HOSTNAME=$(hostname 2>/dev/null || echo unknown)
WIFI_STATE=$(iface_state wlan0); WIFI_SSID=$(wifi_ssid); WIFI_IP=$(iface_ipv4 wlan0)
WIRED_STATE=$(iface_state eth0); WIRED_IP=$(iface_ipv4 eth0)
FALLBACK=no; case "$WIRED_IP" in 192.168.99.2|192.168.99.2/*) FALLBACK=yes;; esac
TEMP=$(run vcgencmd measure_temp | sed "s/temp=//;s/'C/°C/")
FAN=—; for p in /run/sandbells-fan.pct /tmp/sandbells-fan.pct; do [ -r "$p" ] && { FAN="$(cat "$p")%"; break; }; done
MEM=$(run free -h | awk '/^Mem:/{print $3" / "$2}')
MODEL=$(tr -d '\0' </sys/firmware/devicetree/base/model 2>/dev/null || uname -m)
LOAD=$(cut -d' ' -f1 /proc/loadavg 2>/dev/null || echo —)
THROTTLED=—
out=$(run vcgencmd get_throttled)
if [ -n "$out" ]; then
  echo "$out" | grep -q '=0x0$' && THROTTLED=No || THROTTLED=Yes
fi
TIME_LABEL=$(chrony_label); GIT=$(git_info)

{
  clear 2>/dev/null || true
  echo "============================================"
  echo "  SANDBELLS  EARLY STATUS"
  echo "============================================"
  echo
  echo "NETWORK"
  printf "  WiFi     : %-16s (%s)   IP: %s\n" "${WIFI_SSID:--}" "$WIFI_STATE" "${WIFI_IP:--}"
  printf "  Wired    : %-16s          IP: %s\n" "$WIRED_STATE" "${WIRED_IP:--}"
  echo "  Fallback : $FALLBACK"
  echo
  echo "SERVER"
  echo "  Hostname : ${HOSTNAME}.local"
  echo "  Git      : $GIT"
  echo "  Services : nginx=$(svc nginx)  gunicorn=$(svc gunicorn)  kiosk=$(svc sandbells-kiosk)"
  echo
  echo "HARDWARE"
  echo "  Model    : $MODEL"
  echo "  Temp/Fan : ${TEMP:--}  /  $FAN"
  echo "  Memory   : ${MEM:--}"
  echo "  Load     : $LOAD"
  echo "  Throttled: $THROTTLED"
  echo
  echo "TIME"
  echo "  Source   : $TIME_LABEL"
  echo
  echo "--------------------------------------------"
  echo "  Continuing to kiosk in ${DELAY} seconds..."
  echo "============================================"
} > "$TTY" 2>/dev/null || echo "WARNING: could not write to $TTY" >&2
sleep "$DELAY"
