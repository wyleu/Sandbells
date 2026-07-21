#!/bin/bash
# 14-kiosk-systemd.sh
# Sandbells Install Step – Make luakit kiosk the default boot experience
# Also permanently disables screen blanking / DPMS for the kiosk user.
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
echo " 14 – Kiosk Systemd Service + No-Blanking"
echo "=================================================="

PROJECT_DIR="/home/sandbells/Code/Sandbells"
USER_HOME="/home/sandbells"
SYSTEMD_DIR="${PROJECT_DIR}/systemd"

# ------------------------------------------------------------------
# 1. Ensure start script is executable and in place
# ------------------------------------------------------------------
echo "[1/8] Installing start-kiosk-solo.sh..."
chmod +x "${PROJECT_DIR}/start-kiosk-solo.sh"
# Also put a convenience copy in ~/bin if desired
mkdir -p "${USER_HOME}/bin"
ln -sf "${PROJECT_DIR}/start-kiosk-solo.sh" "${USER_HOME}/bin/start-kiosk" 2>/dev/null || true

pause

# ------------------------------------------------------------------
# 2. Luakit config – force fullscreen (already present, just ensure)
# ------------------------------------------------------------------
echo "[2/8] Ensuring luakit fullscreen config..."
LUAKIT_CFG_DIR="${USER_HOME}/.config/luakit"
mkdir -p "$LUAKIT_CFG_DIR"

# If the project ships a ready rc.lua, install it; otherwise patch
if [ -f "${PROJECT_DIR}/luakit/rc.lua" ]; then
    cp "${PROJECT_DIR}/luakit/rc.lua" "${LUAKIT_CFG_DIR}/rc.lua"
    echo "Installed project luakit/rc.lua"
else
    # Minimal guarantee of fullscreen
    if ! grep -q "w.win.fullscreen = true" "${LUAKIT_CFG_DIR}/rc.lua" 2>/dev/null; then
        cat >> "${LUAKIT_CFG_DIR}/rc.lua" << 'EOF'

-- Sandbells kiosk: force fullscreen
local window = require "window"
window.add_signal("init", function(w)
    w.win.fullscreen = true
end)
EOF
        echo "Appended fullscreen signal to existing rc.lua"
    else
        echo "Fullscreen already configured in rc.lua"
    fi
fi
chown -R sandbells:sandbells "$LUAKIT_CFG_DIR"

pause

# ------------------------------------------------------------------
# 3. Permanent screen-blanking disable (X11 + lightdm)
# ------------------------------------------------------------------
echo "[3/8] Disabling screen blanking permanently..."

# a) User-level xprofile (runs when graphical session starts)
cat > "${USER_HOME}/.xprofile" << 'EOF'
#!/bin/bash
# Sandbells – never blank the screen
xset s off
xset -dpms
xset s noblank
xset s 0 0
xset dpms 0 0 0
EOF
chmod +x "${USER_HOME}/.xprofile"
chown sandbells:sandbells "${USER_HOME}/.xprofile"

# b) Also drop an Xresources / Xsession.d snippet
sudo tee /etc/X11/Xsession.d/99-sandbells-noblank > /dev/null << 'EOF'
# Sandbells kiosk – disable DPMS & screensaver
xset s off >/dev/null 2>&1 || true
xset -dpms >/dev/null 2>&1 || true
xset s noblank >/dev/null 2>&1 || true
EOF

# c) lightdm greeter / seat config – prevent idle
sudo mkdir -p /etc/lightdm/lightdm.conf.d
sudo tee /etc/lightdm/lightdm.conf.d/50-sandbells-kiosk.conf > /dev/null << 'EOF'
[Seat:*]
# Autologin already handled by install-steps/08-autologin.sh
xserver-command=X -s 0 -dpms
# Optional: start a minimal session; we override with our service
# user-session=sandbells-kiosk
EOF

