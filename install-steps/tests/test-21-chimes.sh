#!/bin/bash
# Syntax, shellcheck, and a sandbox run of 21-chimes.sh with stubbed
# apt-get, dpkg, systemctl, usermod, sudo and id.  Nothing on the host
# is installed or changed.
# Run from anywhere:  bash install-steps/tests/test-21-chimes.sh

set -eu

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STEPS_DIR="$(cd "$TEST_DIR/.." && pwd)"
STEP="$STEPS_DIR/21-chimes.sh"
COMMON="$STEPS_DIR/sandbells-common.sh"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "ok: $*"; }

[ -f "$STEP" ] || fail "missing $STEP"
[ -x "$STEP" ] || fail "$STEP is not executable"

bash -n "$STEP" || fail "bash -n $STEP"
pass "bash -n"

if command -v shellcheck >/dev/null 2>&1; then
    # SC2329: functions that are called dynamically look unused to shellcheck.
    shellcheck -s bash -e SC2329 "$STEP" || fail "shellcheck $STEP"
    pass "shellcheck"
else
    echo "shellcheck not installed — skipped"
fi

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/chimes-21-XXXXXX")"
FAKE_ROOT="$WORKDIR/root"
mkdir -p "$FAKE_ROOT"
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

STUBS="$WORKDIR/stubs"
STATE="$WORKDIR/state"
FAKE_REPO="$WORKDIR/repo"
FAKE_HOME="$WORKDIR/home"
SF2_DST_DIR="$WORKDIR/usr/local/share/sounds/sf2"
BUNDLES_DIR="$FAKE_HOME/Downloads/chime-bundles"
LOG="$STATE/commands.log"

mkdir -p "$STUBS" "$STATE" "$SF2_DST_DIR" "$BUNDLES_DIR" \
    "$FAKE_REPO/install-steps" "$FAKE_REPO/systemd" \
    "$FAKE_REPO/changes" "$FAKE_REPO/Bellvirtenv/bin" \
    "$FAKE_HOME/Downloads"

cp "$STEP" "$FAKE_REPO/install-steps/21-chimes.sh"
cp "$COMMON" "$FAKE_REPO/install-steps/sandbells-common.sh"
HELPER="$STEPS_DIR/sandbells-qmidinet.sh"
[ -f "$HELPER" ] || fail "missing $HELPER"
cp "$HELPER" "$FAKE_REPO/install-steps/sandbells-qmidinet.sh"
chmod +x "$FAKE_REPO/install-steps/21-chimes.sh" "$FAKE_REPO/install-steps/sandbells-qmidinet.sh"
mkdir -p "$FAKE_REPO/systemd"
for unit in sandbells-qmidinet.service sandbells-qmidinet-select.service; do
    src="$STEPS_DIR/../systemd/$unit"
    [ -f "$src" ] || fail "missing $src"
    cp "$src" "$FAKE_REPO/systemd/$unit"
done

cat > "$FAKE_REPO/systemd/gunicorn.service" <<'EOF'
[Unit]
Description=Gunicorn daemon for Sandbells Django

[Service]
Type=notify
User=chimetest
Group=chimetest
WorkingDirectory=/tmp/not-used
EOF

: > "$FAKE_REPO/changes/manage.py"
cat > "$FAKE_REPO/Bellvirtenv/bin/python" <<'EOF'
#!/bin/bash
# Stub Django venv python: record manage.py invocations and succeed.
log="${CHIME_TEST_LOG:?}"
echo "python $*" >>"$log"
cmd=""
for arg in "$@"; do
    if [ "$arg" = "migrate" ]; then cmd=migrate; fi
    if [ "$arg" = "collectstatic" ]; then cmd=collectstatic; fi
    if [ "$arg" = "chime_load" ]; then cmd=chime_load; fi
done
# First migrate --check in a workdir fails so the step runs migrate --noinput.
check_flag=false
for arg in "$@"; do
    [ "$arg" = "--check" ] && check_flag=true
