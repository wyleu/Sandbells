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
echo "Sandbells Multi-Unit Hostname Setup"
echo "=================================================="

BASE_NAME="sandbells"

# Check if a hostname is already set to something sensible
CURRENT=$(hostname)
if [[ "$CURRENT" != "raspberrypi" && "$CURRENT" != "sandbells" ]]; then
    echo "Current hostname is already: $CURRENT"
    read -p "Keep current hostname? (Y/n): " keep
    if [[ "$keep" =~ ^[Yy] ]]; then
        pause
        exit 0
    fi
fi

echo "Scanning local network for existing Sandbells units..."

num=1
while true; do
    if [ $num -eq 1 ]; then
        candidate="$BASE_NAME"
    else
        candidate="${BASE_NAME}${num}"
    fi

    # Test both .local and without
    if ! ping -c 1 -W 2 "$candidate.local" >/dev/null 2>&1 && \
       ! ping -c 1 -W 2 "$candidate" >/dev/null 2>&1; then
        echo "✅ Found available hostname: $candidate"
        break
    fi

    echo "   $candidate.local is already in use."
    ((num++))
    
    if [ $num -gt 30 ]; then
        echo "⚠ Many units detected - switching to manual entry."
        break
    fi
done

# User confirmation / override
read -p "Use hostname '$candidate' ? [Y/n] or type custom name: " input
if [[ -n "$input" && ! "$input" =~ ^[Yy]$ ]]; then
    if [[ "$input" =~ ^[0-9]+$ ]]; then
        candidate="${BASE_NAME}${input}"
    else
        candidate="$input"
    fi
fi

HOSTNAME="$candidate"

echo "Setting hostname to: $HOSTNAME"

# Apply the hostname
sudo hostnamectl set-hostname "$HOSTNAME"
sudo sed -i "s/127.0.1.1.*/127.0.1.1\t$HOSTNAME/" /etc/hosts

echo "Hostname set successfully to $HOSTNAME.local"
echo "=================================================="

pause
