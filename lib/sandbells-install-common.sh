# sandbells-install-common.sh — sourced by install-steps/NN-*.sh

sandbells_install_init() {
    # call from each step with "${BASH_SOURCE[0]}"
    local caller="${1:-}"
    QUICK_MODE="${QUICK_MODE:-false}"
    if [ -n "$caller" ]; then
        SCRIPT_DIR="$(cd "$(dirname "$caller")" && pwd)"
    else
        SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    fi
    REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
}

pause() {
    if [ "${QUICK_MODE}" = true ]; then
        sleep 1.5
        return 0
    fi
    echo ""
    read -r -p "Press Enter to continue (or Q to stop) > " choice
    if [[ "$choice" =~ ^[Qq]$ ]]; then
        echo "Setup stopped safely."
        exit 1
    fi
}

step_banner() {
    echo "=================================================="
    echo "$1"
    echo "=================================================="
}

require_files() {
    local f
    for f in "$@"; do
        if [ ! -f "$f" ]; then
            echo "ERROR: missing $f"
            exit 1
        fi
    done
}

install_sbin() {
    # install_sbin SRC DST_NAME  → /usr/local/sbin/DST_NAME mode 755
    sudo install -m 755 "$1" "/usr/local/sbin/$2"
    echo "  installed /usr/local/sbin/$2"
}

install_unit() {
    sudo install -m 644 "$1" "/etc/systemd/system/$2"
    echo "  installed /etc/systemd/system/$2"
}

systemd_reload_enable() {
    # systemd_reload_enable unit [timer?]
    sudo systemctl daemon-reload
    sudo systemctl enable "$1"
    if [ -n "${2:-}" ]; then
        sudo systemctl enable "$2"
        sudo systemctl start "$2" || true
    else
        sudo systemctl restart "$1" 2>/dev/null || sudo systemctl start "$1" || true
    fi
}
