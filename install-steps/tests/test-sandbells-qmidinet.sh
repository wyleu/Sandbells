#!/bin/bash
# Interface choice and config for sandbells-qmidinet.sh, against a fake
# sysfs and stubbed ip/systemctl.  Nothing on the host is started or
# changed, and /etc/sandbells/settings.json is never written.
# Run from anywhere:  bash install-steps/tests/test-sandbells-qmidinet.sh

set -eu

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STEPS_DIR="$(cd "$TEST_DIR/.." && pwd)"
HELPER="$STEPS_DIR/sandbells-qmidinet.sh"
UNIT="$STEPS_DIR/../systemd/sandbells-qmidinet.service"
SELECT="$STEPS_DIR/../systemd/sandbells-qmidinet-select.service"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "ok: $*"; }

[ -f "$HELPER" ] || fail "missing $HELPER"
[ -x "$HELPER" ] || fail "$HELPER is not executable"
[ -f "$UNIT" ] || fail "missing $UNIT"
[ -f "$SELECT" ] || fail "missing $SELECT"

bash -n "$HELPER" || fail "bash -n $HELPER"
pass "bash -n"

if command -v shellcheck >/dev/null 2>&1; then
    shellcheck -s bash -e SC2329 "$HELPER" || fail "shellcheck $HELPER"
    pass "shellcheck"
else
    echo "shellcheck not installed — skipped"
fi

# Guards: named constants, no hard-coded eth0/wlan0 as the only choice,
# no settings writes, no Wi-Fi passwords, documented qmidinet options.
text="$(cat "$HELPER")"
for token in DEFAULT_UDP_ADDR DEFAULT_UDP_PORT DEFAULT_NUM_PORTS \
        DEFAULT_CHECK_PERIOD_S IFACE_TYPE_ETHER SKIP_IFACE_RE \
        QMIDINET_CLIENT_NAME "225.0.0.37" 21928 check_period_s \
        wired_interface wifi_interface; do
    printf '%s' "$text" | grep -q -F -- "$token" \
        || fail "helper should name $token"
done
printf '%s' "$text" | grep -q "Does not edit /etc/sandbells/settings.json" \
    || fail "helper should say it does not edit settings"
if printf '%s' "$text" | grep -Eiq 'psk|wpa_passphrase'; then
    fail "helper must not mention Wi-Fi passwords"
fi
# The helper may list eth0/wlan0 only as documentation, not as defaults.
printf '%s' "$text" | grep -q 'DEFAULT_WIRED_INTERFACE=""' \
    || fail "wired default should be empty (auto)"
printf '%s' "$text" | grep -q 'DEFAULT_WIFI_INTERFACE=""' \
    || fail "wifi default should be empty (auto)"

grep -q -- "--no-gui" "$UNIT" || fail "unit should run qmidinet --no-gui"
grep -q -- "--interface=" "$UNIT" || fail "unit should pass --interface"
grep -q -- "--udp-addr=" "$UNIT" || fail "unit should pass --udp-addr"
grep -q -- "--udp-port=" "$UNIT" || fail "unit should pass --udp-port"
grep -q -- "--jack-midi=" "$UNIT" || fail "unit should pass --jack-midi"
grep -q "QT_QPA_PLATFORM=offscreen" "$UNIT" || fail "unit should set offscreen Qt"
grep -q -- "--loop" "$SELECT" || fail "select unit should run --loop"
grep -q "WantedBy=multi-user.target" "$SELECT" || fail "select unit should start at boot"
if grep -q "WantedBy=multi-user.target" "$UNIT"; then
    fail "qmidinet unit should not enable itself (select starts it)"
fi
pass "named constants and unit options"

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/qmidinet-test-XXXXXX")"
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

NET="$WORKDIR/net"
ADDR="$WORKDIR/addr"
ENVF="$WORKDIR/qmidinet.env"
STUBS="$WORKDIR/stubs"
LOG="$WORKDIR/commands.log"
SETTINGS="$WORKDIR/settings.json"
mkdir -p "$NET" "$ADDR" "$STUBS"

