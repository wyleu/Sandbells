#!/bin/bash
# sandbells-time-select.sh
# Ensure chrony sources from settings.json time_hosts (sandmon, sandgps*, 10.42.0.1, …)
# - Writes /etc/chrony/sources.d/sandbells.sources only
# - Does not clobber full chrony.conf
# - Safe to run at boot (systemd oneshot) and by hand
#
# Installed to: /usr/local/sbin/sandbells-time-select.sh

set -e

LOGTAG="sandbells-time"
log() { logger -t "$LOGTAG" "$*" 2>/dev/null || true; echo "$*"; }

# common may live next to this script (repo) or only in the install tree
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for cand in \
    "$SCRIPT_DIR/sandbells-common.sh" \
    /home/sandbells/Code/Sandbells/install-steps/sandbells-common.sh \
    /usr/local/share/sandbells/sandbells-common.sh
do
    if [ -f "$cand" ]; then
        # shellcheck source=/dev/null
        source "$cand"
        break
    fi
done

SETTINGS="${SANDBELLS_SETTINGS:-/etc/sandbells/settings.json}"
SOURCES_D="/etc/chrony/sources.d"
SOURCES_FILE="$SOURCES_D/sandbells.sources"
CHRONY_CONF="/etc/chrony/chrony.conf"

DEFAULT_TIME_HOSTS=(
    10.42.0.1
    sandmon.local
    sandgps.local
    sandgps1.local
    sandgps2.local
    sandgps3.local
)

if type load_time_hosts &>/dev/null; then
    load_time_hosts
else
    TIME_HOSTS=()
    if [ -f "$SETTINGS" ] && command -v jq >/dev/null 2>&1; then
        mapfile -t TIME_HOSTS < <(jq -r '.time_hosts[]? // empty' "$SETTINGS" 2>/dev/null)
    fi
fi
if [ "${#TIME_HOSTS[@]}" -eq 0 ]; then
    TIME_HOSTS=("${DEFAULT_TIME_HOSTS[@]}")
fi

host_reachable() {
    local host="$1"
    getent hosts "$host" >/dev/null 2>&1 && return 0
    ping -c 1 -W 1 "$host" >/dev/null 2>&1 && return 0
    return 1
}

# Ensure Debian chrony 4 layout exists (confdir/sourcedir + makestep)
ensure_chrony_base() {
    mkdir -p "$SOURCES_D" /etc/chrony/conf.d

    if [ ! -f "$CHRONY_CONF" ] || ! grep -qE '^sourcedir|^confdir' "$CHRONY_CONF" 2>/dev/null; then
        log "writing chrony.conf skeleton (confdir/sourcedir)"
        cp -a "$CHRONY_CONF" "${CHRONY_CONF}.bak.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
        cat > "$CHRONY_CONF" <<'EOF'
confdir /etc/chrony/conf.d
sourcedir /etc/chrony/sources.d

# Optional uplink fallback (comment out on isolated tower if desired)
pool ntp.ubuntu.com iburst

keyfile /etc/chrony/chrony.keys
driftfile /var/lib/chrony/chrony.drift
ntsdumpdir /var/lib/chrony
logdir /var/log/chrony

maxupdateskew 100.0
rtcsync
makestep 1.0 3
leapsectz right/UTC
EOF
    else
        # Ensure makestep present for large RTC skew after power loss
        if ! grep -qE '^makestep' "$CHRONY_CONF" /etc/chrony/conf.d/*.conf 2>/dev/null; then
            echo 'makestep 1.0 3' > /etc/chrony/conf.d/sandbells-makestep.conf
        fi
    fi
}

write_sources() {
    local prefer_done=0
    local host
    local tmp
    tmp="$(mktemp)"
    {
        echo "# Managed by sandbells-time-select.sh — from time_hosts in settings.json"
        for host in "${TIME_HOSTS[@]}"; do
            [ -n "$host" ] || continue
            if [ "$prefer_done" -eq 0 ]; then
                echo "server $host iburst prefer"
                prefer_done=1
            else
                echo "server $host iburst"
            fi
        done
    } > "$tmp"

    if [ -f "$SOURCES_FILE" ] && cmp -s "$tmp" "$SOURCES_FILE"; then
        rm -f "$tmp"
        return 1
    fi
    mkdir -p "$SOURCES_D"
    cp -a "$SOURCES_FILE" "${SOURCES_FILE}.bak.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
    mv "$tmp" "$SOURCES_FILE"
    chmod 644 "$SOURCES_FILE"
    return 0
}

# --- main ---
log "candidates: ${TIME_HOSTS[*]}"

REACHABLE=()
for host in "${TIME_HOSTS[@]}"; do
    if host_reachable "$host"; then
        log "found: $host"
        REACHABLE+=("$host")
    else
        log "miss:  $host"
    fi
done

if [ "${#REACHABLE[@]}" -eq 0 ]; then
    log "no time_hosts reachable yet — still writing full list for chrony"
else
    log "reachable: ${REACHABLE[*]}"
fi

ensure_chrony_base

if write_sources; then
    log "updated $SOURCES_FILE"
    systemctl restart chrony 2>/dev/null || systemctl start chrony 2>/dev/null || true
    log "chrony restarted"
else
    log "sources unchanged — no chrony restart"
fi

# Best-effort step + sync (do not fail the unit)
chronyc -a 'makestep 1 -1' 2>/dev/null || true
timeout 20 chronyc waitsync 2>/dev/null || log "waitsync timed out (ok if GPS still starting)"
chronyc sources 2>/dev/null | logger -t "$LOGTAG" || true
chronyc tracking 2>/dev/null | logger -t "$LOGTAG" || true
