#!/bin/bash
# 07-time.sh
# Sandbells Chrony Time Configuration Step
# Command line arguments:
#   $1 = QUICK_MODE (true/false) - skip pauses
#   $2 = DEBUG_MODE (true/false) - enable set -x

QUICK_MODE=${1:-false}
DEBUG_MODE=${2:-false}

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

# Candidate local GPS / NTP hosts (first reachable wins)
CANDIDATES=(
    "sandgps.local"
    "sandgps1.local"
    "sandgps2.local"
    "sandgps3.local"
)

if [ "$DEBUG_MODE" = true ]; then
    set -x
fi

echo "Searching for local GPS time servers..."
TIME_SERVER=""
FOUND_LIST=()

for host in "${CANDIDATES[@]}"; do
    # DNS resolve
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

echo ""
echo "Checking current time configuration..."

if [ -n "$TIME_SERVER" ] && grep -q "server $TIME_SERVER" /etc/chrony/chrony.conf 2>/dev/null; then
    echo "Local GPS time server ($TIME_SERVER) already configured."
else
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
fi

echo "Restarting chrony..."
sudo systemctl restart chrony

echo "Waiting for time sync..."
if ! timeout 15 chronyc waitsync 2>/dev/null; then
    echo "Warning: Time sync timeout. This is common on first boot without GPS server."
    echo "Debug info:"
    chronyc sources 2>/dev/null || true
    chronyc tracking 2>/dev/null || true
fi

echo ""
echo "Current time sources:"
timeout 8 chronyc sources || true

echo "Clock Status:"
chronyc tracking 2>/dev/null | grep -E "Stratum|Reference|System time|Leap" || true

echo "Time configuration step completed"
pause
