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
#   - copy changed systemd/ unit files into /etc/systemd/system
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
# Unit files: sandbells_sync_units.sh runs first, so the restarts below use
# the repo's systemd/ units.  It restarts other changed, active units itself
# (e.g. sandbells-ingest) but leaves $RESTART_UNITS to the restart here, so
# nothing is restarted twice.
#
# Needs sudo for systemctl. Does not pull git, migrate, or reboot.
# =============================================================================

set -euo pipefail

ROOT="${SANDBELLS_ROOT:-${HOME}/Code/Sandbells}"
APP="${SANDBELLS_APP:-${ROOT}/changes}"
VENV="${SANDBELLS_VENV:-${ROOT}/Bellvirtenv}"
PY="${VENV}/bin/python"
SYNC_UNITS="${ROOT}/sandbells_sync_units.sh"
RESTART_UNITS="nginx gunicorn sandbells-kiosk"
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

log "sync systemd units"
SANDBELLS_ROOT="$ROOT" "$SYNC_UNITS" --skip-restart "$RESTART_UNITS"

log "restart $RESTART_UNITS"
# shellcheck disable=SC2086  # a list of unit names
sudo systemctl restart $RESTART_UNITS

log "status"
# shellcheck disable=SC2086
systemctl is-active $RESTART_UNITS | paste -sd' ' -
log "done"
