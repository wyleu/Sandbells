"""sandbells_sync_units.sh: copies changed systemd/ units into /etc/systemd/system.
Runs the real script against a temporary repo and destination, with fake sudo and
systemctl on PATH that only log what they were asked; nothing on this machine is
installed, enabled or restarted."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest import skipUnless

from django.test import SimpleTestCase

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "sandbells_sync_units.sh"
RESET = REPO / "sandbells_reset.sh"
SHELLCHECK = shutil.which("shellcheck")

FAKE_SUDO = '#!/bin/bash\necho "sudo $*" >> "$FAKE_LOG"\nexec "$@"\n'
# is-active: true only for the units named in $FAKE_ACTIVE
FAKE_SYSTEMCTL = """#!/bin/bash
echo "systemctl $*" >> "$FAKE_LOG"
if [ "$1" = is-active ]; then
  shift; [ "$1" = --quiet ] && shift
  for u in "$@"; do case " $FAKE_ACTIVE " in *" $u "*) ;; *) exit 3 ;; esac; done
fi
exit 0
"""

UNIT = "[Unit]\nDescription=%s\n\n[Service]\nExecStart=%s\n"


class UnitSyncTests(SimpleTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.root, self.dest, self.bin = self.tmp / "repo", self.tmp / "etc", self.tmp / "bin"
        for d in (self.root / "systemd", self.root / "install-steps", self.dest, self.bin):
            d.mkdir(parents=True)
        for name, text in (("sudo", FAKE_SUDO), ("systemctl", FAKE_SYSTEMCTL)):
            (self.bin / name).write_text(text)
            (self.bin / name).chmod(0o755)
        self.log = self.tmp / "calls.log"
        self.log.touch()
        # installed and unchanged / installed but old / timer changed / new ones
        self.unit("same.service", "/bin/true", installed="same")
        self.unit("ingest.service", "/bin/true", installed="old")
        self.unit("idle.service", "/bin/true", installed="old")
        self.unit("tick.timer", "/bin/true", installed="old")
        self.unit("newstep.service", "/bin/true")
        self.unit("newnow.service", "/bin/true")
        self.unit("newnohelper.service", "/no/such/helper")
        self.unit("newloose.service", "/bin/true")
        (self.root / "systemd" / "README.txt").write_text("not a unit\n")
        (self.root / "install-steps" / "20-x.sh").write_text(
            "sudo systemctl enable newstep.service\n"
            "sudo systemctl enable --now newnow.service\n"
            "sudo systemctl enable newnohelper.service\n")

    def unit(self, name, prog, installed=None):
        text = UNIT % (name, prog)
        (self.root / "systemd" / name).write_text(text)
        if installed == "same":
            (self.dest / name).write_text(text)
        elif installed == "old":
            (self.dest / name).write_text(text.replace("[Service]", "[Service]\n# old"))

    def run_sync(self, *args, active="same.service ingest.service tick.timer"):
        env = dict(os.environ, PATH="%s:%s" % (self.bin, os.environ["PATH"]),
                   SANDBELLS_ROOT=str(self.root), SANDBELLS_UNIT_DEST=str(self.dest),
                   FAKE_LOG=str(self.log), FAKE_ACTIVE=active)
        p = subprocess.run(["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p.stdout, self.log.read_text().splitlines()

    def changing_calls(self, calls):
        return [c for c in calls if not c.startswith("systemctl is-active")]

    def test_dry_run_changes_nothing_and_uses_no_sudo(self):
        before = {p.name: p.read_text() for p in self.dest.iterdir()}
        out, calls = self.run_sync("--dry-run")
        self.assertEqual({p.name: p.read_text() for p in self.dest.iterdir()}, before)
        self.assertEqual(self.changing_calls(calls), [])
        self.assertIn("same same.service", out)
        self.assertIn("would update ingest.service (differs)", out)
        self.assertIn("would update newstep.service (missing)", out)
        self.assertIn("-# old", out)
        self.assertIn("would run: sudo systemctl daemon-reload", out)
        self.assertIn("would run: sudo systemctl restart ingest.service tick.timer", out)
        self.assertNotIn("README", out)

    def test_installs_reloads_enables_and_restarts_only_what_changed(self):
        same = self.dest / "same.service"
        same_stat = same.stat()
        out, calls = self.run_sync()
        for p in (self.root / "systemd").glob("*.*"):
            if p.suffix != ".txt":
                self.assertEqual((self.dest / p.name).read_text(), p.read_text(), p.name)
                if p.name != same.name:
                    # install -m 0644 whatever the umask; the fixtures follow the umask
                    self.assertEqual((self.dest / p.name).stat().st_mode & 0o777, 0o644, p.name)
        # the unchanged unit is not reinstalled: same inode, mtime and mode
        self.assertEqual((same.stat().st_ino, same.stat().st_mtime_ns, same.stat().st_mode),
                         (same_stat.st_ino, same_stat.st_mtime_ns, same_stat.st_mode))
        self.assertFalse((self.dest / "README.txt").exists())
        calls = self.changing_calls(calls)
        self.assertEqual(calls.count("systemctl daemon-reload"), 1)
        self.assertNotIn("same.service", "\n".join(calls))
        self.assertIn("systemctl enable newstep.service", calls)
        self.assertIn("systemctl enable --now newnow.service", calls)
        self.assertFalse([c for c in calls if "enable" in c and ("newloose" in c or "newnohelper" in c)])
        self.assertIn("systemctl restart ingest.service tick.timer", calls)
        self.assertIn("changed idle.service: not active, not restarted", out)
        self.assertIn("new newnohelper.service: not enabled, /no/such/helper is missing", out)

    def test_skip_restart_leaves_units_to_the_caller(self):
        out, calls = self.run_sync("--skip-restart", "ingest tick.timer")
        self.assertFalse([c for c in calls if "restart" in c])
        self.assertIn("changed ingest.service: active, left for the caller to restart", out)

    def test_nothing_changed_means_no_reload(self):
        self.run_sync()
        self.log.write_text("")
        out, calls = self.run_sync()
        self.assertEqual(self.changing_calls(calls), [])
        self.assertIn("all units up to date", out)

    def test_reset_syncs_before_its_own_restart(self):
        text = RESET.read_text()
        self.assertIn('--skip-restart "$RESTART_UNITS"', text)
        self.assertLess(text.index('"$SYNC_UNITS"'), text.index("sudo systemctl restart"))

    def test_scripts_parse_and_are_executable(self):
        for s in (SCRIPT, RESET):
            self.assertTrue(os.access(s, os.X_OK), s)
            self.assertEqual(subprocess.run(["bash", "-n", str(s)]).returncode, 0, s)

    @skipUnless(SHELLCHECK, "shellcheck not installed")
    def test_shellcheck(self):
        p = subprocess.run([SHELLCHECK, str(SCRIPT), str(RESET)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout)
