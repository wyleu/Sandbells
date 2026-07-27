#!/bin/bash
# sandbells_eth_link.sh — bring up USB-Ethernet for sandbells recovery LAN
# Host: 192.168.99.1/24  →  sandbells2: 192.168.99.2

set -e
HOST_IP="192.168.99.1/24"
TARGET="192.168.99.2"
USER="${SANDBELLS_USER:-sandbells}"

# Optional: pass iface name, else try to guess a USB ethernet dongle
IFACE="${1:-}"

if [ -z "$IFACE" ]; then
  # Prefer interfaces that look like USB ethernet and are not wlan/lo
  IFACE="$(nmcli -t -f DEVICE,TYPE,STATE device status 2>/dev/null | awk -F: '$2=="ethernet" && $1!="eth0"{print $1; exit}')"
  if [ -z "$IFACE" ]; then
    IFACE="$(ls /sys/class/net | grep -vE '^(lo|wlan|docker|veth)' | head -1)"
  fi
fi

if [ -z "$IFACE" ] || [ ! -d "/sys/class/net/$IFACE" ]; then
  echo "No ethernet iface found. Pass name: $0 enx...  (see: ip -br link)"
  exit 1
fi

echo "Using interface: $IFACE"
sudo ip link set "$IFACE" up
# Clear old addresses on this iface (careful: only the recovery dongle)
sudo ip addr flush dev "$IFACE"
sudo ip addr add "$HOST_IP" dev "$IFACE"

echo "Waiting for link / peer..."
for i in 1 2 3 4 5 6 7 8 9 10; do
  if ping -c 1 -W 1 "$TARGET" >/dev/null 2>&1; then
    echo "OK — $TARGET reachable"
    echo "  ssh ${USER}@${TARGET}"
    echo "  ssh ${USER}@sandbells2.local   # if avahi works"
    exit 0
  fi
  sleep 1
done

echo "No reply from $TARGET"
echo "  Check cable, that sandbells2 applied fallback ${TARGET}/24,"
echo "  and that this iface is the USB dongle: ip -br link"
exit 1