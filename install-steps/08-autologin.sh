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


echo "Setting up automatic login..."
sudo tee /etc/lightdm/lightdm.conf > /dev/null <<EOF
[Seat:*]
autologin-user=sandbells
autologin-user-timeout=0
autologin-session=lightdm-xsession
EOF
echo "Auto-login configured"
pause
