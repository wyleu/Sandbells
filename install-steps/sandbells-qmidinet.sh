#!/bin/bash
# sandbells-qmidinet.sh
# Pick a network for QmidiNet and start, stop or restart the service.
#
# Wired (ethernet with a link and a global IPv4 address) wins; otherwise
# Wi-Fi with a link and an address.  If neither is ready, QmidiNet is
# stopped and this script waits for a change (ip monitor, or a sleep of
# check_period_s).  When wired comes up later, QmidiNet is restarted on it.
#
# Does not edit /etc/sandbells/settings.json.  Never prints Wi-Fi
# secrets.  The Pico's MIDI port is not opened or written.
#
# Settings, all optional, under "chimes" / "chimes.qmidinet" in
# /etc/sandbells/settings.json (or SANDBELLS_SETTINGS).  Named constants
# below are the defaults:
#   wired_interface, wifi_interface  ("" = first ready iface of that kind)
#   udp_addr   (default 225.0.0.37, ipMIDI / QmidiNet multicast)
#   udp_port   (default 21928)
#   num_ports  (default 1)
#   check_period_s  (default 30; wait timeout, not a tight poll)
#
# Commands:
#   --once          choose and sync once (default)
#   --loop          sync, then wait for a link/address change and repeat
#   --choose        print the chosen interface (empty if none) and exit
#   --print-config  print the resolved settings (no secrets) and exit
#   --stop          stop the QmidiNet unit
#   --help
#
# The systemd unit runs, from `man qmidinet`:
#   qmidinet --no-gui --jack-midi=no --alsa-midi=yes \
#            --interface=IFACE --udp-addr=ADDR --udp-port=PORT --num-ports=N
#
# Env for tests / install: SANDBELLS_QMIDINET_NETDIR, SANDBELLS_QMIDINET_ADDRDIR,
# SANDBELLS_QMIDINET_ENV, SANDBELLS_QMIDINET_UNIT, SANDBELLS_SYSTEMCTL,
# SANDBELLS_SETTINGS, SANDBELLS_QMIDINET_DRY_RUN, SANDBELLS_QMIDINET_LIB.

# ---------------------------------------------------------------------------
# Named constants (no magic numbers or hard-coded interface names)
# ---------------------------------------------------------------------------
SETTINGS="${SANDBELLS_SETTINGS:-/etc/sandbells/settings.json}"
SETTINGS_JSON_BLOCK="chimes"
SETTINGS_JSON_SUB="qmidinet"

# Linux ARPHRD_ETHER (Wi-Fi and copper/USB ethernet all use this type).
IFACE_TYPE_ETHER=1

DEFAULT_WIRED_INTERFACE=""
DEFAULT_WIFI_INTERFACE=""
# ipMIDI / QmidiNet multicast, from `man qmidinet`.
DEFAULT_UDP_ADDR="225.0.0.37"
DEFAULT_UDP_PORT=21928
DEFAULT_NUM_PORTS=1
DEFAULT_CHECK_PERIOD_S=30
DEFAULT_QMIDINET="qmidinet"
DEFAULT_JACK_MIDI="no"
DEFAULT_ALSA_MIDI="yes"

# ALSA client name QmidiNet registers (aplaymidi -l).  Documented here so
# Chimes tests and this helper agree; not used as a filter.
QMIDINET_CLIENT_NAME="QmidiNet"

QMIDINET_UNIT="${SANDBELLS_QMIDINET_UNIT:-sandbells-qmidinet.service}"
ENV_FILE="${SANDBELLS_QMIDINET_ENV:-/run/sandbells/qmidinet.env}"
NET_DIR="${SANDBELLS_QMIDINET_NETDIR:-/sys/class/net}"
# Optional directory of per-iface files used instead of `ip addr` (tests).
ADDR_DIR="${SANDBELLS_QMIDINET_ADDRDIR:-}"
SYSTEMCTL="${SANDBELLS_SYSTEMCTL:-systemctl}"
LOGTAG="sandbells-qmidinet"

# Names that are never a wired or Wi-Fi path to the LAN.
SKIP_IFACE_RE='^(lo|docker.*|veth.*|br-.*|virbr.*|tun.*|tap.*|wg.*|tailscale.*|cni.*|flannel.*)$'