done
if [ "$cmd" = "migrate" ] && [ "$check_flag" = true ]; then
    state="${CHIME_TEST_STATE:?}/migrate-check"
    if [ -f "$state" ]; then
        exit 0
    fi
    touch "$state"
    exit 1
fi
if [ "$cmd" = "chime_load" ]; then
    echo "updated stub tune from bundle"
fi
exit 0
EOF
chmod +x "$FAKE_REPO/Bellvirtenv/bin/python"

# Already-installed package (must be skipped).
printf '%s\n' poppler-utils >"$STATE/installed.txt"
# chimetest exists, not yet in group audio
printf '%s\n' chimetest >"$STATE/groups-chimetest.txt"

cat > "$STUBS/logcmd" <<'EOF'
#!/bin/bash
echo "$*" >>"${CHIME_TEST_LOG:?}"
EOF
chmod +x "$STUBS/logcmd"

cat > "$STUBS/dpkg" <<'EOF'
#!/bin/bash
echo "dpkg $*" >>"${CHIME_TEST_LOG:?}"
if [ "${1:-}" = "-s" ]; then
    if grep -qx "$2" "${CHIME_TEST_STATE:?}/installed.txt" 2>/dev/null; then
        echo "Status: install ok installed"
        exit 0
    fi
    exit 1
fi
exit 0
EOF
chmod +x "$STUBS/dpkg"

cat > "$STUBS/apt-get" <<'EOF'
#!/bin/bash
echo "apt-get $*" >>"${CHIME_TEST_LOG:?}"
if [ "${1:-}" = "update" ]; then
    exit 0
fi
if [ "${1:-}" = "install" ]; then
    for arg in "$@"; do
        case "$arg" in
            -*|install) continue ;;
            *) echo "$arg" >>"${CHIME_TEST_STATE:?}/installed.txt" ;;
        esac
    done
    exit 0
fi
exit 1
EOF
chmod +x "$STUBS/apt-get"

cat > "$STUBS/sudo" <<'EOF'
#!/bin/bash
echo "sudo $*" >>"${CHIME_TEST_LOG:?}"
if [ "${1:-}" = "-u" ]; then
    shift 2
    exec "$@"
fi
exec "$@"
EOF
chmod +x "$STUBS/sudo"

cat > "$STUBS/usermod" <<'EOF'
#!/bin/bash
echo "usermod $*" >>"${CHIME_TEST_LOG:?}"
# usermod -aG GROUP USER
group=""
user=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        -aG|-G) group="$2"; shift 2 ;;
        -*) shift ;;
        *) user="$1"; shift ;;
    esac
done
if [ -n "$group" ] && [ -n "$user" ]; then
    file="${CHIME_TEST_STATE:?}/groups-${user}.txt"
    touch "$file"
    if ! grep -qx "$group" "$file" 2>/dev/null; then
        echo "$group" >>"$file"
    fi
fi
exit 0
EOF
chmod +x "$STUBS/usermod"

cat > "$STUBS/id" <<'EOF'
#!/bin/bash
# Identity for the sandbox: the operator is "tester"; "chimetest" is the
# gunicorn user.  Group membership is stored in $CHIME_TEST_STATE.
echo "id $*" >>"${CHIME_TEST_LOG:?}"
if [ "$#" -eq 0 ]; then
    echo "uid=1000(tester) gid=1000(tester) groups=1000(tester)"
    exit 0
fi
if [ "$1" = "-u" ]; then
    echo "1000"
    exit 0
fi
if [ "$1" = "-un" ]; then
    echo "tester"
    exit 0
fi
if [ "$1" = "-nG" ]; then
    user="${2:-tester}"
    file="${CHIME_TEST_STATE:?}/groups-${user}.txt"
    if [ -f "$file" ]; then
        tr '\n' ' ' <"$file"
        echo
        exit 0
    fi
    if [ "$user" = "tester" ]; then
        echo "tester"
        exit 0
    fi
    exit 1
