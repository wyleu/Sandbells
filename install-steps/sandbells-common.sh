#!/bin/bash
# sandbells-common.sh
# Shared helpers for Sandbells install steps and runtime scripts
# - Settings loading (time_hosts, networks)
# - show_header
# - Small defensive utilities
#
# Usage:
#   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   source "$SCRIPT_DIR/sandbells-common.sh"
#

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
SETTINGS="${SANDBELLS_SETTINGS:-/etc/sandbells/settings.json}"

DEFAULT_TIME_HOSTS=(
    sandgps.local
    sandgps1.local
    sandgps2.local
    sandgps3.local
)

load_time_hosts() {
    TIME_HOSTS=()
    if [ -f "$SETTINGS" ] && command -v jq >/dev/null 2>&1; then
        mapfile -t TIME_HOSTS < <(jq -r '.time_hosts[]? // empty' "$SETTINGS" 2>/dev/null)
    fi
    if [ "${#TIME_HOSTS[@]}" -eq 0 ]; then
        TIME_HOSTS=("${DEFAULT_TIME_HOSTS[@]}")
    fi
}

load_networks() {
    NETWORKS=()
    if [ ! -f "$SETTINGS" ]; then
        return
    fi
    if ! command -v jq >/dev/null 2>&1; then
        return
    fi
    while IFS=$'\t' read -r ssid psk; do
        [ -n "$ssid" ] || continue
        NETWORKS+=("$ssid:$psk")
    done < <(jq -r '.networks[]? | "\(.ssid // "")\t\(.psk // "")"' "$SETTINGS" 2>/dev/null)
}

# ---------------------------------------------------------------------------
# Header (moved from show_header.sh)
# ---------------------------------------------------------------------------
show_header() {
    clear
    # Core variables
    ELAPSED=$(( $(date +%s) - ${START_TIME:-$(date +%s)} ))
    CURRENT_HOSTNAME=$(hostname)
    GIT_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "No git")
    GIT_BRANCH=$(git branch --show-current 2>/dev/null || echo "Not in git repo")
    PROJECT_DIR="${PROJECT_DIR:-/home/sandbells/Code/Sandbells}"

    # Colors
    GREEN='\033[0;32m'
    BLUE='\033[0;34m'
    YELLOW='\033[1;33m'
    CYAN='\033[0;36m'
    WHITE='\033[1;37m'
    RED='\033[0;31m'
    BOLD='\033[1m'
    NC='\033[0m'

    echo -e "${CYAN}======================================================================${NC}"
    echo -e " ${BOLD}${GREEN}Sandbells Church Bell Kiosk Setup${NC}"
    echo -e "${CYAN}======================================================================${NC}"
    echo -e " ${CYAN}Date${NC} : ${WHITE}$(date)${NC}"
    echo -e " ${CYAN}Elapsed Time${NC} : ${WHITE}${ELAPSED} seconds${NC}"
    echo -e " ${CYAN}User${NC} : ${WHITE}$(whoami)${NC}"
    echo -e " ${CYAN}Hostname${NC} : ${YELLOW}$CURRENT_HOSTNAME${NC}"
    echo -e " ${CYAN}URL${NC} : ${YELLOW}$CURRENT_HOSTNAME.local${NC}"
    echo -e " ${CYAN}Git Commit${NC} : ${WHITE}$GIT_HASH${NC}"
    echo -e " ${CYAN}Git Branch${NC} : ${WHITE}$GIT_BRANCH${NC}"
    echo -e " ${CYAN}Project Path${NC} : ${WHITE}$PROJECT_DIR${NC}"
    echo -e " ${CYAN}Machine${NC} : ${WHITE}$(cat /proc/cpuinfo | grep -m1 Model | cut -d: -f2 | xargs || echo 'Unknown')${NC}"
    echo -e " ${CYAN}Architecture${NC} : ${WHITE}$(uname -m) ($(getconf LONG_BIT)-bit)${NC}"

    # Memory
    MEM_TOTAL=$(free -h | awk '/^Mem:/ {print $2}')
    MEM_USED=$(free -h | awk '/^Mem:/ {print $3}')
    MEM_FREE=$(free -h | awk '/^Mem:/ {print $4}')
    MEM_PERCENT_USED=$(free | awk '/^Mem:/ {printf "%.0f", $3/$2 * 100}')
    echo -e " ${CYAN}Memory${NC} : ${WHITE}${MEM_USED} used of ${MEM_TOTAL} total${NC}"
    echo -e " ${WHITE}(${MEM_FREE} still free — ${MEM_PERCENT_USED}% in use)${NC}"

    # Temperature
    TEMP=$(vcgencmd measure_temp 2>/dev/null | cut -d= -f2 || echo "N/A")
    echo -e " ${CYAN}Temperature${NC} : ${WHITE}$TEMP${NC}"

    # Time Server
    STRATUM=$(chronyc tracking 2>/dev/null | grep -i stratum | awk '{print $3}' || echo "Unknown")
    RAW_REFID=$(chronyc tracking 2>/dev/null | grep -i "Reference ID" | awk '{print $4}' | tr -d '()' || echo "")
    RAW_SOURCE=$(chronyc sources 2>/dev/null | grep '^\*' | awk '{print $2}' || echo "")
    if [[ $RAW_SOURCE == sandgp* ]]; then
        TIMESERVER="${RAW_SOURCE}.local"
    elif [[ $RAW_REFID == sandgp* ]]; then
        TIMESERVER="${RAW_REFID}.local"
    elif [[ $RAW_REFID =~ ^[0-9A-Fa-f]{8}$ ]]; then
        IP_FROM_HEX=$(printf "%d.%d.%d.%d" 0x${RAW_REFID:0:2} 0x${RAW_REFID:2:2} 0x${RAW_REFID:4:2} 0x${RAW_REFID:6:2} 2>/dev/null)
        RESOLVED=$(avahi-resolve-address "$IP_FROM_HEX" 2>/dev/null | awk '{print $2}' || echo "")
        if [[ $RESOLVED == *.local ]]; then
            TIMESERVER="$RESOLVED"
        else
            TIMESERVER="sandgps3.local (Ref: $RAW_REFID)"
        fi
    else
        TIMESERVER="${RAW_SOURCE:-$RAW_REFID}"
    fi
    echo -e " ${CYAN}Time Server${NC} : ${WHITE}$TIMESERVER${NC}"
    if [ "$STRATUM" = "Unknown" ] || [ "$STRATUM" -gt 10 ] 2>/dev/null; then
        echo -e " ${CYAN}Clock Stratum${NC} : ${RED}$STRATUM (Not Locked!)${NC}"
    else
        echo -e " ${CYAN}Clock Stratum${NC} : ${WHITE}$STRATUM${NC}"
    fi

    # Component Status
    SSH_STATUS=$( [ "$(systemctl is-active ssh 2>/dev/null)" = "active" ] && echo -e "${GREEN}Enabled${NC}" || echo -e "${RED}NOT Enabled${NC}" )
    ONEWIRE_STATUS=$( lsmod | grep -q w1 && echo -e "${GREEN}Enabled${NC}" || echo -e "${RED}NOT Enabled${NC}" )
    FAN_STATUS=$( [ "$(systemctl is-active sandbells-fan.service 2>/dev/null)" = "active" ] && echo -e "${GREEN}Enabled${NC}" || echo -e "${RED}NOT Enabled${NC}" )
    echo -e " ${CYAN}SSH${NC} : ${SSH_STATUS}"
    echo -e " ${CYAN}OneWire${NC} : ${ONEWIRE_STATUS}"
    echo -e " ${CYAN}Fan Control${NC} : ${FAN_STATUS}"

    # ZRAM
    ZRAM_LINE=$(swapon --show | grep zram)
    if [ -n "$ZRAM_LINE" ]; then
        ZRAM_DEV=$(echo "$ZRAM_LINE" | awk '{print $1}')
        ZRAM_SIZE=$(echo "$ZRAM_LINE" | awk '{print $3}')
        ZRAM_USED=$(echo "$ZRAM_LINE" | awk '{print $4}')
        echo -e " ${CYAN}ZRAM${NC} : ${WHITE}${ZRAM_USED} used of ${ZRAM_SIZE} total${NC}"
        echo -e " ${WHITE}(${ZRAM_DEV} — compressed swap)${NC}"
    else
        echo -e " ${CYAN}ZRAM${NC} : ${WHITE}Not active${NC}"
    fi

    # Display
    if [ -n "$DISPLAY" ]; then
        DISPLAY_INFO="${XDG_SESSION_TYPE:-tty} [${DISPLAY}]"
    else
        DISPLAY_INFO="${XDG_SESSION_TYPE:-tty}"
    fi
    echo -e " ${CYAN}Display Server${NC} : ${WHITE}$DISPLAY_INFO${NC}"
    echo -e "${CYAN}======================================================================${NC}"
    echo ""
}

