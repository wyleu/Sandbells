#!/bin/bash
# 07-time.sh
# Install time-select ensure helper + systemd unit, run one reconcile
# Chrony sources come from settings.json time_hosts via sandbells-time-select.sh
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
echo "Time Configuration (Chrony ensure)"
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

sudo install -m 755 "$SELECT_SRC" "$SELECT_DST"
echo "  installed $SELECT_DST"
sudo install -m 644 "$UNIT_SRC" "$UNIT_DST"
echo "  installed $UNIT_DST"

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

# ------------------------------------------------------------------
# fake-hwclock: the Pi has no RTC.  Without it a reboot starts at the
# image/kernel date (seen: 16 Jul 2026) until a time server answers.
# Restores the last saved time at boot; saves hourly and at shutdown.
# ------------------------------------------------------------------
echo ""
echo "fake-hwclock (no RTC on the Pi)..."
if package_installed fake-hwclock; then
    echo "  already installed: fake-hwclock"
else
    sudo apt-get install --no-install-recommends -y fake-hwclock || {
        echo "Warning: fake-hwclock install failed — continuing"
    }
fi
if command -v fake-hwclock >/dev/null 2>&1; then
    sudo systemctl enable fake-hwclock.service 2>/dev/null || true
    # Only save a time chrony trusts, never the stale boot date
    if chronyc tracking 2>/dev/null | grep -q "Leap status *: Normal"; then
        sudo fake-hwclock save force
        echo "  saved $(cat /etc/fake-hwclock.data 2>/dev/null) UTC to /etc/fake-hwclock.data"
    else
        echo "  chrony not synchronised yet — not saving (hourly cron/shutdown will)"
    fi
fi

echo ""
systemctl is-enabled sandbells-time-select.service || true
systemctl is-active sandbells-time-select.service || true

echo ""
echo "Time configuration step completed"
pause