fi
# id USER  (existence check)
user="$1"
if [ "$user" = "tester" ] || [ -f "${CHIME_TEST_STATE:?}/groups-${user}.txt" ]; then
    echo "uid=1001($user) gid=1001($user) groups=1001($user)"
    exit 0
fi
exit 1
EOF
chmod +x "$STUBS/id"

cat > "$STUBS/systemctl" <<'EOF'
#!/bin/bash
echo "systemctl $*" >>"${CHIME_TEST_LOG:?}"
# Do not return a User= so the step reads the unit file (the path we test).
if [ "${1:-}" = "show" ]; then
    exit 0
fi
exit 0
EOF
chmod +x "$STUBS/systemctl"

# No-op sleep so quick-mode pauses do not slow the test.
cat > "$STUBS/sleep" <<'EOF'
#!/bin/bash
exit 0
EOF
chmod +x "$STUBS/sleep"

# logger is used by sandbells-common.log; keep it quiet.
cat > "$STUBS/logger" <<'EOF'
#!/bin/bash
exit 0
EOF
chmod +x "$STUBS/logger"

# A stand-in font and one bundle (contents do not matter; python is stubbed).
printf 'SF2-STUB\n' >"$FAKE_HOME/Downloads/sandbach_bells_8.sf2"
printf 'ZIP-STUB\n' >"$BUNDLES_DIR/the-boars-head-carol.chime.zip"

# Real install(1) and cmp(1) from the host: $STUBS is first on PATH, so
# keep those names off the stub list.  The step calls `sudo install`, and
# the sudo stub execs the real install via the rest of PATH.
run_step() {
    : >"$LOG"
    rm -f "$STATE/migrate-check"
    env -i \
        PATH="$STUBS:/usr/bin:/bin" \
        HOME="$FAKE_HOME" \
        XDG_DOWNLOAD_DIR="$FAKE_HOME/Downloads" \
        CHIME_TEST_LOG="$LOG" \
        CHIME_TEST_STATE="$STATE" \
        SANDBELLS_PROJECT_DIR="$FAKE_REPO" \
        SANDBELLS_GUNICORN_UNIT="$FAKE_REPO/systemd/gunicorn.service" \
        SANDBELLS_CHIME_SOUNDFONT_DST="$SF2_DST_DIR/sandbach_bells_8.sf2" \
        SANDBELLS_CHIME_BUNDLES="$BUNDLES_DIR" \
        SANDBELLS_INSTALL_ROOT="$FAKE_ROOT" \
        USER=tester \
        LANG=C \
        "$@"
}

# ------------------------------------------------------------------
# 1. Full stubbed run (not dry-run): installs, copies, group, migrate, load
# ------------------------------------------------------------------
OUT1="$WORKDIR/run1.out"
if ! run_step "$FAKE_REPO/install-steps/21-chimes.sh" true >"$OUT1" 2>&1; then
    cat "$OUT1" >&2
    fail "first run exited non-zero"
fi
pass "first stubbed run"

grep -q "already installed: poppler-utils" "$OUT1" || fail "should skip poppler-utils"
grep -q "installing: alsa-utils fluidsynth qmidinet" "$OUT1" || {
    cat "$OUT1" >&2
    fail "should install alsa-utils, fluidsynth and qmidinet"
}
grep -q "optional: fluid-soundfont-gm" "$OUT1" || fail "should attempt optional font package"
grep -q "gunicorn runs as: chimetest" "$OUT1" || fail "should read User= from the unit"
grep -q "added chimetest to group audio" "$OUT1" || fail "should add the user to audio"
grep -q "Restart gunicorn" "$OUT1" || fail "should note a gunicorn restart is needed"
grep -q "installed $SF2_DST_DIR/sandbach_bells_8.sf2" "$OUT1" || fail "should install the soundfont"
grep -q "loading $BUNDLES_DIR/the-boars-head-carol.chime.zip" "$OUT1" || fail "should load the bundle"
grep -q "does not edit /etc/sandbells/settings.json" "$OUT1" || fail "should say it does not edit settings"

