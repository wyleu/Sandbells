#!/bin/bash
# ===============================================================
# Sandbells DEBUG INSTALLER
# File: install_debug.sh
# Purpose: Installs Sandbells in debug mode (runserver :8000)
# ===============================================================

set -e

SCRIPT_NAME=$(basename "$0")

echo "=================================================="
echo "     Sandbells DEBUG Kiosk Installer"
echo "     Script: $SCRIPT_NAME"
echo "     Mode  : Development Server (runserver :8000)"
echo "=================================================="

PROJECT_DIR="/opt/sandbells"
USER="sandbells"
VENV_DIR="$PROJECT_DIR/Bellvirtenv"

# Update system
echo "[1/5] Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install dependencies
echo "[2/5] Installing dependencies..."
sudo apt install -y python3-pip python3-venv luakit xserver-xorg xinit unclutter \
                    matchbox-window-manager

# Create dedicated user
if ! id "$USER" &>/dev/null; then
    echo "[3/5] Creating dedicated user '$USER'..."
    sudo useradd -m -s /bin/bash $USER
    echo "$USER ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/$USER
fi

# Setup project files
echo "[4/5] Setting up project in $PROJECT_DIR..."
sudo mkdir -p $PROJECT_DIR
sudo chown $USER:$USER $PROJECT_DIR

if [ ! -d "$PROJECT_DIR/changes" ]; then
    echo "Copying project files..."
    sudo cp -r . $PROJECT_DIR/
    sudo chown -R $USER:$USER $PROJECT_DIR
fi

cd $PROJECT_DIR

# Virtual environment
echo "[5/5] Setting up Python virtual environment..."
sudo rm -rf $VENV_DIR
sudo -u $USER python3 -m venv $VENV_DIR

# Install packages as the correct user
echo "Installing Python packages..."
sudo -u $USER $VENV_DIR/bin/pip install --upgrade pip
sudo -u $USER $VENV_DIR/bin/pip install -r requirements.txt

echo "=================================================="
echo "DEBUG INSTALLATION SUCCESSFUL"
echo ""
echo "To manually start the debug server:"
echo "   cd $PROJECT_DIR"
echo "   sudo -u $USER $VENV_DIR/bin/python changes/manage.py runserver 0.0.0.0:8000"
echo ""
echo "Next step: We can add LuaKit full-screen autostart."
echo "=================================================="