# ---------------------------------------------------------------------------
if [ "${SANDBELLS_QMIDINET_LIB:-}" != 1 ]; then
    set -eu
fi

log() { logger -t "$LOGTAG" "$*" 2>/dev/null || true; echo "$*"; }

dry_run() {
    case "${SANDBELLS_QMIDINET_DRY_RUN:-}" in
        1|true|TRUE|yes|YES) return 0 ;;
        *) return 1 ;;
    esac
}

# Read one optional scalar from settings.json: chimes.qmidinet.KEY, else
# chimes.KEY.  Prints nothing if the file, block or key is missing.
# Only that one value is written; the rest of the file is never printed.
json_chimes_get() {
    local key="$1"
    [ -f "$SETTINGS" ] || return 0
    command -v python3 >/dev/null 2>&1 || return 0
    python3 - "$SETTINGS" "$SETTINGS_JSON_BLOCK" "$SETTINGS_JSON_SUB" "$key" <<'PY'
import json, sys
path, block, sub, key = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
try:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
except (OSError, json.JSONDecodeError, UnicodeError):
    sys.exit(0)
if not isinstance(raw, dict):
    sys.exit(0)
body = raw.get(block)
if not isinstance(body, dict):
    sys.exit(0)
val = None
nested = body.get(sub)
if isinstance(nested, dict) and key in nested:
    val = nested.get(key)
elif key in body:
    val = body.get(key)
if val is None or val == "":
    sys.exit(0)
if isinstance(val, bool) or not isinstance(val, (str, int, float)):
    sys.exit(0)
print(val)
PY
}

load_config() {
    WIRED_INTERFACE="${SANDBELLS_QMIDINET_WIRED:-$(json_chimes_get wired_interface)}"
    WIFI_INTERFACE="${SANDBELLS_QMIDINET_WIFI:-$(json_chimes_get wifi_interface)}"
    UDP_ADDR="${SANDBELLS_QMIDINET_UDP_ADDR:-$(json_chimes_get udp_addr)}"
    UDP_PORT="${SANDBELLS_QMIDINET_UDP_PORT:-$(json_chimes_get udp_port)}"
    NUM_PORTS="${SANDBELLS_QMIDINET_NUM_PORTS:-$(json_chimes_get num_ports)}"
    CHECK_PERIOD_S="${SANDBELLS_QMIDINET_PERIOD_S:-$(json_chimes_get check_period_s)}"
    QMIDINET_BIN="${SANDBELLS_QMIDINET_BIN:-$(json_chimes_get program)}"
    JACK_MIDI="${SANDBELLS_QMIDINET_JACK_MIDI:-$(json_chimes_get jack_midi)}"
    ALSA_MIDI="${SANDBELLS_QMIDINET_ALSA_MIDI:-$(json_chimes_get alsa_midi)}"

    [ -n "$WIRED_INTERFACE" ] || WIRED_INTERFACE="$DEFAULT_WIRED_INTERFACE"
    [ -n "$WIFI_INTERFACE" ] || WIFI_INTERFACE="$DEFAULT_WIFI_INTERFACE"
    [ -n "$UDP_ADDR" ] || UDP_ADDR="$DEFAULT_UDP_ADDR"
    [ -n "$UDP_PORT" ] || UDP_PORT="$DEFAULT_UDP_PORT"
    [ -n "$NUM_PORTS" ] || NUM_PORTS="$DEFAULT_NUM_PORTS"
    [ -n "$CHECK_PERIOD_S" ] || CHECK_PERIOD_S="$DEFAULT_CHECK_PERIOD_S"
    [ -n "$QMIDINET_BIN" ] || QMIDINET_BIN="$DEFAULT_QMIDINET"
    [ -n "$JACK_MIDI" ] || JACK_MIDI="$DEFAULT_JACK_MIDI"
    [ -n "$ALSA_MIDI" ] || ALSA_MIDI="$DEFAULT_ALSA_MIDI"
}