[ -f "$SF2_DST_DIR/sandbach_bells_8.sf2" ] || fail "destination soundfont missing"
[ -x "$FAKE_ROOT/usr/local/sbin/sandbells-qmidinet.sh" ] || fail "helper was not installed"
[ -f "$FAKE_ROOT/etc/systemd/system/sandbells-qmidinet.service" ] || fail "qmidinet unit was not installed"
[ -f "$FAKE_ROOT/etc/systemd/system/sandbells-qmidinet-select.service" ] || fail "select unit was not installed"
[ -f "$FAKE_ROOT/etc/systemd/system/sandbells-qmidinet.service.d/user.conf" ] || fail "user drop-in was not installed"
grep -q "^User=chimetest$" "$FAKE_ROOT/etc/systemd/system/sandbells-qmidinet.service.d/user.conf" \
    || fail "drop-in should use User= from the gunicorn unit"
grep -q "systemctl enable sandbells-qmidinet-select.service" "$LOG" \
    || fail "select unit should be enabled"
grep -q "installed $FAKE_ROOT/usr/local/sbin/sandbells-qmidinet.sh" "$OUT1" \
    || fail "first run should install the helper"
cmp -s "$FAKE_HOME/Downloads/sandbach_bells_8.sf2" "$SF2_DST_DIR/sandbach_bells_8.sf2" \
    || fail "installed soundfont does not match the source"

grep -q "apt-get install --no-install-recommends -y alsa-utils fluidsynth qmidinet" "$LOG" \
    || fail "apt-get was not called for required packages"
grep -q "apt-get install --no-install-recommends -y fluid-soundfont-gm" "$LOG" \
    || fail "apt-get was not called for the optional package"
if grep -q "apt-get install --no-install-recommends -y poppler-utils" "$LOG"; then
    fail "poppler-utils should not have been installed again"
fi
grep -q "usermod -aG audio chimetest" "$LOG" || fail "usermod was not called"
grep -q "manage.py migrate bells --noinput" "$LOG" || fail "migrate bells was not run"
grep -q "manage.py collectstatic --noinput" "$LOG" || fail "collectstatic was not run"
grep -q "manage.py chime_load $BUNDLES_DIR/the-boars-head-carol.chime.zip" "$LOG" \
    || fail "chime_load was not run"
if grep -q "settings.json" "$LOG"; then
    fail "a stubbed command touched settings.json"
fi
if grep -Eiq 'aplaymidi|amidi|aconnect' "$LOG"; then
    fail "a stubbed command touched a MIDI tool"
fi
pass "first run side effects"

# ------------------------------------------------------------------
# 2. Second run: idempotent (no apt install, no usermod, soundfont unchanged)
# ------------------------------------------------------------------
OUT2="$WORKDIR/run2.out"
# Keep installed.txt and groups as left by run 1; reset only the log / check flag.
if ! run_step "$FAKE_REPO/install-steps/21-chimes.sh" true >"$OUT2" 2>&1; then
    cat "$OUT2" >&2
    fail "second run exited non-zero"
fi
grep -q "all required packages are already installed" "$OUT2" \
    || fail "second run should skip required packages"
grep -q "already installed (optional): fluid-soundfont-gm" "$OUT2" \
    || fail "second run should skip the optional package"
grep -q "unchanged: $SF2_DST_DIR/sandbach_bells_8.sf2" "$OUT2" \
    || fail "second run should leave the soundfont in place"
grep -q "already in group audio: chimetest" "$OUT2" \
    || fail "second run should leave group membership in place"
grep -q "unchanged: $FAKE_ROOT/usr/local/sbin/sandbells-qmidinet.sh" "$OUT2" \
    || fail "second run should leave the helper in place"
grep -q "unchanged: $FAKE_ROOT/etc/systemd/system/sandbells-qmidinet.service" "$OUT2" \
    || fail "second run should leave the qmidinet unit in place"
if grep -q "apt-get install" "$LOG"; then
    fail "second run should not call apt-get install"
fi
if grep -q "usermod" "$LOG"; then
    fail "second run should not call usermod"
