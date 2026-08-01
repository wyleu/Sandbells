#!/bin/bash
# 01-hostname.sh
# Sandbells Install Step – set hostname if still at default
#
# Args: $1 = QUICK_MODE (true/false)

QUICK_MODE=${1:-false}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/sandbells-common.sh"

echo "=================================================="
echo "Sandbells Hostname Setup"
echo "=================================================="

CURRENT=$(hostname)
echo "Current hostname: $CURRENT"

# Only change if it's the default Raspberry Pi name
if [[ "$CURRENT" != "raspberrypi" ]]; then
    echo "Keeping existing hostname: $CURRENT"
    pause
    exit 0
fi

BASE_NAME="sandbells"
echo "Scanning for existing Sandbells units..."

num=1
while true; do
    if [ $num -eq 1 ]; then
        candidate="$BASE_NAME"
    else
        candidate="${BASE_NAME}${num}"
    fi

    if ! ping -c 1 -W 2 "$candidate.local" >/dev/null 2>&1 && \
       ! ping -c 1 -W 2 "$candidate" >/dev/null 2>&1; then
        echo "Using hostname: $candidate"
        break
    fi
    echo "  $candidate is taken."
    num=$((num + 1))
done

echo "Setting hostname to: $candidate"
echo "$candidate" | sudo tee /etc/hostname > /dev/null
sudo sed -i "s/127.0.1.1.*/127.0.1.1\t$candidate/" /etc/hosts
sudo hostnamectl set-hostname "$candidate"
echo "Hostname set to $candidate"

pause
