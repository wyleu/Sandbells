#!/bin/bash
# 13-gunicorn-nginx.sh
# Sandbells Install Step – Gunicorn socket/service + Nginx reverse proxy
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
echo " 13 – Gunicorn + Nginx"
echo "=================================================="

PROJECT_DIR="/home/sandbells/Code/Sandbells"
SYSTEMD_DIR="${PROJECT_DIR}/systemd"
NGINX_SRC="${PROJECT_DIR}/nginx/nginx.conf"

# ------------------------------------------------------------------
# 1. Install packages
# ------------------------------------------------------------------
echo "[1/7] Installing nginx (gunicorn comes from the venv)..."
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends nginx

# Stop the default nginx so we can replace config cleanly
sudo systemctl stop nginx 2>/dev/null || true

pause

# ------------------------------------------------------------------
# 2. Install gunicorn socket + service
# ------------------------------------------------------------------
echo "[2/7] Installing gunicorn systemd units..."
sudo cp "${SYSTEMD_DIR}/gunicorn.socket"  /etc/systemd/system/
sudo cp "${SYSTEMD_DIR}/gunicorn.service" /etc/systemd/system/

# Ensure the runtime directory can be created
sudo mkdir -p /run
sudo chown sandbells:sandbells /run 2>/dev/null || true

pause

# ------------------------------------------------------------------
# 3. Install nginx configuration
# ------------------------------------------------------------------
echo "[3/7] Installing nginx configuration..."
# Backup existing
if [ -f /etc/nginx/nginx.conf ]; then
    sudo cp /etc/nginx/nginx.conf "/etc/nginx/nginx.conf.bak.$(date +%Y%m%d%H%M%S)"
fi

sudo cp "$NGINX_SRC" /etc/nginx/nginx.conf

# Make sure log dir and static dir exist
sudo mkdir -p /var/log/nginx
sudo mkdir -p /var/www/sandbells/static
sudo chown -R sandbells:sandbells /var/www/sandbells
sudo chown -R www-data:www-data /var/log/nginx 2>/dev/null || true

# Test config
echo "Testing nginx configuration..."
sudo nginx -t

pause

# ------------------------------------------------------------------
# 4. Enable + start gunicorn (socket activation)
# ------------------------------------------------------------------
echo "[4/7] Enabling gunicorn socket + service..."
sudo systemctl daemon-reload
sudo systemctl enable gunicorn.socket
sudo systemctl enable gunicorn.service
sudo systemctl start gunicorn.socket
# The service will be started on first connection, but we can start it now
sudo systemctl start gunicorn.service || true

sleep 2
sudo systemctl status gunicorn.socket --no-pager || true
sudo systemctl status gunicorn.service --no-pager || true

pause

# ------------------------------------------------------------------
# 5. Enable + start nginx
# ------------------------------------------------------------------
echo "[5/7] Enabling and starting nginx..."
sudo systemctl enable nginx
sudo systemctl restart nginx
sleep 1
sudo systemctl status nginx --no-pager || true

pause

# ------------------------------------------------------------------
# 6. Quick connectivity test
# ------------------------------------------------------------------
echo "[6/7] Connectivity test..."
if curl -s --connect-timeout 3 http://127.0.0.1/ >/dev/null 2>&1; then
    echo "✓ http://127.0.0.1/ responds"
else
    echo "⚠ http://127.0.0.1/ did not respond (Django may still be starting)"
fi

if curl -s --connect-timeout 3 http://sandbells.local/ >/dev/null 2>&1; then
    echo "✓ http://sandbells.local/ responds"
else
    echo "⚠ http://sandbells.local/ did not respond (check /etc/hosts or avahi)"
fi

# Show socket
ls -l /run/gunicorn.socket 2>/dev/null || echo "Socket not yet visible"

pause

# ------------------------------------------------------------------
# 7. Firewall note (optional)
# ------------------------------------------------------------------
echo "[7/7] Notes"
echo "  • Gunicorn listens on unix:/run/gunicorn.socket"
echo "  • Nginx proxies port 80 → gunicorn and serves /static/"
echo "  • Static files must be in /var/www/sandbells/static (step 12)"
echo "  • If you change Django code: sudo systemctl reload gunicorn"
echo "  • If you change nginx.conf: sudo nginx -t && sudo systemctl reload nginx"
echo ""
echo "Gunicorn + Nginx setup COMPLETE."
pause
