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

echo "=== Installing zram (compressed RAM swap for Pi 3) ==="

sudo apt update
sudo apt install -y zram-tools

sudo bash -c 'cat > /etc/default/zramswap << EOF
ALGO=lz4
SIZE=384M
EOF'

sudo systemctl restart zramswap.service
sudo systemctl enable zramswap.service

echo "zram configured with 384MB compressed swap."
echo ""
echo "Current swap devices:"
swapon --show
echo ""
echo "zram device info:"
zramctl

echo ""
echo "zram installation completed successfully."
pause
