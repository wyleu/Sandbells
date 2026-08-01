#!/bin/bash
# 12-django-venv.sh
# Sandbells Install Step – Django virtualenv, requirements, migrate, collectstatic
#
# Args: $1 = QUICK_MODE (true/false)

QUICK_MODE=${1:-false}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/sandbells-common.sh"

echo "=================================================="
echo " 12 – Django Virtualenv + Static Files"
echo "=================================================="

PROJECT_DIR="/home/sandbells/Code/Sandbells"
VENV_DIR="${PROJECT_DIR}/Bellvirtenv"
CHANGES_DIR="${PROJECT_DIR}/changes"
STATIC_DEST="/var/www/sandbells/static"
LOG_DIR="/var/log/django"

# ------------------------------------------------------------------
# 0. Ensure log directory exists (prevents PermissionError in settings.py)
# ------------------------------------------------------------------
echo "[0/6] Ensuring log directory $LOG_DIR ..."
sudo mkdir -p "$LOG_DIR"
sudo chown sandbells:sandbells "$LOG_DIR"
sudo chmod 755 "$LOG_DIR"

cd "$PROJECT_DIR" || { echo "ERROR: $PROJECT_DIR not found"; exit 1; }

# ------------------------------------------------------------------
# 1. System packages needed for building Python wheels
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
# 4. Django migrations + fixtures
# ------------------------------------------------------------------
echo "[4/6] Running Django migrations..."
cd "$CHANGES_DIR" || { echo "ERROR: changes/ directory missing"; exit 1; }

python manage.py migrate --noinput || {
    echo "WARNING: migrate failed (DB may not be ready yet). Continuing..."
}

echo "Loading canonical fixtures (towers + patterns)..."
python manage.py loaddata bells/fixtures/towers.json 2>/dev/null || \
    echo "WARNING: towers.json not loaded (already present or missing)"
python manage.py loaddata bells/fixtures/patterns.json 2>/dev/null || \
    echo "WARNING: patterns.json not loaded (already present or missing)"
pause

# ------------------------------------------------------------------
# 5. Collect static files
# ------------------------------------------------------------------
echo "[5/6] Collecting static files → $STATIC_DEST ..."
sudo mkdir -p "$STATIC_DEST"
sudo chown -R sandbells:sandbells /var/www/sandbells

python manage.py collectstatic --noinput --clear 2>/dev/null || \
    python manage.py collectstatic --noinput --clear

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
# 6. Sanity check
# ------------------------------------------------------------------
echo "[6/6] Sanity check..."
python -c "import django; print('Django', django.get_version())"
python -c "import gunicorn; print('Gunicorn OK')"
deactivate

echo ""
echo "Django virtualenv + static files COMPLETE."
echo "Venv: $VENV_DIR"
echo "Static: $STATIC_DEST"
echo "Logs: $LOG_DIR"
pause
