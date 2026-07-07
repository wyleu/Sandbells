#!/bin/bash
# Sandbells Teardown
echo "=================================================="
echo " Sandbells Teardown"
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

read -p "Are you sure you want to teardown? (y/N): " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

sudo rm -rf /opt/sandbells
sudo rm -f /etc/systemd/system/sandbells.service
sudo rm -f /etc/nginx/sites-enabled/sandbells
sudo rm -f /etc/nginx/sites-available/sandbells

sudo systemctl daemon-reload 2>/dev/null || true

echo "Teardown completed."
