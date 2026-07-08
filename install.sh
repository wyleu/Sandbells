#!/bin/bash
# Sandbells Kiosk Installer
echo "=================================================="
echo " Sandbells Kiosk Installer"
echo "=================================================="

echo "User       : $(whoami)"
echo "Directory  : $(pwd)"
if git rev-parse --is-inside-work-tree &>/dev/null; then
    echo "Git branch : $(git branch --show-current)"
    echo "Git status : $(git status --porcelain | wc -l) uncommitted changes"
else
    echo "Git        : Not a git repository"
fi
echo "=================================================="

set -e
ORIGINAL_DIR="$(pwd)"

TARGET_USER="sandbells"
PROJECT_DIR="/opt/sandbells"
VENV_DIR="$PROJECT_DIR/Bellvirtenv"

# User
if ! id "$TARGET_USER" &>/dev/null; then
    sudo useradd -m -s /bin/bash "$TARGET_USER"
    echo "$TARGET_USER ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/$TARGET_USER
fi

sudo mkdir -p $PROJECT_DIR
sudo chown $TARGET_USER:$TARGET_USER $PROJECT_DIR

# Copy
sudo rsync -a --exclude='.git' --exclude='Bellvirtenv' --exclude='__pycache__' "$ORIGINAL_DIR/" "$PROJECT_DIR/"
sudo chown -R $TARGET_USER:$TARGET_USER $PROJECT_DIR

cd $PROJECT_DIR

# Venv + Packages + DB + Static
sudo rm -rf $VENV_DIR
sudo -u $TARGET_USER python3 -m venv $VENV_DIR

sudo -u $TARGET_USER bash -c "
    source $VENV_DIR/bin/activate
    pip install -r requirements.txt
    python changes/manage.py migrate
    python changes/manage.py loaddata fixtures/initial_data.json || true
"

# Static files
sudo rm -rf /var/www/html/static
sudo mkdir -p /var/www/html/static
sudo chown -R $TARGET_USER:www-data /var/www/html/static
sudo chmod -R 775 /var/www/html/static

sudo -u $TARGET_USER bash -c "
    source $VENV_DIR/bin/activate
    python changes/manage.py collectstatic --noinput --clear || true
"

sudo chown -R www-data:www-data /var/www/html/static
sudo chmod -R 755 /var/www/html/static

cd "$ORIGINAL_DIR"

echo "Installation completed successfully."
