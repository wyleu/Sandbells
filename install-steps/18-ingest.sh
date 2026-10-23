#!/bin/bash
# 18-ingest.sh
# Install + enable sandbells-ingest.service (sand.event/v1 from the
# concentrator /ws into the Django DB).  Step 12 has already installed
# requirements.txt (websocket-client) and migrated; this re-checks both
# cheaply so the step can also be run on its own.
# Args: $1 = QUICK_MODE
# master_install auto-runs [0-9][0-9]-*.sh — no master_install edit needed.

QUICK_MODE=${1:-false}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck source=/dev/null
[ -f "$SCRIPT_DIR/sandbells-common.sh" ] && source "$SCRIPT_DIR/sandbells-common.sh"

PROJECT_DIR="/home/sandbells/Code/Sandbells"
VENV_PY="${PROJECT_DIR}/Bellvirtenv/bin/python"
VENV_PIP="${PROJECT_DIR}/Bellvirtenv/bin/pip"
CHANGES_DIR="${PROJECT_DIR}/changes"
REQUIREMENTS="${PROJECT_DIR}/requirements.txt"
UNIT_SRC="$REPO_DIR/systemd/sandbells-ingest.service"
UNIT_DST="/etc/systemd/system/sandbells-ingest.service"
RUN_AS="sandbells"

if ! type pause &>/dev/null; then
  pause() {
    [ "$QUICK_MODE" = true ] && { sleep 1.5; return; }
    echo ""; read -r -p "Press Enter to continue (or Q to stop) > " choice
    [[ "$choice" =~ ^[Qq]$ ]] && { echo "Setup stopped safely."; exit 1; }
  }
fi

as_app() {
  if [ "$(id -un)" = "$RUN_AS" ]; then "$@"; else sudo -u "$RUN_AS" "$@"; fi
}

echo "=================================================="
echo " 18 – Event ingest service"
echo "=================================================="

[ -f "$UNIT_SRC" ] || { echo "ERROR: missing $UNIT_SRC"; exit 1; }
[ -x "$VENV_PY" ] || { echo "ERROR: no venv at $VENV_PY (run step 12 first)"; exit 1; }

# ------------------------------------------------------------------
# 1. websocket-client in the venv (from requirements.txt)
# ------------------------------------------------------------------
echo "[1/3] Checking websocket-client in the venv..."
if as_app "$VENV_PY" -c "import websocket" 2>/dev/null; then
  echo "  already installed: websocket-client"
else
  echo "  missing — pip install -r requirements.txt"
  as_app "$VENV_PIP" install -r "$REQUIREMENTS" || { echo "ERROR: pip failed"; exit 1; }
fi

# ------------------------------------------------------------------
# 2. Migrations (events tables) + static files (farm_status.js heartbeat)
# ------------------------------------------------------------------
echo "[2/3] Checking migrations..."
cd "$CHANGES_DIR" || { echo "ERROR: $CHANGES_DIR missing"; exit 1; }
if as_app "$VENV_PY" manage.py migrate --check >/dev/null 2>&1; then
  echo "  migrations up to date"
else
  as_app "$VENV_PY" manage.py migrate --noinput || { echo "ERROR: migrate failed"; exit 1; }
fi
as_app "$VENV_PY" manage.py collectstatic --noinput >/dev/null \
  && echo "  static files collected" || echo "  WARNING: collectstatic failed"
pause

# ------------------------------------------------------------------
# 3. systemd unit
# ------------------------------------------------------------------
echo "[3/3] Installing sandbells-ingest.service..."
CHANGED=false
if sudo cmp -s "$UNIT_SRC" "$UNIT_DST"; then
  echo "  unchanged: $UNIT_DST"
else
  sudo install -m 644 "$UNIT_SRC" "$UNIT_DST"
  echo "  installed $UNIT_DST"
  CHANGED=true
fi
sudo systemctl daemon-reload
sudo systemctl enable --now sandbells-ingest.service
if [ "$CHANGED" = true ]; then
  sudo systemctl restart sandbells-ingest.service
fi

sleep 3
echo ""
systemctl is-enabled sandbells-ingest.service || true
systemctl is-active sandbells-ingest.service || true
# page 3 link widget reads this (tmpfs, RuntimeDirectory of the unit)
if [ -f /run/sandbells-ingest/link.json ]; then
  echo "  link state: /run/sandbells-ingest/link.json"
else
  echo "  WARNING: no /run/sandbells-ingest/link.json yet (page 3 shows INGEST DOWN)"
fi
journalctl -u sandbells-ingest.service -n 5 --no-pager 2>/dev/null || true
echo "Ingest step completed"
echo "  Follow: journalctl -u sandbells-ingest -f"
pause