# Linux ARPHRD_ETHER
IFACE_TYPE_ETHER=1

make_iface() {
    # make_iface NAME TYPE [wireless] [carrier] [addr] [bridge]
    local name="$1" typ="${2:-1}" wireless="${3:-}" carrier="${4:-}" \
        addr="${5:-}" kind="${6:-}"
    mkdir -p "$NET/$name"
    printf '%s\n' "$typ" >"$NET/$name/type"
    if [ "$wireless" = "wifi" ]; then
        mkdir -p "$NET/$name/wireless"
    fi
    if [ "$kind" = "bridge" ]; then
        mkdir -p "$NET/$name/bridge"
    fi
    if [ "$kind" = "bond" ]; then
        mkdir -p "$NET/$name/bonding"
    fi
    if [ -n "$carrier" ]; then
        printf '%s\n' "$carrier" >"$NET/$name/carrier"
        if [ "$carrier" = 1 ]; then
            echo up >"$NET/$name/operstate"
        else
            echo down >"$NET/$name/operstate"
        fi
    fi
    if [ -n "$addr" ]; then
        printf '%s\n' "$addr" >"$ADDR/$name"
    else
        rm -f "$ADDR/$name"
    fi
}

cat > "$STUBS/systemctl" <<'EOF'
#!/bin/bash
echo "systemctl $*" >>"${CHIME_TEST_LOG:?}"
if [ "${1:-}" = "is-active" ]; then
    if [ -f "${CHIME_TEST_STATE:?}/qmidinet-active" ]; then
        exit 0
    fi
    exit 1
fi
if [ "${1:-}" = "start" ] || [ "${1:-}" = "restart" ]; then
    touch "${CHIME_TEST_STATE:?}/qmidinet-active"
    exit 0
fi
if [ "${1:-}" = "stop" ]; then
    rm -f "${CHIME_TEST_STATE:?}/qmidinet-active"
    exit 0
fi
exit 0
EOF
chmod +x "$STUBS/systemctl"

cat > "$STUBS/logger" <<'EOF'
#!/bin/bash
exit 0
EOF
chmod +x "$STUBS/logger"

STATE="$WORKDIR/state"
mkdir -p "$STATE"

run_helper() {
    env -i \
        PATH="$STUBS:/usr/bin:/bin" \
        HOME="$WORKDIR" \
        CHIME_TEST_LOG="$LOG" \
        CHIME_TEST_STATE="$STATE" \
        SANDBELLS_SETTINGS="$SETTINGS" \
        SANDBELLS_QMIDINET_NETDIR="$NET" \
        SANDBELLS_QMIDINET_ADDRDIR="$ADDR" \
        SANDBELLS_QMIDINET_ENV="$ENVF" \
        SANDBELLS_SYSTEMCTL="$STUBS/systemctl" \
        SANDBELLS_QMIDINET_DRY_RUN="${SANDBELLS_QMIDINET_DRY_RUN:-}" \
        LANG=C \
        "$HELPER" "$@"
}

choose() {
    run_helper --choose
}

reset_net() {
    rm -rf "$NET" "$ADDR"
    mkdir -p "$NET" "$ADDR"
    # loopback is always there and must be ignored
    mkdir -p "$NET/lo"
    echo 772 >"$NET/lo/type"
    echo 1 >"$NET/lo/carrier"
    echo "127.0.0.1/8" >"$ADDR/lo"
    rm -f "$ENVF" "$STATE/qmidinet-active"
    : >"$LOG"
}

# ------------------------------------------------------------------
# 1. No usable interface
# ------------------------------------------------------------------
reset_net
got="$(choose || true)"
[ -z "$got" ] || fail "expected no interface, got '$got'"
pass "no interface when only lo is present"

