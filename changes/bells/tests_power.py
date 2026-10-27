"""Reboot / Shut down on the farm status page: bells/controls.py, the page
partial, power.js.  Nothing here ever reboots anything: the sudo check and the
real command are mocked."""

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from unittest import mock, skipUnless

from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from . import controls

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

LOCAL = {"id": "sandbells", "name": "sandbells", "kind": "host", "family": "sandbells", "role": "kiosk",
         "status_url": "http://127.0.0.1/api/system-status/", "ws_url": "", "poll_hint_sec": 5}
OTHER = {"id": "sandbells2", "name": "sandbells2", "kind": "host", "family": "sandbells", "role": "kiosk",
         "status_url": "http://sandbells2.local/api/system-status/", "ws_url": "", "poll_hint_sec": 5}
PICO = {"id": "swing", "name": "swing", "kind": "pico", "family": "sandswing", "role": "",
        "status_url": "http://127.0.0.1/status", "ws_url": "", "poll_hint_sec": 5}
FARM = [LOCAL, OTHER, PICO]


def setUpModule():
    logging.getLogger("bells.controls").setLevel(logging.CRITICAL)
    logging.getLogger("django.request").setLevel(logging.CRITICAL)


def tearDownModule():
    logging.getLogger("bells.controls").setLevel(logging.NOTSET)
    logging.getLogger("django.request").setLevel(logging.NOTSET)


def permitted(rc=0):
    return mock.patch("bells.controls.subprocess.run", return_value=mock.Mock(returncode=rc))


class AddressTests(SimpleTestCase):
    def test_local_addresses(self):
        for a in ("127.0.0.1", "::1", "192.168.0.111", "10.1.2.3", "172.16.0.9", "169.254.10.1", "::ffff:192.168.1.5"):
            self.assertTrue(controls.is_local(a), a)

    def test_public_and_junk(self):
        for a in ("8.8.8.8", "2001:4860::8888", "", "unix:", "nonsense"):
            self.assertFalse(controls.is_local(a), a)

    def test_forwarded_for_uses_nginx_hop(self):
        req = mock.Mock(META={"REMOTE_ADDR": "", "HTTP_X_FORWARDED_FOR": "8.8.8.8, 192.168.0.5"})
        self.assertEqual(controls.client_ip(req), "192.168.0.5")


class ThisMachineTests(SimpleTestCase):
    def test_only_the_local_sandbells_entry(self):
        with mock.patch("bells.controls.socket.gethostname", return_value="sandbells.local"):
            self.assertTrue(controls.is_this_machine(LOCAL))
            self.assertTrue(controls.is_this_machine({"family": "sandbells", "status_url": "http://sandbells.local/x"}))
            self.assertTrue(controls.is_this_machine({"status_url": "http://localhost/x"}))
            self.assertTrue(controls.is_this_machine({"status_url": ""}))
            self.assertFalse(controls.is_this_machine(OTHER))
            self.assertFalse(controls.is_this_machine(PICO))
            self.assertFalse(controls.is_this_machine({"family": "sandbells", "status_url": "http://192.168.0.81/x"}))