fi
# migrate --check now succeeds (state file written by the stub at the start
# of this run after we wipe it... wait, run_step wipes migrate-check, so
# first check fails and migrate --noinput runs again).  That is acceptable:
# the step's --check / migrate pattern is what we test on the first run.
# After --check state is new each run_step.  Do not assert migrate is skipped.
pass "second run idempotent"

# ------------------------------------------------------------------
# 3. Dry-run on a clean dest: no files written, no usermod/apt
# ------------------------------------------------------------------
SF2_DRY="$WORKDIR/dry/sf2/sandbach_bells_8.sf2"
mkdir -p "$(dirname "$SF2_DRY")"
# Fresh package/group state so dry-run would have work to do.
printf '%s\n' poppler-utils >"$STATE/installed-dry.txt"
printf '%s\n' chimetest >"$STATE/groups-chimetest.txt"
# Point the stubs at a separate log; reuse the same stubs by swapping files.
cp "$STATE/installed-dry.txt" "$STATE/installed.txt"

OUT3="$WORKDIR/run-dry.out"
: >"$LOG"
DRY_ROOT="$WORKDIR/dry/root"
if ! run_step env SANDBELLS_CHIME_DRY_RUN=1 SANDBELLS_CHIME_SOUNDFONT_DST="$SF2_DRY" \
        SANDBELLS_INSTALL_ROOT="$DRY_ROOT" \
        "$FAKE_REPO/install-steps/21-chimes.sh" true --dry-run >"$OUT3" 2>&1; then
    cat "$OUT3" >&2
    fail "dry-run exited non-zero"
fi
grep -q "dry-run: sudo apt-get install" "$OUT3" || fail "dry-run should print apt-get"
grep -q "dry-run: sudo usermod -aG audio chimetest" "$OUT3" || fail "dry-run should print usermod"
grep -q "dry-run: sudo install -D" "$OUT3" || fail "dry-run should print install"
grep -q "dry-run: sudo systemctl enable sandbells-qmidinet-select.service" "$OUT3" \
    || fail "dry-run should print enabling the select unit"
if [ -e "$DRY_ROOT" ]; then
    fail "dry-run must not write the qmidinet install root"
fi
grep -q "dry-run: .*manage.py chime_load" "$OUT3" || fail "dry-run should print chime_load"
if [ -e "$SF2_DRY" ]; then
    fail "dry-run must not write the soundfont"
fi
if grep -q "apt-get install" "$LOG"; then
    fail "dry-run must not call apt-get"
fi
if grep -q "usermod" "$LOG"; then
    fail "dry-run must not call usermod"
fi
pass "dry-run changes nothing"

# ------------------------------------------------------------------
# 4. Missing soundfont and missing bundles dir: warn and continue
# ------------------------------------------------------------------
OUT4="$WORKDIR/run-missing.out"
MISSING_DST="$WORKDIR/missing/sf2/sandbach_bells_8.sf2"
mkdir -p "$(dirname "$MISSING_DST")"
# Required packages already installed so we do not care about apt.
if ! run_step env \
        SANDBELLS_CHIME_SOUNDFONT_DST="$MISSING_DST" \
        SANDBELLS_CHIME_BUNDLES="$WORKDIR/no-such-bundles" \
        HOME="$WORKDIR/empty-home" \
        XDG_DOWNLOAD_DIR="$WORKDIR/empty-home/Downloads" \
        "$FAKE_REPO/install-steps/21-chimes.sh" true >"$OUT4" 2>&1; then
    cat "$OUT4" >&2
    fail "missing-assets run exited non-zero"
fi
grep -q "WARNING: sandbach_bells_8.sf2 not found" "$OUT4" \
    || fail "should warn when the soundfont is missing"
grep -q "no directory $WORKDIR/no-such-bundles" "$OUT4" \
    || fail "should skip a missing bundles directory"
[ ! -e "$MISSING_DST" ] || fail "should not invent a soundfont"
pass "missing soundfont and bundles warn and continue"

echo "All 21-chimes.sh sandbox tests passed."