# ------------------------------------------------------------------
# 2. Wi-Fi only
# ------------------------------------------------------------------
reset_net
make_iface wlan0 "$IFACE_TYPE_ETHER" wifi 1 "192.168.0.22/24"
got="$(choose)"
[ "$got" = "wlan0" ] || fail "expected wlan0, got '$got'"
pass "Wi-Fi is used when it is the only ready network"

# ------------------------------------------------------------------
# 3. Wired and Wi-Fi both ready: wired wins
# ------------------------------------------------------------------
reset_net
make_iface wlan0 "$IFACE_TYPE_ETHER" wifi 1 "192.168.0.22/24"
make_iface eth0 "$IFACE_TYPE_ETHER" "" 1 "192.168.0.21/24"
got="$(choose)"
[ "$got" = "eth0" ] || fail "expected eth0 over wlan0, got '$got'"
pass "wired wins when both have a link and an address"

# ------------------------------------------------------------------
# 4. Wired has a link but no address: fall back to Wi-Fi
# ------------------------------------------------------------------
reset_net
make_iface wlan0 "$IFACE_TYPE_ETHER" wifi 1 "192.168.0.22/24"
make_iface eth0 "$IFACE_TYPE_ETHER" "" 1 ""
got="$(choose)"
[ "$got" = "wlan0" ] || fail "expected wlan0 (eth0 has no address), got '$got'"
pass "Wi-Fi is used when wired has a link but no address"

# ------------------------------------------------------------------
# 5. Then wired gets an address: switch to wired
# ------------------------------------------------------------------
printf '%s\n' "192.168.0.21/24" >"$ADDR/eth0"
got="$(choose)"
[ "$got" = "eth0" ] || fail "expected eth0 once it has an address, got '$got'"
pass "switches to wired when its address appears"

# ------------------------------------------------------------------
# 6. USB ethernet (enx...) counts as wired; docker/bridge is skipped
# ------------------------------------------------------------------
reset_net
make_iface docker0 "$IFACE_TYPE_ETHER" "" 1 "172.17.0.1/16" bridge
make_iface enx123abc "$IFACE_TYPE_ETHER" "" 1 "192.168.1.4/24"
make_iface wlan0 "$IFACE_TYPE_ETHER" wifi 1 "192.168.0.22/24"
got="$(choose)"
[ "$got" = "enx123abc" ] || fail "expected USB ethernet, got '$got'"
pass "USB ethernet is wired; docker bridge is skipped"

# ------------------------------------------------------------------
# 7. Settings can name the interfaces; unused ethernet is ignored
# ------------------------------------------------------------------
reset_net
make_iface eth0 "$IFACE_TYPE_ETHER" "" 1 "10.0.0.1/24"
make_iface enx123abc "$IFACE_TYPE_ETHER" "" 1 "192.168.1.4/24"
make_iface wlan0 "$IFACE_TYPE_ETHER" wifi 1 "192.168.0.22/24"
cat >"$SETTINGS" <<'JSON'
{
  "networks": [{"ssid": "Example", "psk": "SECRET-MUST-NOT-LEAK"}],
  "chimes": {
    "qmidinet": {
      "wired_interface": "enx123abc",
      "wifi_interface": "wlan0",
      "udp_addr": "225.0.0.38",
      "udp_port": 21929,
      "num_ports": 2,
      "check_period_s": 15
    }
  }
}
JSON
got="$(choose)"
[ "$got" = "enx123abc" ] || fail "settings wired_interface should win, got '$got'"

