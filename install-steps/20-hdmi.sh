#!/bin/bash
# 20-hdmi.sh
# Install the Sandbells HDMI helper and apply display.hdmi from
# /etc/sandbells/settings.json to this Pi's boot files.
#
# The helper forces a mode at boot (KMS: video= plus a canned EDID;
# legacy firmware: hdmi_force_hotplug / hdmi_ignore_edid / hdmi_group)
# so a passive HDMI splitter that hides or breaks EDID cannot drop the
# kiosk to a low resolution.  It does not edit settings.json.
#
# Idempotent.  master_install runs [0-9][0-9]-*.sh, so it needs no edit
# there.  By hand, after a pull:
#   bash ~/Code/Sandbells/install-steps/20-hdmi.sh true
# Then, for the tower, hand-edit display.hdmi (see docs/hdmi.md), run
#   sudo sandbells-hdmi apply
# and reboot if it says a reboot is needed.
#
# Args: $1 = QUICK_MODE

QUICK_MODE=${1:-false}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck source=/dev/null
[ -f "$SCRIPT_DIR/sandbells-common.sh" ] && source "$SCRIPT_DIR/sandbells-common.sh"

HELPER_SRC="${SANDBELLS_HDMI_SRC:-$REPO_DIR/changes/bells/hdmi.py}"
HELPER_DST="${SANDBELLS_HDMI_DST:-/usr/local/sbin/sandbells-hdmi}"

if ! type pause &>/dev/null; then
  pause() {
    [ "$QUICK_MODE" = true ] && { sleep 1; return; }
    echo ""; read -r -p "Press Enter to continue (or Q to stop) > " choice
    [[ "$choice" =~ ^[Qq]$ ]] && { echo "Setup stopped safely."; exit 1; }
  }
fi

echo "=================================================="
echo " 20 – HDMI mode from settings (boot, persistent)"
echo "=================================================="

[ -f "$HELPER_SRC" ] || { echo "ERROR: missing $HELPER_SRC"; exit 1; }

echo "[1/2] Installing $HELPER_DST"
sudo install -m 0755 "$HELPER_SRC" "$HELPER_DST"
echo "    installed $(sudo "$HELPER_DST" --help >/dev/null && echo "$HELPER_DST")"

echo "[2/2] Applying display.hdmi from /etc/sandbells/settings.json"
echo "    (settings.json is not edited; a reboot may be needed)"
if [ -f /boot/firmware/config.txt ] || [ -f /boot/config.txt ]; then
  sudo "$HELPER_DST" apply
else
  echo "    No Pi boot config.txt found; skipped apply."
  echo "    On a Pi, after setting display.hdmi, run: sudo sandbells-hdmi apply"
fi

echo
echo "Tower recommendation: force 1920x1080 at 60 Hz.  See docs/hdmi.md."
pause