class PowerViewTests(TestCase):
    def setUp(self):
        self.timer = mock.patch("bells.controls.threading.Timer").start()
        self.addCleanup(mock.patch.stopall)
        controls._pending.update(name=None, at=0.0)
        self.url = {n: reverse("control_action", args=[n]) for n in ("reboot", "poweroff")}

    def test_get_rejected(self):
        for u in self.url.values():
            self.assertEqual(self.client.get(u).status_code, 405)
        self.timer.assert_not_called()

    def test_post_without_csrf_rejected(self):
        c = Client(enforce_csrf_checks=True)
        with permitted():
            for u in self.url.values():
                self.assertEqual(c.post(u).status_code, 403)
        self.timer.assert_not_called()

    def test_post_with_csrf_schedules_reboot_after_a_delay(self):
        c = Client(enforce_csrf_checks=True)
        with mock.patch("bells.views.load_farm_instances", return_value=FARM):
            page = c.get(reverse("farm_status_index", args=[0]))
        token = page.cookies["csrftoken"].value
        with permitted() as run:
            r = c.post(self.url["reboot"], HTTP_X_CSRFTOKEN=token)
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertTrue(j["ok"])
        self.assertEqual(j["control"], "reboot")
        self.assertEqual(j["delay_s"], controls.POWER_DELAY_S)
        self.assertIn("Rebooting", j["message"])
        self.assertEqual(run.call_args[0][0], ["sudo", "-n", "-l", "/usr/bin/systemctl", "reboot"])
        self.timer.assert_called_once_with(controls.POWER_DELAY_S, controls._run_power, args=("reboot",))
        self.timer.return_value.start.assert_called_once()

    def test_poweroff_schedules_poweroff(self):
        with permitted() as run:
            r = self.client.post(self.url["poweroff"])
        self.assertEqual(r.status_code, 200)
        self.assertIn("Shutting down", r.json()["message"])
        self.assertEqual(run.call_args[0][0], ["sudo", "-n", "-l", "/usr/bin/systemctl", "poweroff"])
        self.timer.assert_called_once_with(controls.POWER_DELAY_S, controls._run_power, args=("poweroff",))

    def test_the_commands_are_exactly_these(self):
        with mock.patch("bells.controls.subprocess.Popen") as popen:
            controls._run_power("reboot")
            controls._run_power("poweroff")
        self.assertEqual([c[0][0] for c in popen.call_args_list],
                         [["sudo", "-n", "/usr/bin/systemctl", "reboot"], ["sudo", "-n", "/usr/bin/systemctl", "poweroff"]])
        self.assertTrue(all(c[1]["start_new_session"] for c in popen.call_args_list))

    def test_not_from_a_public_address(self):
        with permitted():
            r = self.client.post(self.url["reboot"], REMOTE_ADDR="8.8.8.8")
        self.assertEqual(r.status_code, 403)
        self.timer.assert_not_called()

    def test_nginx_forwarded_public_address_refused(self):
        with permitted():
            r = self.client.post(self.url["reboot"], REMOTE_ADDR="", HTTP_X_FORWARDED_FOR="192.168.0.5, 8.8.8.8")
        self.assertEqual(r.status_code, 403)

    def test_missing_sudoers_rule_says_not_enabled(self):
        with permitted(rc=1):
            for n, u in self.url.items():
                r = self.client.post(u)
                self.assertEqual(r.status_code, 503)
                self.assertFalse(r.json()["ok"])
                self.assertIn("not enabled", r.json()["error"])
                self.assertIn("step 19", r.json()["error"])
        self.timer.assert_not_called()
        self.assertIsNone(controls._pending["name"])

    def test_sudo_missing_or_hanging_is_not_enabled_too(self):
        for exc in (OSError("no sudo"), subprocess.TimeoutExpired("sudo", 5)):
            with mock.patch("bells.controls.subprocess.run", side_effect=exc):
                r = self.client.post(self.url["reboot"])
            self.assertEqual(r.status_code, 503)
            self.assertIn("not enabled", r.json()["error"])

    def test_only_one_action_in_progress(self):
        with permitted():
            self.assertEqual(self.client.post(self.url["reboot"]).status_code, 200)
            r = self.client.post(self.url["poweroff"])
            self.assertEqual(r.status_code, 409)
            self.assertIn("already in progress", r.json()["error"])
            self.assertEqual(self.client.post(self.url["reboot"]).status_code, 409)
        self.assertEqual(self.timer.call_count, 1)

    def test_a_stale_pending_action_is_forgotten(self):
        with permitted():
            self.client.post(self.url["reboot"])
            controls._pending["at"] -= controls.PENDING_TTL_S + 1
            self.assertEqual(self.client.post(self.url["reboot"]).status_code, 200)

    def test_failed_start_frees_the_slot(self):
        with permitted():
            self.client.post(self.url["reboot"])
        with mock.patch("bells.controls.subprocess.Popen", side_effect=OSError("x")):
            controls._run_power("reboot")
        with permitted():
            self.assertEqual(self.client.post(self.url["reboot"]).status_code, 200)

    def test_action_is_logged_with_the_client_address(self):
        logging.getLogger("bells.controls").setLevel(logging.WARNING)
        self.addCleanup(logging.getLogger("bells.controls").setLevel, logging.CRITICAL)
        with permitted(), self.assertLogs("bells.controls", "WARNING") as cm:
            self.client.post(self.url["reboot"], REMOTE_ADDR="192.168.0.77")
        self.assertTrue(any("control reboot accepted from 192.168.0.77" in m for m in cm.output), cm.output)

    def test_unknown_control(self):
        self.assertEqual(self.client.post(reverse("control_action", args=["laser"])).status_code, 404)

    def test_ping_answers_with_boot_id(self):
        with mock.patch("bells.controls.boot_id", return_value="abc"):
            r = self.client.get(reverse("control_ping"))
        self.assertEqual(r.json()["boot_id"], "abc")
        self.assertIn("no-store", r["Cache-Control"])
        self.assertEqual(self.client.post(reverse("control_ping")).status_code, 405)
        self.assertEqual(self.client.get(reverse("control_ping"), REMOTE_ADDR="8.8.8.8").status_code, 403)


