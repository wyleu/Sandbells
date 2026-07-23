#!/bin/bash
# 07-time.sh
# Sandbells Chrony Time Configuration Step
# - Probe sandgps.local / sandgps1–3
# - Write chrony.conf for this install
# - Install boot-time re-scan script + systemd unit
#
# Args: $1 = QUICK_MODE (true/false)  $2 = DEBUG_MODE (true/false)

QUICK_MODE=${1:-false}
DEBUG_MODE=${2:-false}

# Repo paths (script lives in install-steps/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SELECT_SRC="$SCRIPT_DIR/sandbells-time-select.sh"
UNIT_SRC="$REPO_DIR/systemd/sandbells-time-select.service"
SELECT_DST="/usr/local/sbin/sandbells-time-select.sh"
UNIT_DST="/etc/systemd/system/sandbells-time-select.service"

pause() {
    if [ "$QUICK_MODE" = true ]; then
        sleep 1.5
        return
    fi
    echo ""
    read -p "Press Enter to continue (or Q to stop) > " choice
    if [[ "$choice" =~ ^[Qq]$ ]]; then
        echo "Setup stopped safely."
        exit 1
    fi
}

echo "=================================================="
echo "Time Configuration (Chrony)"
echo "=================================================="

CANDIDATES=(
    "sandgps.local"
    "sandgps1.local"
    "sandgps2.local"
    "sandgps3.local"
)

if [ "$DEBUG_MODE" = true ]; then
    set -x
fi

# --- probe now (for this install session) ---
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
        echo "  miss:  $host"
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

# --- write chrony for this install ---
echo ""
echo "Updating chrony config..."
sudo systemctl stop chrony 2>/dev/null || true
sudo cp /etc/chrony/chrony.conf /etc/chrony/chrony.conf.bak 2>/dev/null || true

if [ -n "$TIME_SERVER" ]; then
    cat | sudo tee /etc/chrony/chrony.conf > /dev/null <<EOF
pool ntp.ubuntu.com iburst
server $TIME_SERVER iburst prefer
makestep 1.0 3
rtcsync
EOF
    echo "Chrony config updated (prefer $TIME_SERVER)."
else
    cat | sudo tee /etc/chrony/chrony.conf > /dev/null <<EOF
pool ntp.ubuntu.com iburst
makestep 1.0 3
rtcsync
EOF
    echo "Chrony config updated (public NTP only)."
fi

echo "Restarting chrony..."
sudo systemctl restart chrony

echo "Waiting for time sync..."
if ! timeout 15 chronyc waitsync 2>/dev/null; then
    echo "Warning: Time sync timeout. This is common on first boot without GPS server."
    chronyc sources 2>/dev/null || true
    chronyc tracking 2>/dev/null || true
fi

echo ""
echo "Current time sources:"
timeout 8 chronyc sources || true
echo "Clock Status:"
chronyc tracking 2>/dev/null | grep -E "Stratum|Reference|System time|Leap" || true

# --- install boot-time re-scan (clean build support) ---
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
sudo systemctl restart sandbells-time-select.service 2>/dev/null || \
    sudo systemctl start sandbells-time-select.service

echo "  enabled sandbells-time-select.service"
systemctl is-enabled sandbells-time-select.service || true
systemctl is-active sandbells-time-select.service || true

echo ""
echo "Time configuration step completed"
pause
