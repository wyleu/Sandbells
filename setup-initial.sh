#!/bin/bash
# Sandbells Initial Setup & Diagnostics - Full cold start
set -e

echo "=================================================="
echo "Sandbells Initial Setup & Diagnostics"
echo "=================================================="
echo "Config: Hostname=sandbells | Time Server=sandgps3.local | Auto-login enabled"
echo "Date: $(date)"
echo ""

echo "[1/5] Hostname..."
sudo hostnamectl set-hostname sandbells

echo "[2/5] WiFi + Country..."
sudo raspi-config nonint do_wifi_ssid_passphrase sandbells Sandbells
sudo raspi-config nonint do_wifi_country GB

echo "[3/5] SSH..."
sudo raspi-config nonint do_ssh 0

echo "[4/5] 1-Wire..."
sudo raspi-config nonint do_onewire 0

echo "[5/5] Packages + Time + Locale + Auto-login..."
sudo apt update
sudo apt install --no-install-recommends -y luakit matchbox-window-manager xinit xserver-xorg git curl chrony lightdm locales-all

# Locale
sudo dpkg-reconfigure -f noninteractive locales
echo "en_US.UTF-8 UTF-8" | sudo tee -a /etc/locale.gen > /dev/null
sudo locale-gen en_US.UTF-8
sudo update-locale LANG=en_US.UTF-8

# Time server
sudo cp /etc/chrony/chrony.conf /etc/chrony/chrony.conf.bak 2>/dev/null || true
cat | sudo tee /etc/chrony/chrony.conf > /dev/null <<EOF
pool ntp.ubuntu.com iburst
server sandgps3.local iburst prefer
makestep 1.0 3
rtcsync
EOF
sudo systemctl restart chrony

# Auto-login
sudo tee /etc/lightdm/lightdm.conf > /dev/null <<EOF
[Seat:*]
autologin-user=sandbells
autologin-user-timeout=0
autologin-session=lightdm-xsession
EOF

echo ""
echo "Time sources:"
chronyc sources | head -8
echo ""
echo "Setup complete! Rebooting..."
sleep 5
sudo reboot
