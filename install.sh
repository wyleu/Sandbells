#!/bin/bash
# ===============================================================
# Sandbells Kiosk Installer
# ===============================================================
set -e

VERBOSE=false
if [[ "$1" == "-v" || "$1" == "--verbose" ]]; then
    VERBOSE=true
fi

echo "=================================================="
echo " Sandbells Kiosk Installer"
echo "=================================================="

# CONFIG
TARGET_USER="${SANDBELLS_USER:-sandbells}"
PROJECT_DIR="/opt/sandbells"
VENV_DIR="$PROJECT_DIR/Bellvirtenv"

log() { echo "[INSTALL] $*"; }
vlog() { if $VERBOSE; then echo "[DETAIL] $*"; fi; }

log "Running as: $(whoami) | Target user: $TARGET_USER"

# Git conflict check
log "Checking for Git conflicts..."
if grep -rq "<<<<<<<" . --include="requirements.txt" --include="*.py" 2>/dev/null; then
    echo "ERROR: Git conflict markers found!"
    exit 1
fi
vlog "No conflict markers found."

# Update system
log "[1/7] Updating system packages..."
sudo apt update -qq && sudo apt upgrade -y

# Dependencies
log "[2/7] Installing dependencies..."
sudo apt install -y nginx gunicorn python3-pip python3-venv \
                    luakit xserver-xorg xinit unclutter matchbox-window-manager

# Create user if needed
if ! id "$TARGET_USER" &>/dev/null; then
    log "[3/7] Creating user $TARGET_USER..."
    sudo useradd -m -s /bin/bash "$TARGET_USER"
    echo "$TARGET_USER ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/$TARGET_USER
else
    log "[3/7] User $TARGET_USER already exists."
fi

# Project directory
log "[4/7] Setting up project directory..."
sudo mkdir -p $PROJECT_DIR
sudo chown $TARGET_USER:$TARGET_USER $PROJECT_DIR

# Copy files
log "[5/7] Copying project files (clean rsync)..."
sudo rsync -a --exclude='.git' --exclude='Bellvirtenv' \
            --exclude='__pycache__' --exclude='*.pyc' \
            ./ "$PROJECT_DIR/"
sudo chown -R $TARGET_USER:$TARGET_USER $PROJECT_DIR
vlog "Files copied to $PROJECT_DIR"

cd $PROJECT_DIR

# Virtual environment
log "[6/7] Setting up Python venv..."
sudo -u $TARGET_USER python3 -m venv $VENV_DIR
vlog "Venv created at $VENV_DIR"

log "Installing Python packages..."
sudo -u $TARGET_USER $VENV_DIR/bin/pip install -r requirements.txt

# Django
log "[7/7] Running Django setup..."
sudo -u $TARGET_USER $VENV_DIR/bin/python changes/manage.py collectstatic --noinput --clear || true
sudo -u $TARGET_USER $VENV_DIR/bin/python changes/manage.py migrate || true

echo "=================================================="
echo "Installation completed successfully!"
echo "Run with -v for verbose output."
echo "Next: sudo reboot"
echo "=================================================="