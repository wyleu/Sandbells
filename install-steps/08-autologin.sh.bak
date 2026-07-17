#!/bin/bash
# 08-autologin.sh
# Sandbells Auto-login and colored prompt setup

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

# Add colored prompt based on hostname
cat >> ~/.bashrc << 'EOF'

# Sandbells Colored Prompt
case $(hostname) in
    sandbells)
        PS1="\[\e[1;36m\][sandbells]\[\e[0m\] \u@\h:\w\$ " ;;
    sandbells2)
        PS1="\[\e[1;33m\][sandbells2]\[\e[0m\] \u@\h:\w\$ " ;;
    sandbells3)
        PS1="\[\e[1;32m\][sandbells3]\[\e[0m\] \u@\h:\w\$ " ;;
    *)
        PS1="\[\e[1;37m\][$(hostname)]\[\e[0m\] \u@\h:\w\$ " ;;
esac
EOF

echo "Colored terminal prompt configured based on hostname"

echo "Setup completed. Reboot recommended."
pause
