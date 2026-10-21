#!/bin/bash
# sandbells-thermal.sh
# One line of health for the journal (run each minute by
# sandbells-thermal.timer), so a thermal crash leaves a trail:
#   temp=61.2C throttled=0x0 load=0.42 0.38 0.30 mem_used_mb=412
# Read back: journalctl -t sandbells-thermal --since "-1h"
#
# Installed to: /usr/local/bin/sandbells-thermal.sh

THERMAL_ZONE="/sys/class/thermal/thermal_zone0/temp"
MILLI=1000
KIB_PER_MIB=1024

temp_c() {
    local t
    t=$(vcgencmd measure_temp 2>/dev/null | sed -n "s/^temp=\([0-9.]*\).*/\1/p")
    if [ -z "$t" ] && [ -r "$THERMAL_ZONE" ]; then
        t=$(awk -v m="$MILLI" '{ printf "%.1f", $1 / m }' "$THERMAL_ZONE")
    fi
    if [ -n "$t" ]; then echo "${t}C"; else echo "na"; fi
}

throttled() {
    local v
    v=$(vcgencmd get_throttled 2>/dev/null | cut -d= -f2)
    echo "${v:-na}"
}

load3() {
    cut -d' ' -f1-3 /proc/loadavg
}

mem_used_mb() {
    awk -v k="$KIB_PER_MIB" '
        /^MemTotal:/     { total = $2 }
        /^MemAvailable:/ { avail = $2 }
        END { printf "%d", (total - avail) / k }' /proc/meminfo
}

echo "temp=$(temp_c) throttled=$(throttled) load=$(load3) mem_used_mb=$(mem_used_mb)"
