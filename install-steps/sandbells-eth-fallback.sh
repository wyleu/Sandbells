#!/bin/bash
# sandbells-eth-fallback.sh — if no usable IPv4 on eth0, assign published static
set -e

LOGTAG="sandbells-eth"
FALLBACK_IP="192.168.99.2/24"
IFACE="eth0"
FLAG="/etc/sandbells/network-enabled"
WAIT_DHCP_SEC="${WAIT_DHCP_SEC:-20}"

log() { logger -t "$LOGTAG" "$*"; echo "$*"; }

# Site has explicit "network is managed" flag → do nothing
if [ -f "$FLAG" ]; then
  log "flag $FLAG present — skip eth fallback"
  exit 0
fi

if [ ! -d "/sys/class/net/$IFACE" ]; then
  log "no $IFACE — skip"
  exit 0
fi

ip link set "$IFACE" up || true

# Let DHCP try first
log "waiting ${WAIT_DHCP_SEC}s for DHCP on $IFACE"
sleep "$WAIT_DHCP_SEC"

# Already have a non-link-local IPv4?
if ip -4 -o addr show dev "$IFACE" scope global 2>/dev/null | grep -q 'inet '; then
  log "$IFACE already has global IPv4 — no fallback"
  exit 0
fi

log "no global IPv4 on $IFACE — applying $FALLBACK_IP"
ip addr flush dev "$IFACE" || true
ip addr add "$FALLBACK_IP" dev "$IFACE"
ip link set "$IFACE" up
log "fallback active: $FALLBACK_IP"
exit 0
