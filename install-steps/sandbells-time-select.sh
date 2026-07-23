#!/bin/bash
# sandbells-time-select.sh — pick first reachable sandgps*.local and configure chrony
set -e

CANDIDATES=(
    "sandgps.local"
    "sandgps1.local"
    "sandgps2.local"
    "sandgps3.local"
)

LOGTAG="sandbells-time"
log() { logger -t "$LOGTAG" "$*"; echo "$*"; }

TIME_SERVER=""
for host in "${CANDIDATES[@]}"; do
    if getent hosts "$host" >/dev/null 2>&1 || ping -c 1 -W 1 "$host" >/dev/null 2>&1; then
        log "found: $host"
        TIME_SERVER="$host"
        break
    else
        log "miss:  $host"
    fi
done

CONF="/etc/chrony/chrony.conf"
NEED_WRITE=0

if [ -n "$TIME_SERVER" ]; then
    log "prefer: $TIME_SERVER"
    if ! grep -q "server $TIME_SERVER iburst prefer" "$CONF" 2>/dev/null; then
        NEED_WRITE=1
    fi
else
    log "no local sandgps*.local — public NTP only"
    if grep -qE 'server sandgps[0-9]*\.local' "$CONF" 2>/dev/null; then
        NEED_WRITE=1
    fi
fi

if [ "$NEED_WRITE" -eq 1 ]; then
    cp -a "$CONF" "${CONF}.bak.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
    if [ -n "$TIME_SERVER" ]; then
        cat > "$CONF" <<EOF
pool ntp.ubuntu.com iburst
server $TIME_SERVER iburst prefer
makestep 1.0 3
rtcsync
EOF
    else
        cat > "$CONF" <<EOF
pool ntp.ubuntu.com iburst
makestep 1.0 3
rtcsync
EOF
    fi
    systemctl restart chrony
    log "chrony reconfigured and restarted"
else
    log "chrony already correct — no change"
fi

# Best-effort sync (don't fail the unit)
timeout 20 chronyc waitsync 2>/dev/null || log "waitsync timed out (ok if GPS still starting)"
chronyc sources 2>/dev/null | logger -t "$LOGTAG" || true