@mock.patch("bells.views.load_farm_instances", return_value=FARM)
class FarmPagePowerTests(TestCase):
    def setUp(self):
        # These tests are about the registry entry that is "this machine", so
        # pin the host name: on a Pi really called sandbells2 the OTHER entry
        # (sandbells2.local) would otherwise count as local and show buttons.
        p = mock.patch("bells.controls.socket.gethostname", return_value="testbox")
        p.start()
        self.addCleanup(p.stop)

    def test_buttons_on_the_local_machines_page(self, _):
        r = self.client.get(reverse("farm_status_index", args=[0]))
        self.assertContains(r, 'id="power"')
        self.assertContains(r, 'data-action="reboot"')
        self.assertContains(r, 'data-action="poweroff"')
        self.assertContains(r, 'data-reboot-url="/control/reboot/"')
        self.assertContains(r, 'data-poweroff-url="/control/poweroff/"')
        self.assertContains(r, 'data-ping-url="/control/ping/"')
        self.assertContains(r, "csrfmiddlewaretoken")
        body = r.content.decode()
        self.assertTrue(re.search(r'/static/css/power\.css\?v=[0-9a-z]+"', body))
        self.assertTrue(re.search(r'/static/js/power\.js\?v=[0-9a-z]+"', body))
        self.assertIn(">Reboot</button>", body)
        self.assertIn(">Shut down</button>", body)

    def test_photo_and_power_controls_on_the_same_page(self, _):
        """farm-photos + power: the local machine's page shows its photo and the
        buttons, the buttons sit in the identity line (<div id="farm-id">) after
        farm-summary, and another machine's page has its photo but no buttons."""
        body = self.client.get(reverse("farm_status_index", args=[0])).content.decode()
        self.assertEqual(body.count('id="power"'), 1)
        self.assertRegex(body, r'<img[^>]+src="/static/img/farm/sandbells\.jpg\?v=[0-9a-z]+"')
        i_id = body.index('<div id="farm-id">')
        i_photo = body.index("/static/img/farm/sandbells.jpg")
        i_sum = body.index('id="farm-summary"')
        i_pow = body.index('id="power"')
        i_end = body.index("</header>")
        self.assertTrue(i_id < i_photo < i_sum < i_pow < i_end)
        self.assertEqual(body.count('<div id="farm-id">'), 1)
        other = self.client.get(reverse("farm_status_index", args=[1])).content.decode()
        self.assertIn("/static/img/farm/sandbells2.jpg", other)
        self.assertNotIn('id="power"', other)

    def test_no_buttons_for_other_machines_or_picos(self, _):
        for i in (1, 2):
            r = self.client.get(reverse("farm_status_index", args=[i]))
            self.assertEqual(r.status_code, 200)
            self.assertNotContains(r, 'id="power"')
            self.assertNotContains(r, "power.js")

    def test_no_red_in_the_css(self, _):
        css = (HERE / "static" / "css" / "power.css").read_text()
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        self.assertNotRegex(css, r"(?i)\bred\b")
        for h in re.findall(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b", css):
            if len(h) == 3:
                h = "".join(c * 2 for c in h)
            r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
            self.assertFalse(r > 150 and g < 0.7 * r and b < 0.7 * r, "reddish colour #" + h)


class InstallStepTests(SimpleTestCase):
    step = REPO / "install-steps" / "19-power.sh"

    def rule(self):
        m = re.search(r"^\$RUN_AS ALL=\(root\) NOPASSWD: (.*)$", self.step.read_text(), re.M)
        self.assertTrue(m)
        return m.group(1).replace("$SYSTEMCTL", "/usr/bin/systemctl")

    def test_exactly_the_two_commands(self):
        self.assertEqual(self.rule(), "/usr/bin/systemctl reboot, /usr/bin/systemctl poweroff")

    def test_validated_idempotent_and_executable(self):
        text = self.step.read_text()
        self.assertIn('"$VISUDO" -cf "$TMP"', text)
        self.assertIn("cmp -s", text)
        self.assertIn("0440", text)
        self.assertTrue(os.access(self.step, os.X_OK))
        self.assertEqual(subprocess.run(["bash", "-n", str(self.step)]).returncode, 0)

    @skipUnless(os.access("/usr/sbin/visudo", os.X_OK), "visudo not installed")
    def test_rule_passes_visudo(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".sudoers") as f:
            f.write("sandbells ALL=(root) NOPASSWD: %s\n" % self.rule())
            f.flush()
            p = subprocess.run(["/usr/sbin/visudo", "-cf", f.name], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


NODE = shutil.which("node")


@skipUnless(NODE, "node not installed")
class PowerJsTests(SimpleTestCase):
    def test_node_unit_tests(self):
        p = subprocess.run([NODE, "--test", str(HERE / "js_tests")], capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
