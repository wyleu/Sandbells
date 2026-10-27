#!/bin/bash
# 19-power.sh
# Let the farm status page's Reboot and Shut down buttons act on THIS Pi:
#   /etc/sudoers.d/sandbells-power (0440) allowing ONLY the gunicorn service user
#   to run exactly these two commands without a password:
#       /usr/bin/systemctl reboot
#       /usr/bin/systemctl poweroff
# The user is read from systemd/gunicorn.service (User=).
# Idempotent: validated with visudo -cf, only replaced when it changes.
# Without this step the buttons answer "not enabled" (nothing happens).
# Args: $1 = QUICK_MODE
# master_install auto-runs [0-9][0-9]-*.sh, so it needs no edit there.  By hand:
#   bash ~/Code/Sandbells/install-steps/19-power.sh true

QUICK_MODE=${1:-false}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck source=/dev/null
[ -f "$SCRIPT_DIR/sandbells-common.sh" ] && source "$SCRIPT_DIR/sandbells-common.sh"

UNIT_SRC="${SANDBELLS_GUNICORN_UNIT:-$REPO_DIR/systemd/gunicorn.service}"
SUDOERS_DST="${SANDBELLS_SUDOERS_DST:-/etc/sudoers.d/sandbells-power}"
SYSTEMCTL="/usr/bin/systemctl"
VISUDO="/usr/sbin/visudo"

if ! type pause &>/dev/null; then
  pause() {
    [ "$QUICK_MODE" = true ] && { sleep 1; return; }
    echo ""; read -r -p "Press Enter to continue (or Q to stop) > " choice
    [[ "$choice" =~ ^[Qq]$ ]] && { echo "Setup stopped safely."; exit 1; }
  }
fi

echo "=================================================="
echo " 19 – Reboot / Shut down buttons (sudoers rule)"
echo "=================================================="

[ -f "$UNIT_SRC" ] || { echo "ERROR: missing $UNIT_SRC"; exit 1; }
[ -x "$SYSTEMCTL" ] || { echo "ERROR: $SYSTEMCTL not found"; exit 1; }
[ -x "$VISUDO" ] || { echo "ERROR: $VISUDO not found (sudo package)"; exit 1; }

RUN_AS="$(sed -n 's/^[[:space:]]*User=[[:space:]]*\([^[:space:]]*\).*/\1/p' "$UNIT_SRC" | tail -n 1)"
[[ "$RUN_AS" =~ ^[a-z_][a-z0-9_-]*$ ]] || { echo "ERROR: no usable User= in $UNIT_SRC"; exit 1; }
id "$RUN_AS" >/dev/null 2>&1 || { echo "ERROR: user $RUN_AS does not exist"; exit 1; }
echo "  gunicorn runs as: $RUN_AS"

# ------------------------------------------------------------------
# 1. sudoers drop-in
# ------------------------------------------------------------------
echo "[1/2] Installing $SUDOERS_DST..."
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
cat > "$TMP" <<EOT
# Installed by Sandbells install-steps/19-power.sh — do not edit here.
# The farm status page's Reboot and Shut down buttons (bells/controls.py) run exactly these.
$RUN_AS ALL=(root) NOPASSWD: $SYSTEMCTL reboot, $SYSTEMCTL poweroff
EOT

if ! sudo "$VISUDO" -cf "$TMP" >/dev/null; then
  echo "ERROR: generated sudoers rule failed visudo -cf — not installed"
  exit 1
fi
if sudo cmp -s "$TMP" "$SUDOERS_DST"; then
  echo "  unchanged: $SUDOERS_DST"
else
  sudo install -o root -g root -m 0440 "$TMP" "$SUDOERS_DST"
  echo "  installed $SUDOERS_DST"
fi
sudo chown root:root "$SUDOERS_DST"
sudo chmod 0440 "$SUDOERS_DST"
if ! sudo "$VISUDO" -c >/dev/null; then
  echo "ERROR: sudoers no longer validates — removing $SUDOERS_DST"
  sudo rm -f "$SUDOERS_DST"
  exit 1
fi
pause

# ------------------------------------------------------------------
# 2. Check (lists the rule, does NOT reboot or power off)
# ------------------------------------------------------------------
echo "[2/2] Checking the rule for $RUN_AS..."
OK=true
for action in reboot poweroff; do
  if sudo -u "$RUN_AS" sudo -n -l "$SYSTEMCTL" "$action" >/dev/null 2>&1; then
    echo "  ✓ $RUN_AS may run: $SYSTEMCTL $action"
  else
    echo "  ⚠ $RUN_AS cannot run $SYSTEMCTL $action without a password"
    OK=false
  fi
done
echo "Reboot / Shut down step completed"
echo "  The buttons POST /control/reboot/ and /control/poweroff/ (localhost/LAN only, CSRF)"
echo "  Log: journalctl -u gunicorn | grep 'control '"
pause
$OK
