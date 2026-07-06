#!/bin/bash
# ===============================================================
# Sandbells Kiosk Installer - Using venv activate
# ===============================================================
set -e

VERBOSE=false
if [[ "$1" == "-v" || "$1" == "--verbose" ]]; then
    VERBOSE=true
fi

ORIGINAL_DIR="$(pwd)"

echo "=================================================="
echo " Sandbells Kiosk Installer"
echo "=================================================="

# CONFIG
TARGET_USER="${SANDBELLS_USER:-sandbells}"
PROJECT_DIR="/opt/sandbells"
VENV_DIR="$PROJECT_DIR/Bellvirtenv"

log() { echo "[INSTALL] $*"; }
vlog() { if $VERBOSE; then echo "[DETAIL] $*"; fi; }

log "Running from: $ORIGINAL_DIR"
log "Target user: $TARGET_USER"

# Git conflict check
log "Checking for Git conflicts..."
if grep -rq "<<<<<<<" . --include="requirements.txt" --include="*.py" 2>/dev/null; then
    echo "ERROR: Git conflict markers found!"
    exit 1
fi

# System updates
log "[1/7] Updating system packages..."
sudo apt update -qq && sudo apt upgrade -y

# Dependencies
log "[2/7] Installing dependencies..."
sudo apt install -y nginx gunicorn python3-pip python3-venv \
                    luakit xserver-xorg xinit unclutter matchbox-window-manager
                    libjpeg-dev zlib1g-dev
# Create user
if ! id "$TARGET_USER" &>/dev/null; then
    log "[3/7] Creating user $TARGET_USER..."
    sudo useradd -m -s /bin/bash "$TARGET_USER"
    echo "$TARGET_USER ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/$TARGET_USER
fi

# Project dir
log "[4/7] Setting up project directory..."
sudo mkdir -p $PROJECT_DIR
sudo chown $TARGET_USER:$TARGET_USER $PROJECT_DIR

# Copy files
log "[5/7] Copying project files..."
sudo rsync -a --exclude='.git' --exclude='Bellvirtenv' \
            --exclude='__pycache__' --exclude='*.pyc' \
            "$ORIGINAL_DIR/" "$PROJECT_DIR/"
sudo chown -R $TARGET_USER:$TARGET_USER $PROJECT_DIR

# Go to project dir for venv work
cd $PROJECT_DIR

# Virtual environment + Django
log "[6/7] Setting up Python virtual environment..."
sudo -u $TARGET_USER python3 -m venv $VENV_DIR

log "Installing requirements..."
sudo -u $TARGET_USER bash -c "
    source $VENV_DIR/bin/activate
    pip install -r requirements.txt
"

log "[7/7] Running Django setup..."
sudo -u $TARGET_USER bash -c "
    source $VENV_DIR/bin/activate
    python changes/manage.py migrate || true
    # Prepare static dir
    mkdir -p /var/www/html/static
    chown -R $TARGET_USER:www-data /var/www/html/static
    chmod -R 775 /var/www/html/static
    # Collect static
    python changes/manage.py collectstatic --noinput --clear || true
    # Final permissions
    chown -R www-data:www-data /var/www/html/static
    chmod -R 755 /var/www/html/static
"

# Return to original directory
cd "$ORIGINAL_DIR"

echo "=================================================="
echo "Installation completed successfully!"
echo "You are back in: $(pwd)"
echo "Next step: sudo reboot"
echo "=================================================="
