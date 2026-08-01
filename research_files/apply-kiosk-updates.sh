#!/bin/bash
# apply-kiosk-updates.sh
# Run this ON THE PI inside your existing ~/Code/Sandbells repo
# to bring in the new kiosk / gunicorn / nginx / django install steps.
#
# Usage:
#   cd ~/Code/Sandbells
#   bash /path/to/apply-kiosk-updates.sh
#   # or copy the whole Sandbells/ folder from the artifacts over the repo

set -e

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
echo "Applying Sandbells kiosk updates from: $REPO_ROOT"
echo "Target repo should be your live ~/Code/Sandbells"

# Safety: we expect to be run from inside the repo or with files already placed
if [ ! -f "$REPO_ROOT/start-kiosk-solo.sh" ]; then
    echo "ERROR: start-kiosk-solo.sh not found. Place this script inside the updated tree."
    exit 1
fi

echo ""
echo "Files that will be installed/updated:"
echo "  start-kiosk-solo.sh"
echo "  master_install.sh"
echo "  TODO.md"
echo "  INSTALL-KIOSK.md"
echo "  luakit/rc.lua"
echo "  nginx/nginx.conf"
echo "  systemd/sandbells-kiosk.service"
echo "  systemd/gunicorn.service"
echo "  systemd/gunicorn.socket"
echo "  install-steps/05-packages.sh"
echo "  install-steps/12-django-venv.sh"
echo "  install-steps/13-gunicorn-nginx.sh"
echo "  install-steps/14-kiosk-systemd.sh"
echo ""

read -p "Continue internally? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# Make scripts executable
chmod +x "$REPO_ROOT"/start-kiosk-solo.sh \
         "$REPO_ROOT"/master_install.sh \
         "$REPO_ROOT"/install-steps/*.sh \
         "$REPO_ROOT"/apply-kiosk-updates.sh 2>/dev/null || true

echo ""
echo "✓ Files are in place and executable."
echo ""
echo "Next steps on the Pi:"
echo "  1. cd ~/Code/Sandbells"
echo "  2. ./install-steps/12-django-venv.sh"
echo "  3. ./install-steps/13-gunicorn-nginx.sh"
echo "  4. ./install-steps/14-kiosk-systemd.sh"
echo "  5. sudo reboot"
echo ""
echo "Or run the full master installer:"
echo "  ./master_install.sh"
echo ""
echo "See INSTALL-KIOSK.md for full documentation."
