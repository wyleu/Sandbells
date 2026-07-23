#!/bin/bash
# deploy-status.sh – redeploy + cache-bust for status-display work on the Pi
set -e

REPO="$HOME/Code/Sandbells"
VENV="$REPO/Bellvirtenv"
DJANGO="$REPO/changes"
CACHE_BUST="${1:-$(date +%s)}"   # optional arg, else timestamp

echo "=== Sandbells deploy ($(date '+%Y-%m-%d %H:%M:%S')) ==="
echo "Branch : $(git -C "$REPO" branch --show-current 2>/dev/null || echo '?')"
echo "Commit : $(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo '?')"
echo "Bust   : $CACHE_BUST"
echo

# 1. Virtualenv
if [[ ! -f "$VENV/bin/activate" ]]; then
  echo "ERROR: virtualenv not found at $VENV"
  exit 1
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
echo "[1/6] virtualenv activated"

# 2. Cache-bust the system_info.js script tag in the template
SVG="$DJANGO/bells/templates/bells/svg_data.html"
if [[ -f "$SVG" ]]; then
  # Replace any existing ?v=... on system_info.js, or add one
  if grep -q 'system_info\.js' "$SVG"; then
    sed -i -E "s|(system_info\.js)(\?v=[^\"']*)?|\1?v=${CACHE_BUST}|g" "$SVG"
    echo "[2/6] cache-bust applied (?v=$CACHE_BUST)"
  else
    echo "[2/6] WARNING: system_info.js not referenced in svg_data.html"
  fi
else
  echo "[2/6] WARNING: $SVG not found"
fi

# 3. Collect static
cd "$DJANGO"
echo "[3/6] collectstatic ..."
python manage.py collectstatic --noinput
echo "      done"

# 4. Stop kiosk, clear WebKit/luakit caches, restart stack
echo "[4/6] stopping kiosk + clearing caches ..."
sudo systemctl stop sandbells-kiosk 2>/dev/null || true

for d in \
  "$HOME/.cache/luakit" \
  "$HOME/.cache/webkitgtk" \
  "$HOME/.cache/webkit" \
  /home/sandbells/.cache/luakit \
  /home/sandbells/.cache/webkitgtk \
  /home/sandbells/.cache/webkit
do
  if [[ -d "$d" ]]; then
    rm -rf "$d"/* 2>/dev/null || true
    echo "      cleared $d"
  fi
done

echo "[5/6] restarting gunicorn + kiosk ..."
sudo systemctl restart gunicorn
sudo systemctl start sandbells-kiosk
echo "      done"

# 5. Health check
echo "[6/6] health check ..."
sleep 2
echo -n "  gunicorn : "; systemctl is-active gunicorn || true
echo -n "  nginx    : "; systemctl is-active nginx || true
echo -n "  kiosk    : "; systemctl is-active sandbells-kiosk || true
echo -n "  API      : "
if curl -sf http://127.0.0.1/api/system-status/ >/dev/null 2>&1; then
  echo "ok"
else
  echo "NOT REACHABLE (may still be starting)"
fi
echo -n "  JS tag   : "
curl -s http://127.0.0.1/ | grep -o 'system_info\.js[^"]*' || echo "(not found)"

echo
echo "=== Deploy finished ==="
echo "Screen should show Screen: / Iframe: under the clock."
echo "If not, press R once on the HDMI display."
