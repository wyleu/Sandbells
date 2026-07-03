#!/bin/bash
# Sandbells Kiosk Installer - One command setup
# Run as: bash install.sh

set -e  # Exit on any error

echo "=================================================="
echo "     Sandbells Kiosk Installer"
echo "=================================================="

PROJECT_DIR="/opt/sandbells"
USER="sandbells"
VENV_DIR="$PROJECT_DIR/Bellvirtenv"

# Update system
echo "[1/6] Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install dependencies
echo "[2/6] Installing dependencies..."
sudo apt install -y nginx gunicorn python3-pip python3-venv \
                    luakit xserver-xorg xinit unclutter \
                    matchbox-window-manager

# Create dedicated user
if ! id "$USER" &>/dev/null; then
    echo "[3/6] Creating dedicated user '$USER'..."
    sudo useradd -m -s /bin/bash $USER
    echo "$USER ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/$USER
fi

# Setup project directory
echo "[4/6] Setting up project directory..."
sudo mkdir -p $PROJECT_DIR
sudo chown $USER:$USER $PROJECT_DIR

# Copy or clone project (if not already there)
if [ ! -d "$PROJECT_DIR/changes" ]; then
    echo "Copying project files..."
    sudo cp -r . $PROJECT_DIR/
    sudo chown -R $USER:$USER $PROJECT_DIR
fi

cd $PROJECT_DIR

# Virtual environment
echo "[5/6] Setting up Python virtual environment..."
sudo -u $USER python3 -m venv $VENV_DIR
sudo -u $USER $VENV_DIR/bin/pip install -r requirements.txt

# Django setup
echo "Running Django collectstatic and migrations..."
sudo -u $USER $VENV_DIR/bin/python changes/manage.py collectstatic --noinput --clear || true
sudo -u $USER $VENV_DIR/bin/python changes/manage.py migrate || true

# TODO: Add nginx, gunicorn, luakit setup here in next iteration

echo "=================================================="
echo "Installation completed successfully!"
echo "Next steps:"
echo "1. Review and edit config files in $PROJECT_DIR/config/"
echo "2. Run: sudo reboot"
echo "=================================================="
