#!/bin/bash
QUICK_MODE=${1:-false}

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
echo "Sandbells Hostname Setup"
echo "=================================================="

BASE_NAME="sandbells"

# Find next available hostname
num=1
while true; do
    if [ $num -eq 1 ]; then
        candidate="$BASE_NAME"
    else
        candidate="${BASE_NAME}${num}"
    fi

    if ! ping -c 1 -W 2 "$candidate.local" >/dev/null 2>&1 && \
       ! ping -c 1 -W 2 "$candidate" >/dev/null 2>&1; then
        echo "Available hostname: $candidate"
        break
    fi
    num=$((num + 1))
    if [ $num -gt 20 ]; then
        candidate="$BASE_NAME"
        break
    fi
done

# Set hostname
echo "Setting hostname to: $candidate"
echo "$candidate" | sudo tee /etc/hostname > /dev/null
sudo sed -i "s/127.0.1.1.*/127.0.1.1\t$candidate/" /etc/hosts

sudo hostnamectl set-hostname "$candidate" 2>/dev/null || true

echo "Hostname set to $candidate"
pause
