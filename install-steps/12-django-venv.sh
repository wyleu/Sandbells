#!/bin/bash
# 12-django-venv.sh
# Sandbells Install Step – Django virtualenv, requirements, migrate, collectstatic
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
echo " 12 – Django Virtualenv + Static Files"
echo "=================================================="

PROJECT_DIR="/home/sandbells/Code/Sandbells"
VENV_DIR="${PROJECT_DIR}/Bellvirtenv"
CHANGES_DIR="${PROJECT_DIR}/changes"
STATIC_DEST="/var/www/sandbells/static"

# Ensure we are the right user / ownership
if [ "$(id -un)" != "sandbells" ] && [ "$(id -un)" != "root" ]; then
    echo "WARNING: Running as $(id -un). Prefer sandbells or root."
fi

cd "$PROJECT_DIR" || { echo "ERROR: $PROJECT_DIR not found"; exit 1; }

# ------------------------------------------------------------------
# 1. System packages needed for building Python wheels on Pi
# ------------------------------------------------------------------
echo "[1/6] Installing Python build dependencies..."
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    python3-venv python3-pip python3-dev \
    libpq-dev build-essential libjpeg-dev zlib1g-dev \
    libffi-dev libssl-dev

pause

# ------------------------------------------------------------------
# 2. Create / update virtualenv
# ------------------------------------------------------------------
echo "[2/6] Creating virtualenv at $VENV_DIR ..."
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo "Virtualenv created."
else
    echo "Virtualenv already exists – will upgrade packages."
fi

# Make sure ownership is correct
sudo chown -R sandbells:sandbells "$VENV_DIR"

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

pip install --upgrade pip setuptools wheel

pause

# ------------------------------------------------------------------
# 3. Install Python requirements
# ------------------------------------------------------------------
echo "[3/6] Installing Python requirements..."
if [ -f "${PROJECT_DIR}/requirements.txt" ]; then
    pip install -r "${PROJECT_DIR}/requirements.txt"
else
    echo "WARNING: requirements.txt not found – installing minimal set"
    pip install django gunicorn psycopg2-binary whitenoise pillow
fi

pause

# ------------------------------------------------------------------
# 4. Django migrations
# ------------------------------------------------------------------
echo "[4/6] Running Django migrations..."
cd "$CHANGES_DIR" || { echo "ERROR: changes/ directory missing"; exit 1; }

# Prefer the project settings; fall back gracefully
python manage.py migrate --noinput || {
    echo "WARNING: migrate failed (DB may not be ready yet). Continuing..."
}

pause

# ------------------------------------------------------------------
# 5. Collect static files
# ------------------------------------------------------------------
echo "[5/6] Collecting static files → $STATIC_DEST ..."
sudo mkdir -p "$STATIC_DEST"
sudo chown -R sandbells:sandbells /var/www/sandbells

# Clear + collect
python manage.py collectstatic --noinput --clear \
    --settings=changes.settings 2>/dev/null || \
python manage.py collectstatic --noinput --clear

# Also copy into the nginx alias location if different
if [ -d "${CHANGES_DIR}/bells/static" ]; then
    sudo cp -a "${CHANGES_DIR}/bells/static/." "$STATIC_DEST/" 2>/dev/null || true
fi
if [ -d "${CHANGES_DIR}/staticfiles" ]; then
    sudo cp -a "${CHANGES_DIR}/staticfiles/." "$STATIC_DEST/" 2>/dev/null || true
fi

sudo chown -R sandbells:sandbells /var/www/sandbells
echo "Static files ready at $STATIC_DEST"
ls -la "$STATIC_DEST" | head -20

pause

# ------------------------------------------------------------------
# 6. Quick sanity check
# ------------------------------------------------------------------
echo "[6/6] Sanity check..."
python -c "import django; print('Django', django.get_version())"
python -c "import gunicorn; print('Gunicorn OK')"
deactivate

echo ""
echo "Django virtualenv + static files COMPLETE."
echo "Venv: $VENV_DIR"
echo "Static: $STATIC_DEST"
pause
