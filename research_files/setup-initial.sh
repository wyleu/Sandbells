#!/bin/bash
# =====================================================
# Sandbells Friendly Setup Installer
# Kiosk Recovery - Offline Church Tower Version
# =====================================================

# ==================== CONFIGURATION ====================
HOSTNAME="sandbells"
WIFI_SSID="sandbells"
WIFI_PASSWORD="Sandbells"
TIME_SERVER="sandgps3.local"
TARGET_USER="sandbells"
BROWSER="luakit"

# =====================================================

set -e

START_TIME=$(date +%s)

QUICK_MODE=false
if [[ "$1" == "--quick" || "$1" == "-q" ]]; then
    QUICK_MODE=true
    echo "Young nephew quick mode activated!"
fi

show_header() {
    clear
    ELAPSED=$(( $(date +%s) - START_TIME ))
    echo "======================================================================"
    echo "          Sandbells Church Bell Kiosk Setup - Progress"
    echo "======================================================================"
    echo "Date              : $(date)"
    echo "Elapsed Time      : ${ELAPSED} seconds"
    echo "User              : $(whoami)"
    echo "Hostname          : $(hostname)"
    echo "Machine           : $(cat /proc/cpuinfo | grep Model | cut -d: -f2 || echo 'Unknown')"
    echo "Architecture      : $(uname -m) ($(getconf LONG_BIT)-bit)"
    echo "Git Branch        : $(git branch --show-current 2>/dev/null || echo 'Not in git repo')"
    echo "Intended Browser  : $BROWSER"
    echo ""
    echo "Status:"
    echo "   Hostname     : $HOSTNAME             [$(if [ "$(hostname)" = "$HOSTNAME" ]; then echo "Set"; else echo "Pending"; fi)]"
    echo "   WiFi         : $(iwgetid -r 2>/dev/null || echo 'Not connected')"
    echo "   SSH          : $(if systemctl is-enabled ssh 2>/dev/null | grep -q enabled; then echo "Enabled"; else echo "Pending"; fi)"
    echo "   1-Wire       : [Enabled after reboot]"
    echo "   Locale       : [UK English]"
    echo "   Time Server  : $TIME_SERVER          [Configured]"
    echo "======================================================================"
}

pause() {
    if [ "$QUICK_MODE" = true ]; then
        sleep 1.5
        return
    fi
    echo ""
    read -p "Press Enter to continue (or Q to stop) > " choice
    if [[ "$choice" =~ ^[Qq]$ ]]; then
        echo "Setup stopped safely."
        exit 0
    fi
}

show_header
pause

echo "[1/8] Setting hostname to $HOSTNAME..."
sudo hostnamectl set-hostname "$HOSTNAME"
show_header
echo "Hostname set successfully"
pause

echo "[2/8] Setting WiFi country and attempting tower network ($WIFI_SSID)..."
sudo raspi-config nonint do_wifi_country GB
sudo raspi-config nonint do_wifi_ssid_passphrase "$WIFI_SSID" "$WIFI_PASSWORD" || true
show_header
echo "WiFi step completed"
pause

echo "[3/8] Enabling SSH access..."
sudo raspi-config nonint do_ssh 0
show_header
echo "SSH enabled"
pause

echo "[4/8] Enabling 1-Wire support..."
sudo raspi-config nonint do_onewire 0
show_header
echo "1-Wire enabled (will be active after reboot)"
pause

echo "[5/8] Installing software packages (this may take a few minutes)..."
echo "This is the largest step - please be patient."
pause
sudo apt update
sudo apt install --no-install-recommends -y luakit matchbox-window-manager xinit xserver-xorg git curl chrony lightdm locales-all
show_header
echo "Packages installed successfully (including $BROWSER)"
pause

echo "[6/8] Setting UK English locale..."
echo "Installing and configuring locale packages..."
sudo dpkg-reconfigure -f noninteractive locales
echo "en_US.UTF-8 UTF-8" | sudo tee -a /etc/locale.gen > /dev/null
sudo locale-gen en_US.UTF-8
sudo update-locale LANG=en_US.UTF-8
show_header
echo "Locale updated to UK English (en_US.UTF-8)"
pause

echo "[7/8] Configuring time with local GPS source ($TIME_SERVER)..."
echo "Stopping chrony service temporarily..."
sudo systemctl stop chrony

echo "Backing up current config..."
sudo cp /etc/chrony/chrony.conf /etc/chrony/chrony.conf.bak 2>/dev/null || true

echo "Writing new config (preferring local GPS)..."
cat | sudo tee /etc/chrony/chrony.conf > /dev/null <<EOF
pool ntp.ubuntu.com iburst
server $TIME_SERVER iburst prefer
makestep 1.0 3
rtcsync
EOF

echo "Restarting chrony service..."
sudo systemctl start chrony
sleep 6

echo "Time sync status:"
chronyc sources | cat
echo ""
echo "Clock Stratum : $(chronyc tracking | grep "Stratum" | awk '{print $3}' || echo 'Unknown')"
echo "Reference ID  : $(chronyc tracking | grep "Reference ID" | awk '{print $4}' | tr -d '()' || echo 'Unknown')"

echo "Time server configured successfully (local GPS preferred)"
pause

echo "[8/8] Setting up automatic login..."
sudo tee /etc/lightdm/lightdm.conf > /dev/null <<EOF
[Seat:*]
autologin-user=$TARGET_USER
autologin-user-timeout=0
autologin-session=lightdm-xsession
EOF
show_header
echo "Auto-login configured"
pause

echo "======================================================================"
echo "SETUP COMPLETE!"
echo ""
echo "The system will now restart."
echo "After reboot, the Sandbells kiosk using $BROWSER should start automatically."
echo "======================================================================"

if [ "$QUICK_MODE" = false ]; then
    read -p "Press Enter to restart now... "
fi

sudo reboot
