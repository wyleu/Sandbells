#!/bin/bash
# master_install.sh
# Sandbells Master Installer - Orchestrates the numbered install steps
# Now includes steps 12 (Django), 13 (Gunicorn/Nginx), 14 (Kiosk systemd)

START_TIME=$(date +%s)

# Configuration
TIME_SERVER="sandgps3.local"
BROWSER="luakit"

# Source shared header
if [ -f show_header.sh ]; then
    source show_header.sh
    show_header 2>/dev/null || true
else
    echo "Warning: show_header.sh not found"
fi

sudo -v

# Ensure /etc/sandbells/settings.json exists early
if [ ! -f /etc/sandbells/settings.json ]; then
    echo "==> Creating /etc/sandbells/settings.json from example"
    sudo install -d /etc/sandbells
    sudo cp install-steps/settings.example.json /etc/sandbells/settings.json
    echo "    Edit /etc/sandbells/settings.json later to set real WiFi passwords etc."
fi

QUICK_MODE=false
if [[ "$1" == "--quick" || "$1" == "-q" ]]; then
    QUICK_MODE=true
    echo "Quick mode activated!"
fi

echo "Starting Sandbells installation steps..."
echo "New steps included: 12-django-venv, 13-gunicorn-nginx, 14-kiosk-systemd"
echo ""

STEPS_DIR="./install-steps"
# Ensure steps are executable
chmod +x "$STEPS_DIR"/[0-9][0-9]-*.sh 2>/dev/null || true
chmod +x start-kiosk-solo.sh 2>/dev/null || true

for step in $STEPS_DIR/[0-9][0-9]-*.sh; do
    if [ -x "$step" ]; then
        if type show_header &>/dev/null; then
            show_header
        fi
        echo "Running: $step"
        echo "----------------------------------------------------------------------"
        "$step" "$QUICK_MODE"
        EXIT_CODE=$?
        if [ $EXIT_CODE -ne 0 ]; then
            echo "Step cancelled or failed (exit code $EXIT_CODE)"
            exit 1
        fi
        echo "----------------------------------------------------------------------"
        echo ""
    fi
done

ELAPSED=$(( $(date +%s) - START_TIME ))
echo "======================================================================"
echo "ALL STEPS COMPLETED in ${ELAPSED} seconds"
echo ""
echo "Next action:  sudo reboot"
echo ""
echo "After reboot the Sandbells kiosk will start automatically on the HDMI screen."
echo "See INSTALL-KIOSK.md for day-to-day commands and troubleshooting."
echo "======================================================================"
