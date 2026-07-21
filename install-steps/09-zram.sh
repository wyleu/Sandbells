#!/bin/bash
# 09-zram.sh
# Sandbells ZRAM Compressed Swap Setup

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
echo "ZRAM Swap Configuration"
echo "=================================================="

# Install if needed
sudo apt install -y zram-tools 2>/dev/null || true

# Calculate reasonable size (half RAM, max 384M)
TOTAL_RAM=$(free -m | awk '/^Mem:/{print $2}')
ZRAM_SIZE=$((TOTAL_RAM / 2))
[ $ZRAM_SIZE -gt 384 ] && ZRAM_SIZE=384

echo "Total RAM: ${TOTAL_RAM}M → Setting ZRAM to ${ZRAM_SIZE}M"

# Configure
sudo bash -c "cat > /etc/default/zramswap << EOF
ALGO=lz4
SIZE=${ZRAM_SIZE}M
EOF"

# Restart cleanly
sudo swapoff -a 2>/dev/null || true
sudo systemctl restart zramswap.service 2>/dev/null || true

sleep 2

# Check status
if swapon --show | grep -q zram; then
    ZRAM_SIZE=$(swapon --show | grep zram | awk '{print $3}')
    echo "ZRAM: Active (${ZRAM_SIZE})"
else
    echo "Warning: ZRAM not active"
fi

echo "ZRAM setup completed."
pause
