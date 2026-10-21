#!/bin/bash
# 17-observability.sh
# Crash evidence for a fanless Pi 3:
#   - persistent journal (/var/log/journal), capped at 50M for the SD card
#   - sandbells-thermal.timer: temp, throttling, load, memory each minute
# Idempotent: only restarts journald when its drop-in changes.
# Args: $1 = QUICK_MODE
# master_install auto-runs [0-9][0-9]-*.sh — no master_install edit needed.

QUICK_MODE=${1:-false}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck source=/dev/null
[ -f "$SCRIPT_DIR/sandbells-common.sh" ] && source "$SCRIPT_DIR/sandbells-common.sh"

JOURNAL_DIR="/var/log/journal"
JOURNALD_SRC="$SCRIPT_DIR/sandbells-journald.conf"
JOURNALD_DST="/etc/systemd/journald.conf.d/sandbells.conf"
THERMAL_SRC="$SCRIPT_DIR/sandbells-thermal.sh"
THERMAL_DST="/usr/local/bin/sandbells-thermal.sh"
SERVICE_SRC="$REPO_DIR/systemd/sandbells-thermal.service"
TIMER_SRC="$REPO_DIR/systemd/sandbells-thermal.timer"
UNIT_DIR="/etc/systemd/system"

if ! type pause &>/dev/null; then
  pause() {
    [ "$QUICK_MODE" = true ] && { sleep 1.5; return; }
    echo ""; read -r -p "Press Enter to continue (or Q to stop) > " choice
    [[ "$choice" =~ ^[Qq]$ ]] && { echo "Setup stopped safely."; exit 1; }
  }
fi

echo "=================================================="
echo " 17 – Observability (persistent journal + thermal log)"
echo "=================================================="

for f in "$JOURNALD_SRC" "$THERMAL_SRC" "$SERVICE_SRC" "$TIMER_SRC"; do
  [ -f "$f" ] || { echo "ERROR: missing $f"; exit 1; }
done

# ------------------------------------------------------------------
# 1. Persistent journal, capped
# ------------------------------------------------------------------
echo "[1/2] Persistent journal..."
RESTART_JOURNALD=false
if [ ! -d "$JOURNAL_DIR" ]; then
  sudo mkdir -p "$JOURNAL_DIR"
  sudo systemd-tmpfiles --create --prefix "$JOURNAL_DIR" 2>/dev/null || true
  echo "  created $JOURNAL_DIR"
  RESTART_JOURNALD=true
else
  echo "  already present: $JOURNAL_DIR"
fi
if sudo cmp -s "$JOURNALD_SRC" "$JOURNALD_DST"; then
  echo "  unchanged: $JOURNALD_DST"
else
  sudo install -d "$(dirname "$JOURNALD_DST")"
  sudo install -m 644 "$JOURNALD_SRC" "$JOURNALD_DST"
  echo "  installed $JOURNALD_DST"
  RESTART_JOURNALD=true
fi
if [ "$RESTART_JOURNALD" = true ]; then
  sudo systemctl restart systemd-journald
  sudo journalctl --flush 2>/dev/null || true
  echo "  journald restarted"
fi
journalctl --disk-usage 2>/dev/null || true
pause

# ------------------------------------------------------------------
# 2. Thermal logger (oneshot + minute timer)
# ------------------------------------------------------------------
echo "[2/2] Thermal logger..."
sudo install -m 755 "$THERMAL_SRC" "$THERMAL_DST"
echo "  installed $THERMAL_DST"
sudo install -m 644 "$SERVICE_SRC" "$UNIT_DIR/sandbells-thermal.service"
sudo install -m 644 "$TIMER_SRC" "$UNIT_DIR/sandbells-thermal.timer"
echo "  installed sandbells-thermal.service + .timer"
sudo systemctl daemon-reload
sudo systemctl enable --now sandbells-thermal.timer
sudo systemctl start sandbells-thermal.service || true

echo ""
echo "  Now: $("$THERMAL_DST")"
systemctl is-enabled sandbells-thermal.timer || true
systemctl is-active sandbells-thermal.timer || true
echo "Observability step completed"
echo "  Read back: journalctl -t sandbells-thermal --since -1h"
echo "  Last boot: journalctl -b -1 -e"
pause
