#!/bin/bash
# 21-chimes.sh
# Packages and assets the Chimes player needs, plus loading tune bundles.
#
#   * alsa-utils (aplaymidi) for MIDI out
#   * poppler-utils (pdftoppm) for page images (also installed by step 05)
#   * fluidsynth for HDMI audio of the bell samples
#   * fluid-soundfont-gm, optional fallback font if the 8-bell font is missing
#   * sandbach_bells_8.sf2 into /usr/local/share/sounds/sf2/ when a source
#     file is given or found (repo assets or ~/Downloads); warn and continue
#     if it is not found (HDMI audio then uses the GM fallback, or stays off)
#   * the gunicorn service user (User= from the systemd unit, never a
#     hard-coded name) added to group audio, so ALSA seq and HDMI work
#   * migrate bells + collectstatic, so the step can be run on its own
#   * every *.chime.zip in a configurable directory (default
#     ~/Downloads/chime-bundles) loaded with manage.py chime_load
#
# Does not edit /etc/sandbells/settings.json.  Does not open or write any
# MIDI port (the Pico's port is never touched).
#
# Idempotent and safe to re-run.  master_install runs every
# install-steps/[0-9][0-9]-*.sh, so it needs no edit there.  By hand,
# after a pull, on sandbells2:
#   bash ~/Code/Sandbells/install-steps/21-chimes.sh true
# Optional:
#   SANDBELLS_CHIME_SOUNDFONT=/path/to/sandbach_bells_8.sf2
#   SANDBELLS_CHIME_BUNDLES=$HOME/Downloads/chime-bundles
#   SANDBELLS_GUNICORN_UNIT=/path/to/gunicorn.service
#   SANDBELLS_PROJECT_DIR=/path/to/Sandbells
#   SANDBELLS_CHIME_DRY_RUN=1   (or --dry-run: print actions, change nothing)
#
# Args: $1 = QUICK_MODE (true/false), as passed by master_install.sh.
#       Also accepted: --dry-run, --soundfont=PATH, --bundles=DIR.

QUICK_MODE=false
DRY_RUN=false
SOUNDFONT_SRC_ARG=""
BUNDLES_ARG=""

for arg in "$@"; do
    case "$arg" in
        true|TRUE|--quick|-q) QUICK_MODE=true ;;
        false|FALSE) QUICK_MODE=false ;;
        --dry-run) DRY_RUN=true ;;
        --soundfont=*) SOUNDFONT_SRC_ARG="${arg#--soundfont=}" ;;
        --bundles=*) BUNDLES_ARG="${arg#--bundles=}" ;;
        --*)
            echo "ERROR: unknown option $arg"
            exit 1
            ;;
    esac
done

case "${SANDBELLS_CHIME_DRY_RUN:-}" in
    1|true|TRUE|yes|YES) DRY_RUN=true ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck source=/dev/null
[ -f "$SCRIPT_DIR/sandbells-common.sh" ] && source "$SCRIPT_DIR/sandbells-common.sh"

# ---------------------------------------------------------------------------
# Named constants (no magic numbers or hard-coded user names)
# ---------------------------------------------------------------------------
PROJECT_DIR="${SANDBELLS_PROJECT_DIR:-$REPO_DIR}"
VENV_PY="${SANDBELLS_VENV_PY:-$PROJECT_DIR/Bellvirtenv/bin/python}"
CHANGES_DIR="${PROJECT_DIR}/changes"
MANAGE_PY="${CHANGES_DIR}/manage.py"

INSTALLED_GUNICORN_UNIT="/etc/systemd/system/gunicorn.service"
REPO_GUNICORN_UNIT="${REPO_DIR}/systemd/gunicorn.service"
USER_NAME_RE='^[a-z_][a-z0-9_-]*$'

AUDIO_GROUP="audio"
GUNICORN_RESTART_CMD="sudo systemctl restart gunicorn"

REQUIRED_PACKAGES=(
    alsa-utils        # aplaymidi: MIDI out
    poppler-utils     # pdftoppm: tune PDFs -> page images
    fluidsynth        # HDMI audio of the bell samples
)
OPTIONAL_PACKAGES=(
    fluid-soundfont-gm    # FluidR3_GM.sf2 fallback; missing package is not a failure
)