# ---------------------------------------------------------------------------
# Interactive helper
# ---------------------------------------------------------------------------
pause() {
    if [ "${QUICK_MODE:-false}" = true ]; then
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

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log() {
    local tag="${LOGTAG:-sandbells}"
    logger -t "$tag" "$*" 2>/dev/null || true
    echo "$*"
}

# ---------------------------------------------------------------------------
# Privilege / environment checks
# ---------------------------------------------------------------------------
need_root() {
    if [ "$(id -u)" -ne 0 ]; then
        echo "ERROR: this step must be run as root (or with sudo)"
        exit 1
    fi
}

need_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "ERROR: required command '$1' not found"
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Package / service helpers (defensive)
# ---------------------------------------------------------------------------
package_installed() {
    dpkg -s "$1" &>/dev/null
}

service_exists() {
    systemctl list-unit-files --type=service 2>/dev/null | grep -q "^$1"
}

service_is_active() {
    [ "$(systemctl is-active "$1" 2>/dev/null)" = "active" ]
}

service_is_enabled() {
    [ "$(systemctl is-enabled "$1" 2>/dev/null)" = "enabled" ]
}

# Safely stop + disable a service if it exists
stop_and_disable() {
    local unit="$1"
    if service_exists "$unit"; then
        sudo systemctl stop "$unit" 2>/dev/null || true
        sudo systemctl disable "$unit" 2>/dev/null || true
    fi
}

# Safely enable + start a service if the unit file exists
enable_and_start() {
    local unit="$1"
    if [ -f "/etc/systemd/system/$unit" ] || [ -f "/lib/systemd/system/$unit" ]; then
        sudo systemctl daemon-reload
        sudo systemctl enable "$unit"
        sudo systemctl restart "$unit" 2>/dev/null || sudo systemctl start "$unit"
    else
        echo "WARNING: unit $unit not found — skipping enable/start"
    fi
}



# ---------------------------------------------------------------------------
# Small defensive helpers
# ---------------------------------------------------------------------------
package_installed() {
    dpkg -s "$1" &>/dev/null
}

service_exists() {
    systemctl list-unit-files --type=service | grep -q "^$1"
}

service_is_active() {
    [ "$(systemctl is-active "$1" 2>/dev/null)" = "active" ]
}

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "ERROR: required command '$1' not found"
        return 1
    }
}