#
# d) Kernel / boot level (Pi specific) – reduce HDMI blanking risk
if [ -f /boot/firmware/config.txt ]; then
    BOOTCFG=/boot/firmware/config.txt
elif [ -f /boot/config.txt ]; then
    BOOTCFG=/boot/config.txt
else
    BOOTCFG=""
fi

if [ -n "$BOOTCFG" ]; then
    if ! grep -q "hdmi_blanking=1" "$BOOTCFG" 2>/dev/null; then
        echo "" | sudo tee -a "$BOOTCFG" > /dev/null
        echo "# Sandbells kiosk – keep HDMI alive" | sudo tee -a "$BOOTCFG" > /dev/null
        echo "hdmi_blanking=1" | sudo tee -a "$BOOTCFG" > /dev/null
        echo "Added hdmi_blanking=1 to $BOOTCFG (takes effect after reboot)"
    fi
fi

echo "Blanking disable measures installed."

pause

# ------------------------------------------------------------------
# 4. Install the systemd kiosk service
# ------------------------------------------------------------------
echo "[4/8] Installing sandbells-kiosk.service..."
sudo cp "${SYSTEMD_DIR}/sandbells-kiosk.service" /etc/systemd/system/
sudo systemctl daemon-reload

pause

# ------------------------------------------------------------------
# 5. Enable the service (do NOT start yet – wait for reboot test)
# ------------------------------------------------------------------
echo "[5/8] Enabling sandbells-kiosk.service to start on boot..."
sudo systemctl enable sandbells-kiosk.service

# Make sure old competing services are disabled
sudo systemctl disable luakit-fullscreen.service 2>/dev/null || true
sudo systemctl disable midori-fullscreen.service 2>/dev/null || true
sudo systemctl disable sandbells.service 2>/dev/null || true

pause

# ------------------------------------------------------------------
# 6. Optional: hide cursor after idle (mouse still works)
# ------------------------------------------------------------------
echo "[6/8] Installing unclutter (optional cursor hide)..."
sudo apt-get install -y --no-install-recommends unclutter 2>/dev/null || true
# unclutter is started from start-kiosk-solo.sh if desired (commented by default)

pause

# ------------------------------------------------------------------
# 7. Permissions / groups
# ------------------------------------------------------------------
echo "[7/8] Final permissions..."
sudo chown -R sandbells:sandbells "$PROJECT_DIR"
sudo chmod +x "${PROJECT_DIR}/start-kiosk-solo.sh"
# Allow sandbells to restart lightdm without password (used by start script)
if ! sudo grep -q "sandbells.*lightdm" /etc/sudoers.d/sandbells 2>/dev/null; then
    echo "sandbells ALL=(ALL) NOPASSWD: /bin/systemctl restart lightdm, /bin/systemctl start lightdm, /bin/systemctl stop lightdm" | \
        sudo tee /etc/sudoers.d/sandbells-lightdm > /dev/null
    sudo chmod 440 /etc/sudoers.d/sandbells-lightdm
    echo "Passwordless lightdm control granted to sandbells"
fi

pause

# ------------------------------------------------------------------
# 8. Summary + test instructions
# ------------------------------------------------------------------
echo "[8/8] DONE – Kiosk systemd service installed."
echo ""
echo "What happens on next boot:"
echo "  1. lightdm starts → auto-login as sandbells"
echo "  2. graphical.target reached"
echo "  3. sandbells-kiosk.service runs start-kiosk-solo.sh"
echo "  4. Script disables blanking, waits for backend, launches luakit fullscreen"
echo ""
echo "Manual test (without reboot):"
echo "  sudo systemctl start sandbells-kiosk.service"
echo "  journalctl -u sandbells-kiosk.service -f"
echo ""
echo "Stop kiosk:"
echo "  sudo systemctl stop sandbells-kiosk.service"
echo ""
echo "If blanking still occurs after reboot, run:"
echo "  DISPLAY=:0 xset q"
echo "  and check the 'Screen Saver' / 'DPMS' sections show timeouts of 0."
echo ""
pause
