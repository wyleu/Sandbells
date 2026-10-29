"""The Strokes page (/events/strokes/, events/strokes.html): the live stroke list on a
top-level page of its own, the full screen wide, with a Strokes button in the shared top
line (events/templatetags/events_live.py top_menu).  It must not ask any device for its
/status (the sandswing Pico's ~7 kB reply is what runs it out of memory): no
/api/farm/device-status/ proxy, no /api/system-status/, no socket to a Pico.  The page's
own scripts are run for two minutes of page time by js_tests/page_requests.js (fake DOM,
fetch and WebSocket) and every request they make is checked."""
import json
import re
import shutil
import subprocess
from pathlib import Path
from unittest import mock, skipUnless
from urllib.parse import urlparse

from django.test import TestCase
from django.urls import reverse

HERE = Path(__file__).resolve().parent
HARNESS = HERE / "js_tests" / "page_requests.js"
STATIC_DIRS = [str(HERE.parent / "bells" / "static"), str(HERE / "static")]
NODE = shutil.which("node")
NODE_TIMEOUT_S = 60

PICO_STATUS = "http://192.168.0.81/status"
PICO_WS = "ws://192.168.0.81/ws"
FARM = [{"id": "sandbells", "name": "sandbells", "family": "sandbells", "kind": "host",
         "status_url": "http://127.0.0.1/api/system-status/", "ws_url": "", "poll_hint_sec": 5},
        {"id": "sandswing", "name": "sandswing", "family": "sandswing", "kind": "pico",
         "status_url": PICO_STATUS, "alt_status_urls": ["http://10.0.0.81/status"],
         "ws_url": PICO_WS, "poll_hint_sec": 5}]
ALLOWED = {"/events/api/since/", "/events/api/link/"}


def run_page(body):
    p = subprocess.run([NODE, str(HARNESS)] + STATIC_DIRS, input=body, capture_output=True,
                       text=True, timeout=NODE_TIMEOUT_S)
    assert p.returncode == 0, p.stdout + p.stderr
    return json.loads(p.stdout)


@mock.patch("bells.views.load_farm_instances", return_value=FARM)
class StrokesMenuButtonTests(TestCase):
    def test_every_top_line_has_the_strokes_button(self, _):
        want = 'class="navbtn strokes" href="%s">Strokes</a>' % reverse("events:strokes")
        for url in (reverse("farm_status_index", args=[0]), reverse("farm_status_index", args=[1]),
                    reverse("farm_heads"), reverse("events:days")):
            self.assertContains(self.client.get(url), want, count=1, msg_prefix=url)

    def test_button_sits_after_sandheads_before_rings_by_day(self, _):
        body = self.client.get(reverse("farm_status_index", args=[0])).content.decode()
        self.assertLess(body.index(">sandheads</a>"), body.index(">Strokes</a>"))
        self.assertLess(body.index(">Strokes</a>"), body.index(">Rings by day</a>"))

    def test_strokes_page_marks_itself_gold_and_nothing_else(self, _):
        r = self.client.get(reverse("events:strokes"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'class="navbtn strokes on"', count=1)
        self.assertNotContains(r, 'class="navbtn on"')
        self.assertNotContains(r, 'class="navbtn heads on"')
        self.assertNotContains(r, 'class="navbtn days on"')
        self.assertContains(r, "a.navbtn.on {")
        for j in range(len(FARM)):
            self.assertContains(r, 'href="%s"' % reverse("farm_status_index", args=[j]))
        self.assertContains(r, 'id="live-events"', count=1)
        self.assertNotContains(r, "{#")

    def test_full_width_layout(self, _):
        r = self.client.get(reverse("events:strokes"))
        self.assertContains(r, 'grid-template-areas: "top link head" "list list list"')
        self.assertNotContains(r, "with-live")                    # no half-screen column
        self.assertNotContains(r, 'id="farm-main"')

    def test_no_concentrator_no_button(self, _):
        with mock.patch("bells.views.load_farm_instances", return_value=FARM[:1]):
            r = self.client.get(reverse("farm_status_index", args=[0]))
            self.assertNotContains(r, ">Strokes</a>")


@mock.patch("bells.views.load_farm_instances", return_value=FARM)
class StrokesPageNoStatusTests(TestCase):
    def test_page_names_no_status_endpoint_device_address_or_socket(self, _):
        body = self.client.get(reverse("events:strokes")).content.decode()
        for bad in (reverse("farm_device_status"), reverse("system_status"), "device-status",
                    "system-status", "status_url", "statusUrl", "FarmStatus",
                    "farm_status.js", "WebSocket", "EventSource", "XMLHttpRequest",
                    "192.168.0.81", "10.0.0.81", "<script src"):
            self.assertFalse(bad in body, bad)
        # /status anywhere but the menu's links to the farm pages (/farm/status/<n>/)
        self.assertEqual(re.findall(r"(?<!/farm)/status", body), [])

    def test_serving_the_page_asks_no_device_anything(self, _):
        with mock.patch("bells.views.urlopen") as urlopen:
            self.assertEqual(self.client.get(reverse("events:strokes")).status_code, 200)
        urlopen.assert_not_called()

    @skipUnless(NODE, "node not installed")
    def test_running_page_makes_no_device_status_requests(self, _):
        out = run_page(self.client.get(reverse("events:strokes")).content.decode())
        self.assertEqual(out["errors"], [])
        self.assertEqual(out["sockets"], [])
        self.assertEqual(out["srcs"], [])
        paths = [urlparse(u).path for u in out["fetches"]]
        self.assertEqual(set(paths) - ALLOWED, set(), out["fetches"])
        for want in ALLOWED:                       # both feeds really are polled
            self.assertIn(want, paths)
        self.assertGreater(paths.count("/events/api/since/"), 30)    # ~1 s poll for 2 min
        self.assertGreater(out["rows"], 0)                            # strokes were drawn

    @skipUnless(NODE, "node not installed")
    def test_harness_does_see_the_farm_pages_status_poll(self, _):
        """The same harness on the sandswing farm page does find its /status poll and its
        socket to the Pico, so the test above would catch one on the Strokes page."""
        out = run_page(self.client.get(reverse("farm_status_index", args=[1])).content.decode())
        self.assertTrue(any(urlparse(u).path == reverse("farm_device_status")
                            for u in out["fetches"]), out["fetches"])
        self.assertIn({"kind": "WebSocket", "url": PICO_WS}, out["sockets"])
