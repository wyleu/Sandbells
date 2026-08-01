#!/bin/bash
# 07-time.sh
# Sandbells Chrony Time Configuration Step
# - Probe sandgps*.local from settings.json
# - Write chrony.conf
# - Install boot-time re-scan script + systemd unit
#
# Args: $1 = QUICK_MODE (true/false)  $2 = DEBUG_MODE (true/false)

QUICK_MODE=${1:-false}
DEBUG_MODE=${2:-false}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/sandbells-common.sh"

REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SELECT_SRC="$SCRIPT_DIR/sandbells-time-select.sh"
UNIT_SRC="$REPO_DIR/systemd/sandbells-time-select.service"
SELECT_DST="/usr/local/sbin/sandbells-time-select.sh"
UNIT_DST="/etc/systemd/system/sandbells-time-select.service"

echo "=================================================="
echo "Time Configuration (Chrony)"
echo "=================================================="

load_time_hosts
CANDIDATES=("${TIME_HOSTS[@]}")

if [ "$DEBUG_MODE" = true ]; then
    set -x
fi

# --- probe for local GPS time servers ---
echo "Searching for local GPS time servers..."
TIME_SERVER=""
FOUND_LIST=()

for host in "${CANDIDATES[@]}"; do
    if getent hosts "$host" >/dev/null 2>&1 || ping -c 1 -W 1 "$host" >/dev/null 2>&1; then
        echo "  found: $host"
        FOUND_LIST+=("$host")
        if [ -z "$TIME_SERVER" ]; then
            TIME_SERVER="$host"
        fi
    else
        echo "  miss: $host"
    fi
done

echo ""
if [ -n "$TIME_SERVER" ]; then
    echo "Using preferred local time server: $TIME_SERVER"
    if [ "${#FOUND_LIST[@]}" -gt 1 ]; then
        echo "Also reachable: ${FOUND_LIST[*]}"
    fi
else
    echo "No local sandgps*.local server found — using public NTP only."
fi

# --- write chrony config (with timeouts so it cannot hang) ---
echo ""
echo "Updating chrony config..."

timeout 10 sudo systemctl stop chrony 2>/dev/null || true
sudo cp /etc/chrony/chrony.conf /etc/chrony/chrony.conf.bak 2>/dev/null || true

if [ -n "$TIME_SERVER" ]; then
    sudo tee /etc/chrony/chrony.conf > /dev/null <<EOF
pool ntp.ubuntu.com iburst
server $TIME_SERVER iburst prefer
makestep 1.0 3
rtcsync
EOF
    echo "Chrony config updated (prefer $TIME_SERVER)."
else
    sudo tee /etc/chrony/chrony.conf > /dev/null <<EOF
pool ntp.ubuntu.com iburst
makestep 1.0 3
rtcsync
EOF
    echo "Chrony config updated (public NTP only)."
fi

echo "Restarting chrony..."
timeout 15 sudo systemctl restart chrony 2>/dev/null || {
    echo "Warning: chrony restart timed out — continuing anyway"
    sudo systemctl start chrony 2>/dev/null || true
}

echo "Waiting for time sync..."
if ! timeout 15 chronyc waitsync 2>/dev/null; then
    echo "Warning: Time sync timeout (common on first boot without GPS)."
    chronyc sources 2>/dev/null || true
    chronyc tracking 2>/dev/null || true
fi

echo ""
echo "Current time sources:"
timeout 8 chronyc sources || true
echo "Clock Status:"
chronyc tracking 2>/dev/null | grep -E "Stratum|Reference|System time|Leap" || true

# --- install boot-time re-scan ---
echo ""
echo "Installing boot-time GPS NTP selector..."

if [ ! -f "$SELECT_SRC" ]; then
    echo "ERROR: missing $SELECT_SRC"
    exit 1
fi
if [ ! -f "$UNIT_SRC" ]; then
    echo "ERROR: missing $UNIT_SRC"
    exit 1
fi

sudo install -m 755 "$SELECT_SRC" "$SELECT_DST"
echo "  installed $SELECT_DST"
sudo install -m 644 "$UNIT_SRC" "$UNIT_DST"
echo "  installed $UNIT_DST"

sudo systemctl daemon-reload
sudo systemctl enable sandbells-time-select.service
timeout 10 sudo systemctl restart sandbells-time-select.service 2>/dev/null || \
    timeout 10 sudo systemctl start sandbells-time-select.service 2>/dev/null || true

echo "  enabled sandbells-time-select.service"
systemctl is-enabled sandbells-time-select.service || true
systemctl is-active sandbells-time-select.service || true

echo ""
echo "Time configuration step completed"
pause