print_config() {
    load_config
    printf '%s\n' \
        "wired_interface=${WIRED_INTERFACE}" \
        "wifi_interface=${WIFI_INTERFACE}" \
        "udp_addr=${UDP_ADDR}" \
        "udp_port=${UDP_PORT}" \
        "num_ports=${NUM_PORTS}" \
        "check_period_s=${CHECK_PERIOD_S}" \
        "program=${QMIDINET_BIN}" \
        "jack_midi=${JACK_MIDI}" \
        "alsa_midi=${ALSA_MIDI}" \
        "alsa_client=${QMIDINET_CLIENT_NAME}"
}

skip_iface_name() {
    local name="$1"
    [[ "$name" =~ $SKIP_IFACE_RE ]]
}

iface_type() {
    local f="$NET_DIR/$1/type"
    [ -f "$f" ] || { echo ""; return 0; }
    tr -d ' \n' <"$f" 2>/dev/null || true
}

iface_is_wireless() {
    [ -d "$NET_DIR/$1/wireless" ]
}

iface_is_bridge_or_bond() {
    [ -d "$NET_DIR/$1/bridge" ] || [ -d "$NET_DIR/$1/bonding" ]
}

iface_exists() {
    [ -d "$NET_DIR/$1" ]
}

# A carrier of 1 is a link.  Some devices have no carrier file; then
# operstate "up" is accepted.
iface_has_link() {
    local c="$NET_DIR/$1/carrier" o="$NET_DIR/$1/operstate" val
    if [ -f "$c" ]; then
        val="$(tr -d ' \n' <"$c" 2>/dev/null || true)"
        [ "$val" = 1 ]
        return
    fi
    [ -f "$o" ] || return 1
    val="$(tr -d ' \n' <"$o" 2>/dev/null || true)"
    [ "$val" = "up" ]
}

iface_has_global_v4() {
    local dev="$1" line
    if [ -n "$ADDR_DIR" ]; then
        [ -s "$ADDR_DIR/$dev" ]
        return
    fi
    command -v ip >/dev/null 2>&1 || return 1
    while IFS= read -r line; do
        [ -n "$line" ] || continue
        return 0
    done < <(ip -4 -o addr show dev "$dev" scope global 2>/dev/null || true)
    return 1
}

iface_ready() {
    iface_exists "$1" && iface_has_link "$1" && iface_has_global_v4 "$1"
}

# Ethernet (copper or USB) that is not Wi-Fi, not a bridge/bond, not skipped.
iface_is_wired() {
    local typ
    iface_exists "$1" || return 1
    skip_iface_name "$1" && return 1
    iface_is_wireless "$1" && return 1
    iface_is_bridge_or_bond "$1" && return 1
    typ="$(iface_type "$1")"
    [ "$typ" = "$IFACE_TYPE_ETHER" ]
}

iface_is_wifi() {
    iface_exists "$1" || return 1
    skip_iface_name "$1" && return 1
    iface_is_wireless "$1"
}

