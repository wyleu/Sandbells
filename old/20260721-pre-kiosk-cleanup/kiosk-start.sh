#!/bin/bash
# Sandbells Kiosk Starter - Robust version

START_TIME=$(date +%s)
PROJECT_DIR="$HOME/Code/Sandbells"

source "$PROJECT_DIR/show_header.sh"
show_header

echo "Launching Kiosk on HDMI display..."

export DISPLAY=:0
export XAUTHORITY=/home/sandbells/.Xauthority

cd "$PROJECT_DIR"

# Kill competing processes
pkill -9 luakit matchbox-window-manager openbox lxsession 2>/dev/null || true
sleep 2

# Disable blanking
xset s off -d :0 2>/dev/null || true
xset -dpms -d :0 2>/dev/null || true
xset s noblank -d :0 2>/dev/null || true

# Try to start matchbox (less aggressive)
matchbox-window-manager -use_titlebar no -use_cursor yes -d :0 &

sleep 3

echo "Attempting to reach local site..."

for url in "http://sandbells.local" "http://localhost:8000" "http://127.0.0.1:8000"; do
    if curl -s --connect-timeout 5 "$url" > /dev/null 2>&1; then
        echo "✓ Server found at $url"
        luakit --enable-plugins --kiosk --single-process "$url" 2>&1 | tee -a luakit.log &
        echo "Kiosk started."
        exit 0
    fi
done

echo "⚠ No local server — showing offline page"
luakit --enable-plugins --kiosk "data:text/html,<h1 style='color:#aa0000;text-align:center;margin-top:20%'>Sandbells Offline</h1><p>Waiting for server...</p>" 2>&1 | tee -a luakit.log &