SOUNDFONT_NAME="sandbach_bells_8.sf2"
SOUNDFONT_DST_DEFAULT="/usr/local/share/sounds/sf2/${SOUNDFONT_NAME}"
SOUNDFONT_DST="${SANDBELLS_CHIME_SOUNDFONT_DST:-$SOUNDFONT_DST_DEFAULT}"
SOUNDFONT_DST_MODE="644"

DOWNLOADS_DIR="${XDG_DOWNLOAD_DIR:-$HOME/Downloads}"
DEFAULT_BUNDLES_DIR="${DOWNLOADS_DIR}/chime-bundles"
BUNDLE_SUFFIX=".chime.zip"

# Seconds to wait at each pause() in quick mode (same idea as steps 19 and 20).
QUICK_PAUSE_S=1

if ! type package_installed &>/dev/null; then
    package_installed() { dpkg -s "$1" &>/dev/null; }
fi

if ! type pause &>/dev/null; then
    pause() {
        if [ "$QUICK_MODE" = true ]; then
            sleep "$QUICK_PAUSE_S"
            return
        fi
        echo ""
        read -r -p "Press Enter to continue (or Q to stop) > " choice
        if [[ "$choice" =~ ^[Qq]$ ]]; then
            echo "Setup stopped safely."
            exit 1
        fi
    }
fi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
run() {
    if [ "$DRY_RUN" = true ]; then
        echo "  dry-run: $*"
        return 0
    fi
    "$@"
}

pick_gunicorn_unit() {
    if [ -n "${SANDBELLS_GUNICORN_UNIT:-}" ]; then
        printf '%s\n' "$SANDBELLS_GUNICORN_UNIT"
        return
    fi
    if [ -f "$INSTALLED_GUNICORN_UNIT" ]; then
        printf '%s\n' "$INSTALLED_GUNICORN_UNIT"
        return
    fi
    printf '%s\n' "$REPO_GUNICORN_UNIT"
}

user_from_unit() {
    # The User= line of a systemd service file (last one wins).
    sed -n 's/^[[:space:]]*User=[[:space:]]*\([^[:space:]]*\).*/\1/p' "$1" | tail -n 1
}

user_in_group() {
    local user="$1" group="$2"
    local -a groups=()
    local g
    read -r -a groups < <(id -nG "$user" 2>/dev/null) || return 1
    for g in "${groups[@]}"; do
        if [ "$g" = "$group" ]; then
            return 0
        fi
    done
    return 1
}

as_app() {
    # Run a command as the gunicorn service user, like step 18.
    if [ "$(id -un)" = "$RUN_AS" ]; then
        "$@"
    else
        sudo -u "$RUN_AS" "$@"
    fi
}

downloads_search_paths() {
    # Possible locations of sandbach_bells_8.sf2 (first existing file wins).
    printf '%s\n' \
        "$REPO_DIR/assets/sounds/sf2/$SOUNDFONT_NAME" \
        "$REPO_DIR/install-steps/assets/$SOUNDFONT_NAME" \
        "$DOWNLOADS_DIR/$SOUNDFONT_NAME" \
        "$DOWNLOADS_DIR/sounds/sf2/$SOUNDFONT_NAME"
}

find_soundfont_source() {
    local path
    if [ -n "$SOUNDFONT_SRC_ARG" ]; then
        if [ -f "$SOUNDFONT_SRC_ARG" ]; then
            printf '%s\n' "$SOUNDFONT_SRC_ARG"
            return 0
        fi
        echo "WARNING: --soundfont is not a file: $SOUNDFONT_SRC_ARG" >&2
        return 1
    fi
    if [ -n "${SANDBELLS_CHIME_SOUNDFONT:-}" ]; then
        if [ -f "$SANDBELLS_CHIME_SOUNDFONT" ]; then
            printf '%s\n' "$SANDBELLS_CHIME_SOUNDFONT"
            return 0
        fi
        echo "WARNING: SANDBELLS_CHIME_SOUNDFONT is not a file: $SANDBELLS_CHIME_SOUNDFONT" >&2
        return 1
    fi
    while IFS= read -r path; do
        if [ -f "$path" ]; then
            printf '%s\n' "$path"
            return 0
        fi
    done < <(downloads_search_paths)
    return 1
}

echo "=================================================="
echo " 21 – Chimes player (MIDI out, HDMI audio, bundles)"
echo "=================================================="
if [ "$DRY_RUN" = true ]; then
    echo "  dry-run: no packages, files, groups or Django commands will be changed"
fi

