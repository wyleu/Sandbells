"""The display reconnects through one shared helper (static/js/reconnect_delay.js), loaded
with the same ?v={{ git_hash }} cache-busting as the other scripts, before the script that
uses it.  The schedule itself is tested in js_tests/reconnect_delay.test.js (run by
AlignJsTests / PowerJsTests with the rest of js_tests)."""
import re
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from bells.tests_align import FARM

HERE = Path(__file__).resolve().parent
JS = HERE / "static" / "js"
USERS = ("farm_status.js", "align.js", "kiosk_bells.js", "tick-ws.js")


def script_positions(body, name):
    return [m.start() for m in re.finditer(r'js/%s\?v=[0-9a-z]+"' % re.escape(name), body)]


@mock.patch("bells.views.load_farm_instances", return_value=FARM)
class ReconnectScriptTests(TestCase):
    def check(self, body, user):
        helper = script_positions(body, "reconnect_delay.js")
        users = script_positions(body, user)
        self.assertEqual(len(helper), 1, "reconnect_delay.js once, cache-busted")
        self.assertEqual(len(users), 1, user)
        self.assertLess(helper[0], users[0], "helper before %s" % user)

    def test_farm_status_page(self, _):
        body = self.client.get(reverse("farm_status_index", args=[1])).content.decode()
        self.check(body, "farm_status.js")

    def test_sandheads_alignment_page(self, _):
        body = self.client.get(reverse("farm_heads")).content.decode()
        self.check(body, "align.js")

    def test_kiosk_pages_that_extend_blank(self, _):
        body = self.client.get(reverse("home")).content.decode()
        self.check(body, "kiosk_bells.js")


class ReconnectSourceTests(SimpleTestCase):
    def test_helper_exists_and_users_call_it(self):
        self.assertTrue((JS / "reconnect_delay.js").is_file())
        for name in USERS:
            src = (JS / name).read_text()
            self.assertIn("ReconnectDelay.create()", src, name)
            self.assertNotRegex(src, r"setTimeout\([^,]+,\s*2000\)", name)
            self.assertNotRegex(src, r"Math\.min\([^)]*15000\)", name)
