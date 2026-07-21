#!/bin/bash
# cleanup-old-scripts.sh
# Safely archive outdated / Midori-era / wyleu-hardcoded scripts
# into an old/ directory. Never deletes anything.
#
# Run from the repo root:
#   cd ~/Code/Sandbells
#   bash cleanup-old-scripts.sh
#
# After reviewing the plan you can re-run with --force to actually move.

set -e

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

OLD_DIR="old/$(date +%Y%m%d)-pre-kiosk-cleanup"
FORCE=false
if [[ "$1" == "--force" ]]; then
    FORCE=true
fi

echo "============================================================"
echo " Sandbells cleanup – archive old / superseded scripts"
echo "============================================================"
echo "Repo: $REPO_ROOT"
echo "Archive target: $OLD_DIR"
echo ""

# ------------------------------------------------------------------
# 1. List of clearly outdated files (Midori era, old launchers, backups)
# ------------------------------------------------------------------
OUTDATED=(
    # Midori era
    startMidori.sh
    startMidorinorm.sh
    systemd/midori-fullscreen.service
    systemd/sandbells.service          # calls non-existent guiMidori.sh

    # Older luakit / kiosk launchers (superseded by start-kiosk-solo.sh)
    startLuakit.sh
    startLuakit.sh.bak
    startLuakit.sh.backup
    start-kiosk-safe.sh
    start-kiosk-safe.sh.bak
    start-kiosk.sh.bak
    kiosk-start.sh
    kiosk-start-light.sh

    # Old systemd units (superseded by sandbells-kiosk.service)
    systemd/luakit-fullscreen.service

    # Old one-shot / debug installers
    install.sh
    install_debug.sh
    start_debug.sh
    teardown.sh

    # Backups
    master_install.sh.bak
    show_header.sh.bak
)

# ------------------------------------------------------------------
# 2. Show the plan
# ------------------------------------------------------------------
echo "The following files will be MOVED into $OLD_DIR/ :"
echo ""

TO_MOVE=()
for f in "${OUTDATED[@]}"; do
    if [ -e "$f" ]; then
        echo "  MOVE  $f"
        TO_MOVE+=("$f")
    else
        echo "  skip  $f  (not present)"
    fi
done

echo ""
if [ ${#TO_MOVE[@]} -eq 0 ]; then
    echo "Nothing to archive – all clean."
else
    echo "Total: ${#TO_MOVE[@]} file(s)"
fi
echo ""

# ------------------------------------------------------------------
# 3. Dry-run vs real run
# ------------------------------------------------------------------
if [ "$FORCE" = false ]; then
    echo ">>> DRY RUN only. No files have been moved."
    echo ">>> Re-run with --force to perform the moves:"
    echo "      bash cleanup-old-scripts.sh --force"
    echo ""
else
    echo ">>> --force given – performing moves..."
    mkdir -p "$OLD_DIR"
    # Keep directory structure inside old/
    for f in "${TO_MOVE[@]}"; do
        dir=$(dirname "$f")
        mkdir -p "$OLD_DIR/$dir"
        mv "$f" "$OLD_DIR/$f"
        echo "  archived  $f  →  $OLD_DIR/$f"
    done
    echo ""
    echo "Done. Archived ${#TO_MOVE[@]} file(s) into $OLD_DIR/"
    echo ""
fi

# ------------------------------------------------------------------
# 4. Report any remaining 'wyleu' references
# ------------------------------------------------------------------
echo "============================================================"
echo " Remaining 'wyleu' references in the repo (should be none"
echo " after the new gunicorn/nginx files are applied):"
echo "============================================================"

# Exclude the old/ archive and .git
HITS=$(grep -r --exclude-dir=.git --exclude-dir=old \
         -n -i "wyleu" \
         --include="*.sh" --include="*.service" --include="*.socket" \
         --include="*.conf" --include="*.lua" --include="*.md" \
         --include="*.txt" --include="*.py" \
         . 2>/dev/null || true)

if [ -z "$HITS" ]; then
    echo "  ✓ None found – clean!"
else
    echo "$HITS"
    echo ""
    echo "  (If the hits are only inside old/ or the tag message, that is fine.)"
fi

echo ""
echo "============================================================"
echo " Suggested next steps after cleanup:"
echo "============================================================"
echo "  1. Apply the new files from the tarball (or copy them in)"
echo "  2. git add -A"
echo "  3. git status          # review"
echo "  4. git commit -m \"Archive old Midori/wyleu scripts; add kiosk systemd + gunicorn/nginx steps\""
echo "  5. Then run install steps 12 → 13 → 14"
echo "============================================================"
