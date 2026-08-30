#!/bin/bash
# =============================================================================
# sandbells_reset.sh
#
# Generic Sandbells helper: refresh Django static files and bounce the
# production stack so the HDMI kiosk is looking at what is on disk.
#
# Why it exists
# -------------
# After editing CSS/JS/templates you otherwise have to remember:
#   - which directory holds manage.py
#   - which virtualenv to use
#   - collectstatic --noinput
#   - restart nginx, gunicorn, and the Luakit kiosk
# This script does that in one go from any cwd.
#
# Layout it assumes (override with env if yours differs)
# ------------------------------------------------------
#   $SANDBELLS_ROOT     default: $HOME/Code/Sandbells
#   $SANDBELLS_APP      default: $SANDBELLS_ROOT/changes   (manage.py lives here)
#   $SANDBELLS_VENV     default: $SANDBELLS_ROOT/Bellvirtenv
#
# Usage
# -----
#   ./sandbells_reset.sh
#   SANDBELLS_ROOT=/other/path ./sandbells_reset.sh
#
# Needs sudo for systemctl. Does not pull git, migrate, or reboot.
# =============================================================================

set -euo pipefail

ROOT="${SANDBELLS_ROOT:-${HOME}/Code/Sandbells}"
APP="${SANDBELLS_APP:-${ROOT}/changes}"
VENV="${SANDBELLS_VENV:-${ROOT}/Bellvirtenv}"
PY="${VENV}/bin/python"
LOGTAG="sandbells-reset"

log() { echo "[$LOGTAG] $*"; }

if [ ! -x "$PY" ]; then
    log "ERROR: venv python not found: $PY"
    exit 1
fi
if [ ! -f "${APP}/manage.py" ]; then
    log "ERROR: manage.py not found in $APP"
    exit 1
fi

log "git status"
if git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "$ROOT" status -sb
    git -C "$ROOT" log -1 --oneline
else
    log "not a git repo: $ROOT"
fi


log "root=$ROOT"
log "app=$APP"
log "venv=$VENV"

log "collectstatic"
cd "$APP"
"$PY" manage.py collectstatic --noinput

log "restart nginx gunicorn sandbells-kiosk"
sudo systemctl restart nginx gunicorn sandbells-kiosk

log "status"
systemctl is-active nginx gunicorn sandbells-kiosk | paste -sd' ' -
log "done"
