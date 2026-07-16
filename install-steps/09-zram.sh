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
echo "ZRAM Swap Configuration"
echo "=================================================="

sudo apt install -y zram-tools 2>/dev/null || true

TOTAL_RAM=$(free -m | awk '/^Mem:/{print $2}')
ZRAM_SIZE=$((TOTAL_RAM / 2))
[ $ZRAM_SIZE -gt 384 ] && ZRAM_SIZE=384

echo "Setting ZRAM size to ${ZRAM_SIZE}M"

# Fix config (force no 'M')
sudo bash -c "cat > /etc/default/zramswap << EOF
ALGO=lz4
SIZE=${ZRAM_SIZE}
EOF"

# Clean restart
sudo swapoff -a 2>/dev/null || true
sudo systemctl daemon-reload
sudo systemctl restart zramswap.service

sleep 2

echo "Status:"
systemctl status zramswap.service --no-pager -l | tail -n 15

echo ""
echo "Swap:"
swapon --show

echo "ZRAM setup completed."
pause
