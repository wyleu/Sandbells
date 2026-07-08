#!/bin/bash
# Sandbells Full Production Installer
VERBOSE=false
if [ "$1" = "-v" ] || [ "$1" = "--verbose" ]; then
    VERBOSE=true
    set -x
fi

echo "=================================================="
echo " Sandbells Kiosk Installer (Production)"
echo "=================================================="
echo "User : $(whoami)"
echo "Directory : $(pwd)"
if git rev-parse --is-inside-work-tree &>/dev/null; then
    echo "Git branch : $(git branch --show-current)"
    echo "Git status : $(git status --porcelain | wc -l) uncommitted changes"
else
    echo "Git : Not a git repository"
fi
echo "=================================================="

set -e
ORIGINAL_DIR="$(pwd)"
TARGET_USER="sandbells"
PROJECT_DIR="/opt/sandbells"
VENV_DIR="$PROJECT_DIR/Bellvirtenv"
CHANGES_DIR="$PROJECT_DIR/changes"

if [ "$VERBOSE" = true ]; then
    echo "[VERBOSE] Starting installation..."
fi

# Create user
if ! id "$TARGET_USER" &>/dev/null; then
    sudo useradd -m -s /bin/bash "$TARGET_USER"
    echo "$TARGET_USER ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/$TARGET_USER
    echo "Created user $TARGET_USER"
fi

sudo mkdir -p $PROJECT_DIR
sudo chown $TARGET_USER:$TARGET_USER $PROJECT_DIR

# Copy code
sudo rsync -a --exclude='.git' --exclude='Bellvirtenv' --exclude='__pycache__' "$ORIGINAL_DIR/" "$PROJECT_DIR/"
sudo chown -R $TARGET_USER:$TARGET_USER $PROJECT_DIR
echo "Code copied to $PROJECT_DIR"

cd $PROJECT_DIR

# Venv + Dependencies
sudo rm -rf $VENV_DIR
sudo -u $TARGET_USER python3 -m venv $VENV_DIR
sudo -u $TARGET_USER bash -c "
    source $VENV_DIR/bin/activate
    pip install --upgrade pip
    pip install -r requirements_pi3.txt || pip install -r requirements.txt
    cd $CHANGES_DIR
    python manage.py migrate
    python manage.py collectstatic --noinput --clear || true
    python manage.py loaddata /opt/sandbells/fixtures/initial_data.json || true
    python manage.py loaddata fixtures/initial_data.json || true
"
echo "Virtualenv and dependencies installed"

# Gunicorn Service
sudo tee /etc/systemd/system/sandbells.service > /dev/null <<EOT
[Unit]
Description=Sandbells Django Gunicorn
After=network.target

[Service]
User=$TARGET_USER
Group=www-data
WorkingDirectory=$CHANGES_DIR
Environment="PATH=$VENV_DIR/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=$VENV_DIR/bin/gunicorn --workers 3 --bind 0.0.0.0:8000 changes.wsgi:application

[Install]
WantedBy=multi-user.target
EOT

sudo systemctl daemon-reload
sudo systemctl enable --now sandbells.service
echo "Gunicorn service installed and started"

# Nginx
sudo tee /etc/nginx/sites-available/sandbells > /dev/null <<EOT
server {
    listen 80;
    server_name sandbells.local;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    location /static/ {
        alias $CHANGES_DIR/static/;
    }
}
EOT

sudo ln -sf /etc/nginx/sites-available/sandbells /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx
echo "Nginx configured and restarted"

cd "$ORIGINAL_DIR"
echo "=================================================="
echo "Installation completed successfully."
echo "Access at http://sandbells.local"
if [ "$VERBOSE" = true ]; then
    echo "[VERBOSE] Full verbose mode completed."
fi