cfg="$(run_helper --print-config)"
printf '%s\n' "$cfg" | grep -qx "wired_interface=enx123abc" || fail "config wired_interface: $cfg"
printf '%s\n' "$cfg" | grep -qx "wifi_interface=wlan0" || fail "config wifi_interface: $cfg"
printf '%s\n' "$cfg" | grep -qx "udp_addr=225.0.0.38" || fail "config udp_addr: $cfg"
printf '%s\n' "$cfg" | grep -qx "udp_port=21929" || fail "config udp_port: $cfg"
printf '%s\n' "$cfg" | grep -qx "num_ports=2" || fail "config num_ports: $cfg"
printf '%s\n' "$cfg" | grep -qx "check_period_s=15" || fail "config check_period_s: $cfg"
if printf '%s' "$cfg" | grep -q "SECRET-MUST-NOT-LEAK"; then
    fail "print-config leaked a Wi-Fi password"
fi
if printf '%s' "$cfg" | grep -qi "psk"; then
    fail "print-config mentioned psk"
fi
pass "settings name the interface and the port; secrets are not printed"

# Named wired interface down: fall back to the named Wi-Fi
rm -f "$ADDR/enx123abc"
echo 0 >"$NET/enx123abc/carrier"
got="$(choose)"
[ "$got" = "wlan0" ] || fail "expected named Wi-Fi when named wired is down, got '$got'"
pass "falls back to named Wi-Fi when named wired is down"

# ------------------------------------------------------------------
# 8. Defaults when settings.json is absent
# ------------------------------------------------------------------
rm -f "$SETTINGS"
cfg="$(run_helper --print-config)"
printf '%s\n' "$cfg" | grep -qx "udp_addr=225.0.0.37" || fail "default udp_addr: $cfg"
printf '%s\n' "$cfg" | grep -qx "udp_port=21928" || fail "default udp_port: $cfg"
printf '%s\n' "$cfg" | grep -qx "num_ports=1" || fail "default num_ports: $cfg"
printf '%s\n' "$cfg" | grep -qx "check_period_s=30" || fail "default check_period_s: $cfg"
printf '%s\n' "$cfg" | grep -qx "wired_interface=" || fail "default wired empty: $cfg"
printf '%s\n' "$cfg" | grep -qx "alsa_client=QmidiNet" || fail "default alsa_client: $cfg"
pass "defaults when settings.json is missing"

# ------------------------------------------------------------------
# 9. --once starts on the chosen iface; same iface is not restarted;
#    loss of network stops it; dry-run does not call systemctl
# ------------------------------------------------------------------
reset_net
make_iface eth0 "$IFACE_TYPE_ETHER" "" 1 "192.168.0.21/24"
: >"$LOG"
run_helper --once >/dev/null
grep -q "systemctl restart sandbells-qmidinet.service" "$LOG" \
    || fail "should start/restart qmidinet on first sync: $(cat "$LOG")"
[ -f "$ENVF" ] || fail "env file should be written"
grep -q "^QMIDINET_IFACE=eth0$" "$ENVF" || fail "env should name eth0"
: >"$LOG"
run_helper --once >/dev/null
if grep -E "systemctl (restart|start|stop)" "$LOG"; then
    fail "should not restart when the interface is unchanged: $(cat "$LOG")"
fi
pass "starts once and leaves a running unit alone"

# lose the network
rm -f "$ADDR/eth0"
echo 0 >"$NET/eth0/carrier"
: >"$LOG"
run_helper --once >/dev/null
grep -q "systemctl stop sandbells-qmidinet.service" "$LOG" \
    || fail "should stop qmidinet when no network remains: $(cat "$LOG")"
pass "stops QmidiNet when no network remains"

reset_net
make_iface wlan0 "$IFACE_TYPE_ETHER" wifi 1 "192.168.0.22/24"
: >"$LOG"
SANDBELLS_QMIDINET_DRY_RUN=1 run_helper --once >/dev/null
if grep -E "systemctl (restart|start|stop)" "$LOG"; then
    fail "dry-run must not start or stop qmidinet: $(cat "$LOG")"
fi
[ ! -f "$ENVF" ] || fail "dry-run must not write the env file"
pass "dry-run changes nothing"

echo "All sandbells-qmidinet.sh tests passed."
