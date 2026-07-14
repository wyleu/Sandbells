#!/bin/bash
# Sandbells Health Check Script - Enhanced for Bellvirtenv, git details, empty outputs

echo "=== Sandbells Health Check (sandbells_health.sh) ==="
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

echo "=== Virtual Environment ==="
if [ -f "Bellvirtenv/bin/activate" ]; then
  if [[ -z "$VIRTUAL_ENV" ]]; then
    echo "Activating Bellvirtenv (always-on policy)..."
    source Bellvirtenv/bin/activate
    echo "Bellvirtenv activated: $VIRTUAL_ENV"
  else
    echo "Bellvirtenv already active: $VIRTUAL_ENV"
  fi
else
  echo "No Bellvirtenv found in current dir."
fi
echo ""

echo "=== Services ==="
echo "Gunicorn:"
systemctl status sandbells --no-pager -l 2>&1 | grep -E "Active|ExecStart|workers|Loaded" || echo "  sandbells.service not found or inactive."
echo ""
echo "Luakit Kiosk:"
systemctl status luakit-kiosk.service --no-pager -l 2>&1 | grep -E "Active|ExecStart|Loaded" || echo "  luakit-kiosk.service not found or inactive."
echo ""

echo "=== Django Environment ==="
echo "Settings DEBUG mode:"
grep -E "DEBUG| CSP" /opt/sandbells/changes/changes/settings.py 2>/dev/null || grep -E "DEBUG| CSP" settings.py 2>/dev/null || echo "  Not found"
echo "Running from: $(pwd)"
echo ""

echo "=== Processes ==="
ps aux | grep -E "gunicorn|luakit|WebKit" | grep -v grep || echo "  No relevant processes found."
echo ""

echo "=== Git Status ==="
if cd /home/$USER/Code/Sandbells 2>/dev/null; then
  echo "Branch: $(git branch --show-current 2>/dev/null || echo 'Unknown')"
  echo "Commit: $(git rev-parse --short=6 HEAD 2>/dev/null || echo 'Unknown')"
  git status --short
else
  echo "Not a git repo or wrong directory."
fi
echo ""

echo "=== Templates Check ==="
if [ -d "templates" ] || [ -d "../templates" ]; then
  grep -r "http-equiv=\"refresh\"" templates/ 2>/dev/null || echo "  No auto-refresh meta tags found."
else
  echo "  No templates directory found."
fi

echo "Health check complete."
echo "Teardown safety: Targets only 'sandbells' user. Explicit confirmation for destructive actions."
