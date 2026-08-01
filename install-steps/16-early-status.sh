#!/bin/bash
# 16-early-status.sh
# Install early console status before LightDM
# Args: $1 = QUICK_MODE
# master_install auto-runs [0-9][0-9]-*.sh — no master_install edit needed.

QUICK_MODE=${1:-false}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

[ -f "$SCRIPT_DIR/sandbells-common.sh" ] && source "$SCRIPT_DIR/sandbells-common.sh"

SELECT_SRC="$SCRIPT_DIR/sandbells-early-status.sh"
UNIT_SRC="$REPO_DIR/systemd/sandbells-early-status.service"
SELECT_DST="/usr/local/sbin/sandbells-early-status.sh"
UNIT_DST="/etc/systemd/system/sandbells-early-status.service"

if ! type pause &>/dev/null; then
  pause() {
    [ "$QUICK_MODE" = true ] && { sleep 1.5; return; }
    echo ""; read -p "Press Enter to continue (or Q to stop) > " choice
    [[ "$choice" =~ ^[Qq]$ ]] && { echo "Setup stopped safely."; exit 1; }
  }
fi

echo "=================================================="
echo "Early status display (console before LightDM)"
echo "=================================================="

for f in "$SELECT_SRC" "$UNIT_SRC"; do
  [ -f "$f" ] || { echo "ERROR: missing $f"; exit 1; }
done

sudo install -m 755 "$SELECT_SRC" "$SELECT_DST"
echo "  installed $SELECT_DST"
sudo install -m 644 "$UNIT_SRC" "$UNIT_DST"
echo "  installed systemd unit"

sudo systemctl daemon-reload
sudo systemctl enable sandbells-early-status.service
echo ""; systemctl is-enabled sandbells-early-status.service || true
echo "Early status step completed"
echo "  Manual test: sudo systemctl start sandbells-early-status.service"
pause
