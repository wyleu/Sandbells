#!/bin/bash
# =============================================================================
# sandbells_sync_units.sh
#
# Generic Sandbells helper: bring the installed systemd unit files in
# /etc/systemd/system up to date with the repo's systemd/ directory.
#
# Why it exists
# -------------
# A `git pull` updates systemd/*.service in the checkout, but systemd only
# reads the copies under /etc/systemd/system, which the numbered install
# steps made once.  Seen: sandbells-ingest.service stayed old (no
# RuntimeDirectory=sandbells-ingest), so /run/sandbells-ingest/link.json was
# never written and the page said "ingest not running".
#
# What it does
# ------------
#   - every unit file in systemd/ (*.service, *.socket, *.timer, ...) is
#     compared with $DEST/<name> (cmp -s); missing or different ones are
#     installed with `install -m 0644` and listed as "updated <name>",
#     the rest as "same <name>"
#   - systemctl daemon-reload, only if something was updated
#   - a unit that was not installed before is enabled only if one of the
#     install-steps/NN-*.sh enables it (with --now if that step uses --now),
#     and only if its ExecStart= program is already there; units that were
#     already installed keep their enabled/disabled state
#   - a changed unit that is active now is restarted (a changed timer:
#     the timer is restarted); unchanged units are never touched
#
# Layout it assumes (override with env if yours differs)
# ------------------------------------------------------
#   $SANDBELLS_ROOT       default: the directory this script is in
#   $SANDBELLS_UNIT_DEST  default: /etc/systemd/system
#
# Usage
# -----
#   ./sandbells_sync_units.sh --dry-run    # what would change; no sudo, no changes
#   ./sandbells_sync_units.sh
#   ./sandbells_sync_units.sh --skip-restart "gunicorn sandbells-kiosk"
#       (still installs, reloads and enables; leaves those units for the
#        caller to restart -- sandbells_reset.sh uses this)
#
# Needs sudo for install/systemctl (not with --dry-run).  Does not pull git,
# install helper scripts from install-steps/, or reboot.
# =============================================================================

set -euo pipefail

ROOT="${SANDBELLS_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
SRC="${ROOT}/systemd"
STEPS="${ROOT}/install-steps"
DEST="${SANDBELLS_UNIT_DEST:-/etc/systemd/system}"
UNIT_MODE="0644"
UNIT_SUFFIXES="service socket timer path mount automount target slice"
LOGTAG="sandbells-sync-units"

log() { echo "[$LOGTAG] $*"; }
usage() { sed -n 's/^#   \(\.\/sandbells_sync_units\.sh.*\)/  \1/p' "${BASH_SOURCE[0]}"; }

DRY_RUN=false
SKIP_RESTART=""
while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run|-n) DRY_RUN=true ;;
        --skip-restart)
            [ $# -ge 2 ] || { log "ERROR: --skip-restart needs a list of units"; exit 2; }
            SKIP_RESTART="$2"; shift ;;
        --skip-restart=*) SKIP_RESTART="${1#*=}" ;;
        -h|--help) usage; exit 0 ;;
        *) log "ERROR: unknown argument: $1"; usage; exit 2 ;;
    esac
    shift
done

# "gunicorn" means gunicorn.service, as systemctl reads it
SKIP_UNITS=" "
for u in ${SKIP_RESTART//,/ }; do
    case "$u" in *.*) ;; *) u="${u}.service" ;; esac
    SKIP_UNITS="${SKIP_UNITS}${u} "
done

if [ ! -d "$SRC" ]; then
    log "ERROR: no unit directory: $SRC"
    exit 1
fi
if [ ! -d "$DEST" ]; then
    log "ERROR: no destination directory: $DEST"
    exit 1
fi

is_unit_file() {
    local s
    for s in $UNIT_SUFFIXES; do
        case "$1" in *."$s") return 0 ;; esac
    done
    return 1
}

# install step that enables $1, and how: prints "<step> now" / "<step> plain"
enabling_step() {
    local name="$1" step line
    [ -d "$STEPS" ] || return 1
    for step in "$STEPS"/[0-9][0-9]-*.sh; do
        [ -f "$step" ] || continue
        line=$(grep -E "systemctl enable( --now)? +${name//./\\.}([[:space:]]|$)" "$step" | head -n 1) || continue
        case "$line" in
            *"enable --now"*) echo "$(basename "$step") now" ;;
            *) echo "$(basename "$step") plain" ;;
        esac
        return 0
    done
    return 1
}

# first ExecStart= program of unit file $1 (absolute path), empty if none
exec_program() {
    sed -n 's/^ExecStart=[-@:+!]*\([^[:space:]]*\).*/\1/p' "$1" | head -n 1
}

run() {
    if [ "$DRY_RUN" = true ]; then
        log "would run: $*"
    else
        "$@"
    fi
}

log "src=$SRC"
log "dest=$DEST"
[ "$DRY_RUN" = true ] && log "dry run: nothing is changed"

CHANGED=()
NEW=()
for src in "$SRC"/*; do
    [ -f "$src" ] || continue
    name=$(basename "$src")
    is_unit_file "$name" || continue
    dst="${DEST}/${name}"
    if [ -f "$dst" ] && cmp -s "$src" "$dst"; then
        log "same $name"
        continue
    fi
    if [ -f "$dst" ]; then why="differs"; else why="missing"; NEW+=("$name"); fi
    CHANGED+=("$name")
    if [ "$DRY_RUN" = true ]; then
        log "would update $name ($why)"
        if [ -f "$dst" ]; then
            diff -u "$dst" "$src" | sed 's/^/    /' || true
        fi
    else
        sudo install -m "$UNIT_MODE" "$src" "$dst"
        log "updated $name ($why)"
    fi
done

if [ ${#CHANGED[@]} -eq 0 ]; then
    log "all units up to date; no daemon-reload, nothing restarted"
    exit 0
fi

run sudo systemctl daemon-reload

for name in "${NEW[@]}"; do
    if ! how=$(enabling_step "$name"); then
        log "new $name: not enabled (no install step enables it)"
        continue
    fi
    step="${how% *}"
    prog=$(exec_program "${SRC}/${name}")
    if [ -n "$prog" ] && [ ! -x "$prog" ]; then
        log "new $name: not enabled, $prog is missing (run install-steps/$step)"
        continue
    fi
    if [ "${how##* }" = now ]; then
        run sudo systemctl enable --now "$name"
        log "new $name: enabled and started, as $step does"
    else
        run sudo systemctl enable "$name"
        log "new $name: enabled, as $step does (starts at next boot)"
    fi
done

RESTART=()
for name in "${CHANGED[@]}"; do
    case " ${NEW[*]} " in *" $name "*) continue ;; esac
    if ! systemctl is-active --quiet "$name"; then
        log "changed $name: not active, not restarted"
        continue
    fi
    case "$SKIP_UNITS" in
        *" $name "*) log "changed $name: active, left for the caller to restart" ;;
        *) RESTART+=("$name") ;;
    esac
done
if [ ${#RESTART[@]} -gt 0 ]; then
    run sudo systemctl restart "${RESTART[@]}"
    if [ "$DRY_RUN" = false ]; then
        log "restarted: ${RESTART[*]}"
        systemctl is-active "${RESTART[@]}" | paste -sd' ' - || true
    fi
fi
log "done (${#CHANGED[@]} changed)"
