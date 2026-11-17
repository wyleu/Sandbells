"""Install step 21 (Chimes player packages, soundfont, audio group, qmidinet, bundles).

Nothing here installs packages or changes the host: bash -n, a few text
guards, the stubbed sandbox in install-steps/tests/test-21-chimes.sh, and
the interface-choice tests in install-steps/tests/test-sandbells-qmidinet.sh.
"""

import os
import re
import subprocess
from pathlib import Path

from django.test import SimpleTestCase

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STEP = REPO / "install-steps" / "21-chimes.sh"
SANDBOX = REPO / "install-steps" / "tests" / "test-21-chimes.sh"
QMIDINET_HELPER = REPO / "install-steps" / "sandbells-qmidinet.sh"
QMIDINET_SANDBOX = REPO / "install-steps" / "tests" / "test-sandbells-qmidinet.sh"
# HERE is changes/bells; parents[1] is the Sandbells repo root (same as tests_power.py).


class ChimesInstallStepTests(SimpleTestCase):
    def test_executable_and_syntax(self):
        self.assertTrue(STEP.is_file())
        self.assertTrue(os.access(STEP, os.X_OK))
        self.assertEqual(subprocess.run(["bash", "-n", str(STEP)], check=False).returncode, 0)

    def test_named_constants_not_a_hard_coded_user(self):
        text = STEP.read_text()
        self.assertIn("REQUIRED_PACKAGES=", text)
        self.assertIn("alsa-utils", text)
        self.assertIn("poppler-utils", text)
        self.assertIn("fluidsynth", text)
        self.assertIn("qmidinet", text)
        self.assertIn("QMIDINET_HELPER_NAME=", text)
        self.assertIn("sandbells-qmidinet.sh", text)
        self.assertIn("sandbells-qmidinet.service", text)
        self.assertIn("sandbells-qmidinet-select.service", text)
        self.assertIn("group_from_unit", text)
        self.assertIn("OPTIONAL_PACKAGES=", text)
        self.assertIn("fluid-soundfont-gm", text)
        self.assertIn("SOUNDFONT_NAME=", text)
        self.assertIn("sandbach_bells_8.sf2", text)
        self.assertIn("/usr/local/share/sounds/sf2/", text)
        self.assertIn('AUDIO_GROUP="audio"', text)
        self.assertIn("user_from_unit", text)
        self.assertIn("User=", text)
        self.assertIn("usermod -aG", text)
        # The gunicorn user comes from the unit, never a literal usermod ... sandbells.
        self.assertIsNone(re.search(r"usermod\s+-aG\s+\S+\s+sandbells\b", text))
        self.assertIn("migrate bells", text)
        self.assertIn("collectstatic", text)
        self.assertIn("chime_load", text)
        self.assertIn("*.chime.zip", text)
        self.assertIn("SANDBELLS_CHIME_BUNDLES", text)
        self.assertIn("SANDBELLS_CHIME_SOUNDFONT", text)

    def test_does_not_rewrite_settings_or_touch_midi_ports(self):
        text = STEP.read_text()
        self.assertIn("does not edit /etc/sandbells/settings.json", text.lower())
        self.assertIn("Pico", text)
        # No write/copy/edit of the live settings file.
        self.assertIsNone(re.search(
            r"""(?:\bcp\b|\binstall\b|\btee\b|\bsed\b|\bjq\b)\s+[^
]*settings\.json""",
            text,
        ))
        self.assertNotIn("aplaymidi -l", text)
        self.assertNotIn("aplaymidi -p", text)
        self.assertNotIn("amidi", text)
        self.assertNotIn("aconnect", text)

    def test_sandbox_with_stubbed_apt_and_systemctl(self):
        self.assertTrue(os.access(SANDBOX, os.X_OK))
        p = subprocess.run(
            ["bash", str(SANDBOX)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_qmidinet_helper_and_interface_choice(self):
        self.assertTrue(QMIDINET_HELPER.is_file())
        self.assertTrue(os.access(QMIDINET_HELPER, os.X_OK))
        self.assertEqual(
            subprocess.run(["bash", "-n", str(QMIDINET_HELPER)], check=False).returncode, 0)
        self.assertTrue(os.access(QMIDINET_SANDBOX, os.X_OK))
        p = subprocess.run(
            ["bash", str(QMIDINET_SANDBOX)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
