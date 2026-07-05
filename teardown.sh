#!/bin/bash
# ===============================================================
# Sandbells Teardown Script
# File: teardown.sh
# Purpose: Clean up Sandbells installation for testing/reinstall
# ===============================================================

echo "=================================================="
echo "     Sandbells Teardown"
echo "     This will remove services and files"
echo "=================================================="

read -p "Are you sure you want to teardown? (y/N): " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

PROJECT_DIR="/opt/sandbells"
USER="sandbells"

echo "Stopping services..."
sudo systemctl stop sandbells.service 2>/dev/null || true
sudo systemctl stop nginx 2>/dev/null || true

echo "Disabling services..."
sudo systemctl disable sandbells.service 2>/dev/null || true

echo "Removing systemd services..."
sudo rm -f /etc/systemd/system/sandbells.service

echo "Removing Nginx config..."
sudo rm -f /etc/nginx/sites-enabled/sandbells
sudo rm -f /etc/nginx/sites-available/sandbells

echo "Removing project files..."
sudo rm -rf $PROJECT_DIR

# echo "Removing user..."
# sudo userdel -r $USER 2>/dev/null || true
# sudo rm -f /etc/sudoers.d/$USER

echo "Reloading systemd..."
sudo systemctl daemon-reload

echo "=================================================="
echo "Teardown completed."
echo "You can now run install_debug.sh again."
echo "=================================================="
