#!/bin/bash
# 15-network-select.sh
# Install sandbells-network-select helper + systemd timer
# Args: $1 = QUICK_MODE (true/false)

QUICK_MODE=${1:-false}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

SELECT_SRC="$SCRIPT_DIR/sandbells-network-select.sh"
UNIT_SRC="$REPO_DIR/systemd/sandbells-network-select.service"
TIMER_SRC="$REPO_DIR/systemd/sandbells-network-select.timer"

SELECT_DST="/usr/local/sbin/sandbells-network-select.sh"
UNIT_DST="/etc/systemd/system/sandbells-network-select.service"
TIMER_DST="/etc/systemd/system/sandbells-network-select.timer"

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
echo "Network select (local WiFi fallback + timer)"
echo "=================================================="

for f in "$SELECT_SRC" "$UNIT_SRC" "$TIMER_SRC"; do
    if [ ! -f "$f" ]; then
        echo "ERROR: missing $f"
        exit 1
    fi
done

sudo install -m 755 "$SELECT_SRC" "$SELECT_DST"
echo "  installed $SELECT_DST"

sudo install -m 644 "$UNIT_SRC" "$UNIT_DST"
sudo install -m 644 "$TIMER_SRC" "$TIMER_DST"
echo "  installed systemd unit + timer"

sudo systemctl daemon-reload
sudo systemctl enable sandbells-network-select.timer
sudo systemctl start sandbells-network-select.timer

# One-shot now (safe no-op if already online)
sudo "$SELECT_DST" || true

echo ""
systemctl is-enabled sandbells-network-select.timer || true
systemctl list-timers sandbells-network-select.timer --no-pager || true

echo "Network select step completed"
pause