# List matching interfaces in a stable (alphabetical) order.
list_ifaces() {
    local kind="$1" name
    [ -d "$NET_DIR" ] || return 0
    shopt -s nullglob
    for name in "$NET_DIR"/*; do
        name="$(basename "$name")"
        case "$kind" in
            wired) iface_is_wired "$name" || continue ;;
            wifi)  iface_is_wifi "$name" || continue ;;
            *) continue ;;
        esac
        printf '%s\n' "$name"
    done | LC_ALL=C sort
    shopt -u nullglob
}

# If a name is set, only that interface (when ready).  Else the first ready
# one of that kind.
first_ready() {
    local configured="$1" kind="$2" name
    if [ -n "$configured" ]; then
        if iface_ready "$configured"; then
            printf '%s\n' "$configured"
            return 0
        fi
        return 1
    fi
    while IFS= read -r name; do
        [ -n "$name" ] || continue
        if iface_ready "$name"; then
            printf '%s\n' "$name"
            return 0
        fi
    done < <(list_ifaces "$kind")
    return 1
}

# Wired with link+address first; otherwise Wi-Fi.  Empty if neither is ready.
choose_interface() {
    load_config
    local iface
    if iface="$(first_ready "$WIRED_INTERFACE" wired)"; then
        printf '%s\n' "$iface"
        return 0
    fi
    if iface="$(first_ready "$WIFI_INTERFACE" wifi)"; then
        printf '%s\n' "$iface"
        return 0
    fi
    return 1
}

current_env_iface() {
    local line
    [ -f "$ENV_FILE" ] || return 0
    line="$(sed -n 's/^QMIDINET_IFACE=//p' "$ENV_FILE" | tail -n 1)"
    printf '%s\n' "$line"
}

write_env() {
    local iface="$1" dir
    dir="$(dirname "$ENV_FILE")"
    if dry_run; then
        echo "dry-run: write $ENV_FILE (QMIDINET_IFACE=$iface udp-addr=$UDP_ADDR udp-port=$UDP_PORT num-ports=$NUM_PORTS)"
        return 0
    fi
    mkdir -p "$dir"
    cat >"$ENV_FILE" <<EOF
QMIDINET_IFACE=$iface
QMIDINET_UDP_ADDR=$UDP_ADDR
QMIDINET_UDP_PORT=$UDP_PORT
QMIDINET_NUM_PORTS=$NUM_PORTS
QMIDINET_BIN=$QMIDINET_BIN
QMIDINET_JACK_MIDI=$JACK_MIDI
QMIDINET_ALSA_MIDI=$ALSA_MIDI
EOF
}

unit_is_active() {
    "$SYSTEMCTL" is-active --quiet "$QMIDINET_UNIT" 2>/dev/null
}

run_systemctl() {
    if dry_run; then
        echo "dry-run: $SYSTEMCTL $*"
        return 0
    fi
    "$SYSTEMCTL" "$@"
}

# Start, restart or stop QmidiNet so it matches the chosen interface.
sync_qmidinet() {
    load_config
    local iface="" old
    iface="$(choose_interface || true)"
    old="$(current_env_iface)"
    if [ -z "$iface" ]; then
        if unit_is_active || [ -n "$old" ]; then
            log "no usable network (wired or Wi-Fi) — waiting; QmidiNet stopped"
            run_systemctl stop "$QMIDINET_UNIT" || true
        fi
        return 0
    fi
    write_env "$iface"
    if unit_is_active && [ "$old" = "$iface" ]; then
        return 0
    fi
    if [ -n "$old" ] && [ "$old" != "$iface" ]; then
        log "moving QmidiNet from $old to $iface"
    else
        log "starting QmidiNet on $iface"
    fi
    run_systemctl restart "$QMIDINET_UNIT" || run_systemctl start "$QMIDINET_UNIT" || true
}

wait_for_change() {
    load_config
    local period="$CHECK_PERIOD_S"
    # Only use ip monitor against the real network (not a fake sysfs).
    if [ -z "${SANDBELLS_QMIDINET_NETDIR:-}" ] && command -v ip >/dev/null 2>&1 \
            && command -v timeout >/dev/null 2>&1; then
        timeout --signal=INT "$period" ip -o monitor link address >/dev/null 2>&1 || true
        return 0
    fi
    sleep "$period"
}

stop_qmidinet() {
    run_systemctl stop "$QMIDINET_UNIT" || true
}

usage() {
    sed -n '2,36p' "$0" | sed 's/^# \?//'
}

# ---------------------------------------------------------------------------
# main (skipped when sourced as a library for tests)
# ---------------------------------------------------------------------------
if [ "${SANDBELLS_QMIDINET_LIB:-}" = 1 ]; then
    :
else

cmd="once"
if [ "$#" -gt 0 ]; then
    case "$1" in
        --once) cmd="once" ;;
        --loop) cmd="loop" ;;
        --choose) cmd="choose" ;;
        --print-config) cmd="print-config" ;;
        --stop) cmd="stop" ;;
        --help|-h) cmd="help" ;;
        --*)
            echo "ERROR: unknown option $1" >&2
            exit 1
            ;;
        *)
            echo "ERROR: unknown argument $1" >&2
            exit 1
            ;;
    esac
fi

case "$cmd" in
    help) usage; exit 0 ;;
    print-config) print_config; exit 0 ;;
    choose)
        choose_interface || exit 0
        exit 0
        ;;
    stop) stop_qmidinet; exit 0 ;;
    once) sync_qmidinet; exit 0 ;;
    loop)
        while true; do
            sync_qmidinet
            wait_for_change
        done
        ;;
esac

fi
