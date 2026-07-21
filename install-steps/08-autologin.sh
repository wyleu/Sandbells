#!/bin/bash
# 08-autologin.sh
# Sandbells Auto-login (console + lightdm graphical) and colored prompt
#
# Command line arguments:
#   $1 = QUICK_MODE (true/false)

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
echo " 08 – Auto-login (console + graphical) + prompt"
echo "=================================================="

USER_NAME="sandbells"

# ------------------------------------------------------------------
# 1. Console autologin (tty1) – useful for recovery / SSH-less access
# ------------------------------------------------------------------
echo "[1/4] Console autologin on tty1..."
sudo mkdir -p /etc/systemd/system/getty@tty1.service.d
sudo tee /etc/systemd/system/getty@tty1.service.d/override.conf > /dev/null <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty -o '-p -f -- \\\\u' --noclear --autologin ${USER_NAME} %I \$TERM
EOF
echo "Console autologin enabled for ${USER_NAME}"

# ------------------------------------------------------------------
# 2. LightDM graphical autologin (required for kiosk on HDMI)
# ------------------------------------------------------------------
echo "[2/4] LightDM graphical autologin..."
sudo mkdir -p /etc/lightdm/lightdm.conf.d
sudo tee /etc/lightdm/lightdm.conf.d/50-sandbells-kiosk.conf > /dev/null <<EOF
[Seat:*]
autologin-user=${USER_NAME}
autologin-user-timeout=0
xserver-command=X -s 0 -dpms
EOF

# Also set in main conf if present (raspi-config style) – harmless if already set
if [ -f /etc/lightdm/lightdm.conf ]; then
    sudo sed -i 's/^#\?autologin-user=.*/autologin-user='"${USER_NAME}"'/' /etc/lightdm/lightdm.conf 2>/dev/null || true
    sudo sed -i 's/^#\?autologin-user-timeout=.*/autologin-user-timeout=0/' /etc/lightdm/lightdm.conf 2>/dev/null || true
    if ! grep -q '^autologin-user=' /etc/lightdm/lightdm.conf; then
        echo "autologin-user=${USER_NAME}" | sudo tee -a /etc/lightdm/lightdm.conf > /dev/null
        echo "autologin-user-timeout=0" | sudo tee -a /etc/lightdm/lightdm.conf > /dev/null
    fi
fi

sudo systemctl enable lightdm.service
echo "LightDM autologin configured for ${USER_NAME}"

# ------------------------------------------------------------------
# 3. Boot into graphical target (not text-only multi-user)
# ------------------------------------------------------------------
echo "[3/4] Default boot target → graphical.target..."
sudo systemctl set-default graphical.target
echo "Default target is now: $(systemctl get-default)"

# ------------------------------------------------------------------
# 4. Colored prompt + sandbells-status helper
# ------------------------------------------------------------------
echo "[4/4] Colored prompt + sandbells-status..."
if ! grep -q "Sandbells Clean Colored Prompt" ~/.bashrc 2>/dev/null; then
    cat >> ~/.bashrc << 'EOF'

# Sandbells Clean Colored Prompt
case $(hostname) in
    sandbells)  PS1="\[\e[1;36m\]\u@\h\[\e[0m\]:\w\$ " ;;
    sandbells2) PS1="\[\e[1;33m\]\u@\h\[\e[0m\]:\w\$ " ;;
    sandbells3) PS1="\[\e[1;32m\]\u@\h\[\e[0m\]:\w\$ " ;;
    *)          PS1="\[\e[1;37m\]\u@\h\[\e[0m\]:\w\$ " ;;
esac
EOF
    echo "Colored prompt added"
else
    echo "Colored prompt already present"
fi

sudo tee /usr/local/bin/sandbells-status > /dev/null <<'EOF'
#!/bin/bash
cd /home/sandbells/Code/Sandbells
export START_TIME=$(date +%s)
source show_header.sh
show_header
EOF
sudo chmod +x /usr/local/bin/sandbells-status
echo "sandbells-status command ready"

echo ""
echo "Auto-login setup COMPLETE."
echo "  • Console: getty@tty1 autologin"
echo "  • Graphical: lightdm autologin as ${USER_NAME}"
echo "  • Boot target: graphical.target"
echo "Reboot recommended to verify full kiosk path."
pause
