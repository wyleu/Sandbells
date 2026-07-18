#!/bin/bash
# 08-autologin.sh
# Sandbells Auto-login and Colored Prompt Setup

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
echo "Auto-login and Colored Prompt Setup"
echo "=================================================="

# Enable auto-login for user sandbells
sudo mkdir -p /etc/systemd/system/getty@tty1.service.d
sudo tee /etc/systemd/system/getty@tty1.service.d/override.conf > /dev/null <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty -o '-p -f -- \\u' --noclear --autologin sandbells %I $TERM
EOF

echo "Auto-login enabled for user sandbells"

# Add clean colored prompt
cat >> ~/.bashrc << 'EOF'

# Sandbells Clean Colored Prompt
case $(hostname) in
    sandbells)
        PS1="\[\e[1;36m\]\u@\h\[\e[0m\]:\w\$ " ;;
    sandbells2)
        PS1="\[\e[1;33m\]\u@\h\[\e[0m\]:\w\$ " ;;
    sandbells3)
        PS1="\[\e[1;32m\]\u@\h\[\e[0m\]:\w\$ " ;;
    *)
        PS1="\[\e[1;37m\]\u@\h\[\e[0m\]:\w\$ " ;;
esac
EOF

echo "Colored terminal prompt configured based on hostname"
echo "Setup completed. Reboot recommended to see changes."
pause
