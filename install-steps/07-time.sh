#!/bin/bash
# 07-time.sh
# Sandbells Chrony Time Configuration Step
# - Read time_hosts from settings.json (sandmon, sandgps*, 10.42.0.1, …)
# - Ensure chrony 4 confdir/sourcedir layout
# - Install sandbells-time-select ensure helper + systemd unit
# - Run one reconcile now
#
# Args: $1 = QUICK_MODE (true/false)  $2 = DEBUG_MODE (true/false)

QUICK_MODE=${1:-false}
DEBUG_MODE=${2:-false}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/sandbells-common.sh"

REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SELECT_SRC="$SCRIPT_DIR/sandbells-time-select.sh"
UNIT_SRC="$REPO_DIR/systemd/sandbells-time-select.service"
SELECT_DST="/usr/local/sbin/sandbells-time-select.sh"
UNIT_DST="/etc/systemd/system/sandbells-time-select.service"

echo "=================================================="
echo "Time Configuration (Chrony)"
echo "=================================================="

if [ "$DEBUG_MODE" = true ]; then
    set -x
fi

load_time_hosts
echo "time_hosts from settings (or defaults):"
for h in "${TIME_HOSTS[@]}"; do
    echo "  - $h"
done
echo ""

for f in "$SELECT_SRC" "$UNIT_SRC"; do
    if [ ! -f "$f" ]; then
        echo "ERROR: missing $f"
        exit 1
    fi
done

# Install ensure helper + unit first so we can run the same path as boot
sudo install -m 755 "$SELECT_SRC" "$SELECT_DST"
echo "  installed $SELECT_DST"
sudo install -m 644 "$UNIT_SRC" "$UNIT_DST"
echo "  installed $UNIT_DST"

# Mild unit description refresh (optional local edit if still sandgps-only text)
sudo systemctl daemon-reload
sudo systemctl enable sandbells-time-select.service

echo ""
echo "Running time-select ensure..."
timeout 60 sudo "$SELECT_DST" || {
    echo "Warning: time-select returned non-zero — continuing"
}

echo ""
echo "Current time sources:"
timeout 8 chronyc sources -v 2>/dev/null || timeout 8 chronyc sources 2>/dev/null || true
echo "Clock status:"
chronyc tracking 2>/dev/null | grep -E "Stratum|Reference|System time|Leap" || true

echo ""
systemctl is-enabled sandbells-time-select.service || true
systemctl is-active sandbells-time-select.service || true

echo ""
echo "Time configuration step completed"
pause
