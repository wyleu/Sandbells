#!/bin/bash
# Sandbells Luakit Kiosk Starter - SSH friendly

START_TIME=$(date +%s)
PROJECT_DIR="$HOME/Code/Sandbells"

source "$PROJECT_DIR/show_header.sh"
show_header

echo "Starting Luakit Kiosk..."
echo ""

# Ensure we're targeting the right display
export DISPLAY=:0

cd "$PROJECT_DIR"

# Clean up old processes
pkill -9 luakit matchbox-window-manager 2>/dev/null || true
sleep 1.5

# Disable power saving
xset s off 2>/dev/null || true
xset -dpms 2>/dev/null || true
xset s noblank 2>/dev/null || true

# Start window manager with visible cursor
matchbox-window-manager -use_titlebar no -use_cursor yes &

sleep 2

echo "Attempting to connect to local site..."

for url in "http://sandbells.local" "http://localhost:8000" "http://127.0.0.1:8000"; do
    if curl -s --connect-timeout 4 "$url" > /dev/null 2>&1; then
        echo "✓ Found server at $url"
        echo "Launching Luakit..."
        luakit --enable-plugins --kiosk "$url" 2>&1 | tee -a luakit.log &
        echo "Browser started successfully."
        exit 0
    fi
done

echo "⚠ No local server detected."
luakit --kiosk "data:text/html,<h1 style='color:#aa0000;text-align:center;margin-top:20%'>Sandbells Offline</h1><p>The main system is not responding.</p>" &