# ---------------------------------------------------------------------------
# 1. Packages
# ---------------------------------------------------------------------------
echo "[1/5] Packages (skip if already installed)..."
TO_INSTALL=()
for pkg in "${REQUIRED_PACKAGES[@]}"; do
    if package_installed "$pkg"; then
        echo "  already installed: $pkg"
    else
        TO_INSTALL+=("$pkg")
    fi
done

if [ ${#TO_INSTALL[@]} -eq 0 ]; then
    echo "  all required packages are already installed"
else
    echo "  installing: ${TO_INSTALL[*]}"
    run sudo apt-get update -qq
    if [ "$DRY_RUN" = true ]; then
        echo "  dry-run: sudo apt-get install --no-install-recommends -y ${TO_INSTALL[*]}"
    else
        sudo apt-get install --no-install-recommends -y "${TO_INSTALL[@]}" \
            || { echo "ERROR: apt failed to install: ${TO_INSTALL[*]}"; exit 1; }
    fi
fi

for pkg in "${OPTIONAL_PACKAGES[@]}"; do
    if package_installed "$pkg"; then
        echo "  already installed (optional): $pkg"
    else
        echo "  optional: $pkg"
        if [ "$DRY_RUN" = true ]; then
            echo "  dry-run: sudo apt-get install --no-install-recommends -y $pkg"
        elif sudo apt-get install --no-install-recommends -y "$pkg"; then
            echo "  installed (optional): $pkg"
        else
            echo "  WARNING: optional package $pkg was not installed (HDMI audio can use the 8-bell font if present)"
        fi
    fi
done
pause

# ---------------------------------------------------------------------------
# 2. Sandbach 8-bell soundfont
# ---------------------------------------------------------------------------
echo "[2/5] Soundfont $SOUNDFONT_NAME -> $SOUNDFONT_DST"
SOUNDFONT_SRC=""
if SOUNDFONT_SRC="$(find_soundfont_source)"; then
    echo "  source: $SOUNDFONT_SRC"
    if [ -f "$SOUNDFONT_DST" ] && cmp -s "$SOUNDFONT_SRC" "$SOUNDFONT_DST"; then
        echo "  unchanged: $SOUNDFONT_DST"
    else
        if [ "$DRY_RUN" = true ]; then
            echo "  dry-run: sudo install -D -m $SOUNDFONT_DST_MODE $SOUNDFONT_SRC $SOUNDFONT_DST"
        else
            sudo install -D -m "$SOUNDFONT_DST_MODE" "$SOUNDFONT_SRC" "$SOUNDFONT_DST"
            echo "  installed $SOUNDFONT_DST"
        fi
    fi
else
    if [ -f "$SOUNDFONT_DST" ]; then
        echo "  already present: $SOUNDFONT_DST (no new source found)"
    else
        echo "  WARNING: $SOUNDFONT_NAME not found (looked in repo assets and $DOWNLOADS_DIR)"
        echo "  HDMI audio will use FluidR3_GM if fluid-soundfont-gm is installed, else stay off."
        echo "  To install the 8-bell font later:"
        echo "    sudo install -D -m $SOUNDFONT_DST_MODE /path/to/$SOUNDFONT_NAME $SOUNDFONT_DST_DEFAULT"
    fi
fi
pause

# ---------------------------------------------------------------------------
# 3. gunicorn user -> group audio
# ---------------------------------------------------------------------------
echo "[3/5] gunicorn user in group $AUDIO_GROUP..."
UNIT_SRC="$(pick_gunicorn_unit)"
[ -f "$UNIT_SRC" ] || { echo "ERROR: missing gunicorn unit: $UNIT_SRC"; exit 1; }
RUN_AS="$(user_from_unit "$UNIT_SRC")"
if ! [[ "$RUN_AS" =~ $USER_NAME_RE ]]; then
    echo "ERROR: no usable User= in $UNIT_SRC"
    exit 1
fi
echo "  gunicorn runs as: $RUN_AS  (from $UNIT_SRC)"

ADDED_TO_AUDIO=false
if [ "$DRY_RUN" = true ]; then
    if id "$RUN_AS" >/dev/null 2>&1 && user_in_group "$RUN_AS" "$AUDIO_GROUP"; then
        echo "  already in group $AUDIO_GROUP: $RUN_AS"
    else
        echo "  dry-run: sudo usermod -aG $AUDIO_GROUP $RUN_AS"
        ADDED_TO_AUDIO=true
    fi
else
    id "$RUN_AS" >/dev/null 2>&1 || { echo "ERROR: user $RUN_AS does not exist"; exit 1; }
    if user_in_group "$RUN_AS" "$AUDIO_GROUP"; then
        echo "  already in group $AUDIO_GROUP: $RUN_AS"
    else
        sudo usermod -aG "$AUDIO_GROUP" "$RUN_AS"
        ADDED_TO_AUDIO=true
        echo "  added $RUN_AS to group $AUDIO_GROUP"
    fi
fi
if [ "$ADDED_TO_AUDIO" = true ]; then
    echo "  group membership is picked up on the next login or service start."
    echo "  Restart gunicorn so the player can use ALSA / HDMI:"
    echo "    $GUNICORN_RESTART_CMD"
    echo "  (this step does not restart it)"
fi
pause

# ---------------------------------------------------------------------------
# 4. migrate bells + collectstatic (same pattern as step 18, so this
#    step can be run on its own after a pull)
# ---------------------------------------------------------------------------
echo "[4/5] Django migrate bells + collectstatic..."
if [ ! -x "$VENV_PY" ]; then
    echo "ERROR: no venv at $VENV_PY (run step 12 first)"
    exit 1
fi
if [ ! -f "$MANAGE_PY" ]; then
    echo "ERROR: missing $MANAGE_PY"
    exit 1
fi
if [ "$DRY_RUN" = true ]; then
    echo "  dry-run: cd $CHANGES_DIR && $VENV_PY manage.py migrate bells --check || migrate --noinput"
    echo "  dry-run: $VENV_PY manage.py collectstatic --noinput"
else
    cd "$CHANGES_DIR" || { echo "ERROR: $CHANGES_DIR missing"; exit 1; }
    if as_app "$VENV_PY" manage.py migrate bells --check >/dev/null 2>&1; then
        echo "  bells migrations up to date"
    else
        as_app "$VENV_PY" manage.py migrate bells --noinput \
            || { echo "ERROR: migrate bells failed"; exit 1; }
    fi
    if as_app "$VENV_PY" manage.py collectstatic --noinput >/dev/null; then
        echo "  static files collected"
    else
        echo "  WARNING: collectstatic failed"
    fi
fi
pause

# ---------------------------------------------------------------------------
# 5. Load *.chime.zip bundles
# ---------------------------------------------------------------------------
if [ -n "$BUNDLES_ARG" ]; then
    BUNDLES_DIR="$BUNDLES_ARG"
elif [ -n "${SANDBELLS_CHIME_BUNDLES:-}" ]; then
    BUNDLES_DIR="$SANDBELLS_CHIME_BUNDLES"
else
    BUNDLES_DIR="$DEFAULT_BUNDLES_DIR"
fi

echo "[5/5] Loading Chimes bundles from $BUNDLES_DIR"
if [ ! -d "$BUNDLES_DIR" ]; then
    echo "  no directory $BUNDLES_DIR — skipped (set SANDBELLS_CHIME_BUNDLES or --bundles=DIR)"
else
    shopt -s nullglob
    BUNDLES=( "$BUNDLES_DIR"/*"$BUNDLE_SUFFIX" )
    shopt -u nullglob
    if [ ${#BUNDLES[@]} -eq 0 ]; then
        echo "  no *$BUNDLE_SUFFIX in $BUNDLES_DIR — skipped"
    else
        if [ "$DRY_RUN" = true ]; then
            for bundle in "${BUNDLES[@]}"; do
                echo "  dry-run: $VENV_PY manage.py chime_load $bundle"
            done
        else
            cd "$CHANGES_DIR" || { echo "ERROR: $CHANGES_DIR missing"; exit 1; }
            for bundle in "${BUNDLES[@]}"; do
                echo "  loading $bundle"
                if as_app "$VENV_PY" manage.py chime_load "$bundle"; then
                    :
                else
                    echo "  WARNING: chime_load failed for $bundle"
                fi
            done
        fi
    fi
fi

echo ""
echo "Chimes install step completed."
echo "  This step does not edit /etc/sandbells/settings.json and does not"
echo "  open or write any MIDI port (the Pico's port is never touched)."
if [ "$ADDED_TO_AUDIO" = true ]; then
    echo "  Next: $GUNICORN_RESTART_CMD"
fi
pause
