#!/bin/bash
echo "=== Sandbells Health Check ==="
echo "Date: $(date)"
echo "Hostname: $(hostname)"
echo "Uptime: $(uptime)"
echo ""

echo "=== Hardware ==="
echo "Architecture: $(uname -m)"
echo "CPU Cores: $(nproc)"
echo "Memory:"
free -h
echo "Swap:"
swapon --show
echo ""

echo "=== Services ==="
echo "Gunicorn:"
systemctl status sandbells --no-pager -l | grep -E "Active|ExecStart|workers"
echo ""
echo "Luakit Kiosk:"
systemctl status luakit-kiosk.service --no-pager -l | grep -E "Active|ExecStart"
echo ""

echo "=== Django Environment ==="
echo "Settings DEBUG mode: $(grep DEBUG /opt/sandbells/changes/changes/settings.py 2>/dev/null || echo 'Not found')"
echo "Running from: $(pwd)"
echo ""

echo "=== Processes ==="
ps aux | grep -E "gunicorn|luakit|WebKit" | grep -v grep
echo ""

echo "=== Git Status ==="
cd /home/wyleu/Code/Sandbells 2>/dev/null && git status --short || echo "Not a git repo or not in directory"
