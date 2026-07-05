#!/bin/bash
# ===============================================================
# Sandbells Teardown Script
# ===============================================================
set -e

VERBOSE=false
if [[ "$1" == "-v" || "$1" == "--verbose" ]]; then
    VERBOSE=true
fi

echo "=================================================="
echo " Sandbells Teardown"
echo "=================================================="

read -p "Are you sure you want to teardown? (y/N): " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

PROJECT_DIR="/opt/sandbells"
USER="sandbells"

log() { echo "[TEARDOWN] $*"; }
vlog() { if $VERBOSE; then echo "[DETAIL] $*"; fi; }

log "Stopping services..."
sudo systemctl stop sandbells.service 2>/dev/null || true
sudo systemctl stop nginx 2>/dev/null || true
sudo pkill -f gunicorn 2>/dev/null || true
sudo pkill -f luakit 2>/dev/null || true

log "Disabling and removing services..."
sudo systemctl disable sandbells.service 2>/dev/null || true
sudo rm -f /etc/systemd/system/sandbells.service
sudo rm -f /etc/nginx/sites-enabled/sandbells
sudo rm -f /etc/nginx/sites-available/sandbells

log "Removing project files..."
sudo rm -rf $PROJECT_DIR
vlog "Project directory removed: $PROJECT_DIR"

log "Reloading systemd..."
sudo systemctl daemon-reload

echo "=================================================="
echo "Teardown completed successfully."
echo "Run with -v for more details next time."
echo "=================================================="
