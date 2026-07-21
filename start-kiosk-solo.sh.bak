#!/bin/bash
# start-kiosk-solo.sh
# Solo Kiosk for Sandbells - HDMI + mouse only, little-old-lady friendly
# Runs luakit fullscreen via lightdm. Disables all screen blanking/DPMS.
# Intended to be started by systemd (sandbells-kiosk.service)

set -e

PROJECT_DIR="${HOME}/Code/Sandbells"
LOG_FILE="${PROJECT_DIR}/luakit.log"
URL="http://sandbells.local:8000"
# Fallbacks if the named host is not yet resolvable
FALLBACK_URLS=(
    "http://sandbells.local:8000"
    "http://localhost:8000"
    "http://127.0.0.1:8000"
    "http://sandbells.local"
    "http://localhost"
)

echo "=== Starting Solo Sandbells Kiosk $(date) ===" | tee -a "$LOG_FILE"
echo "= = = Working version: lightdm + Luakit fullscreen on HDMI = = =" | tee -a "$LOG_FILE"

# Clean previous browser / WM instances
pkill -9 luakit 2>/dev/null || true
pkill -9 matchbox-window-manager 2>/dev/null || true
pkill -9 WebKitWebProcess 2>/dev/null || true
sleep 1

export DISPLAY=:0
# Prefer the real user's Xauthority (lightdm creates it)
if [ -f "${HOME}/.Xauthority" ]; then
    export XAUTHORITY="${HOME}/.Xauthority"
elif [ -f /var/run/lightdm/root/:0 ]; then
    export XAUTHORITY=/var/run/lightdm/root/:0
fi

cd "$PROJECT_DIR"

# ------------------------------------------------------------------
# Ensure lightdm / X is up
# ------------------------------------------------------------------
if ! pgrep -x Xorg >/dev/null && ! pgrep -x X >/dev/null; then
    echo "X not running – restarting lightdm..." | tee -a "$LOG_FILE"
    sudo systemctl restart lightdm
    # Wait for X to be ready (up to 30 s)
    for i in $(seq 1 30); do
        if pgrep -x Xorg >/dev/null || pgrep -x X >/dev/null; then
            echo "X is up after ${i}s" | tee -a "$LOG_FILE"
            break
        fi
        sleep 1
    done
    sleep 2
else
    echo "X already running" | tee -a "$LOG_FILE"
fi

# ------------------------------------------------------------------
# Disable ALL screen blanking / power management (critical for kiosk)
# ------------------------------------------------------------------
# These must be run against the live DISPLAY after X is up
xset s off 2>/dev/null || true
xset -dpms 2>/dev/null || true
xset s noblank 2>/dev/null || true
xset s 0 0 2>/dev/null || true          # screensaver timeout 0
# Extra belt-and-braces for some Pi / lightdm setups
xset dpms 0 0 0 2>/dev/null || true

echo "Screen blanking / DPMS disabled" | tee -a "$LOG_FILE"

# Optional: hide mouse cursor after a few seconds of inactivity
# (uncomment if desired – mouse still works when moved)
# if command -v unclutter >/dev/null; then
#     pkill unclutter 2>/dev/null || true
#     unclutter -idle 3 -root &
# fi

# ------------------------------------------------------------------
# Find a working backend URL
# ------------------------------------------------------------------
CHOSEN_URL=""
for u in "${FALLBACK_URLS[@]}"; do
    if curl -s --connect-timeout 3 --max-time 4 "$u" >/dev/null 2>&1; then
        CHOSEN_URL="$u"
        echo "✓ Backend reachable at $CHOSEN_URL" | tee -a "$LOG_FILE"
        break
    fi
done

if [ -z "$CHOSEN_URL" ]; then
    echo "⚠ No backend responding – showing offline page" | tee -a "$LOG_FILE"
    CHOSEN_URL="data:text/html,<html><body style='background:#111;color:#c00;font-family:sans-serif;text-align:center;padding-top:20%'><h1>Sandbells Offline</h1><p>Waiting for server...</p><p>$(date)</p></body></html>"
fi

# ------------------------------------------------------------------
# Launch Luakit (fullscreen is forced by ~/.config/luakit/rc.lua)
# Keep the process in the foreground so systemd can supervise it.
# ------------------------------------------------------------------
echo "Launching Luakit kiosk → $CHOSEN_URL" | tee -a "$LOG_FILE"

# -U = unique instance, -u = uri
# The rc.lua already contains:
#   window.add_signal("init", function(w) w.win.fullscreen = true end)
exec luakit -U -u "$CHOSEN_URL" 2>&1 | tee -a "$LOG_FILE"
