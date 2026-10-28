"""The home page's bell movement is driven by Sandbells' own event feed (static/js/bell_feed.js
polling /events/api/since/, the farm page's live-list endpoint), not by a WebSocket to a Pico.
The poll logic is tested in js_tests/bell_feed.test.js (run by AlignJsTests / PowerJsTests with
the rest of js_tests); here: the page hands the script the farm page's endpoint and poll
period, loads it in order, and the endpoint's answer is what the script expects."""
import json
import re
import shutil
import subprocess
from pathlib import Path
from unittest import skipUnless

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from events import constants as C
from events.models import Event
from events.parse import parse
from events.tests import raw
from events.templatetags.events_live import live_panel

from bells.tests_bell_motion import positions

HERE = Path(__file__).resolve().parent
JS = HERE / "static" / "js"
NODE = shutil.which("node")
BOOT = "feedboot"


def add(seq, **changes):
    changes.setdefault("boot_id", BOOT)
    changes.setdefault("utc_ms", 1792578276496 + seq)
    changes.setdefault("tick_ms", 11594059 + seq)
    Event.objects.bulk_create([Event.from_parsed(parse(raw(seq=seq, **changes)), host="sandbells")])


class BellFeedPageTests(TestCase):
    def page(self):
        return self.client.get(reverse("home")).content.decode()

    def test_script_loaded_once_cache_busted_between_its_helpers_and_kiosk_bells(self):
        body = self.page()
        feed = positions(body, "js/bell_feed.js")
        self.assertEqual(len(feed), 1)
        for before in ("js/reconnect_delay.js", "js/bell_motion.js"):
            self.assertLess(positions(body, before)[0], feed[0], before)
        self.assertLess(feed[0], positions(body, "js/kiosk_bells.js")[0])

    def test_bell_circle_carries_the_farm_pages_endpoint_and_poll_period(self):
        body = self.page()
        tag = re.search(r'<div id="bell-circle"[^>]*>', body).group(0)
        attrs = dict(re.findall(r'data-([a-z-]+)="([^"]*)"', tag))
        self.assertEqual(attrs, {
            "feed-url": reverse("events:api_since"),
            "feed-poll-ms": str(C.LIVE_POLL_MS),
            "feed-limit": str(C.LIVE_LIMIT_DEFAULT),
            "feed-timeout-ms": str(C.LIVE_FETCH_TIMEOUT_MS),
        })
        # and that is exactly what the farm page's live list is given
        panel = live_panel()
        self.assertEqual((panel["since_url"], panel["poll_ms"], panel["batch"], panel["timeout_ms"]),
                         (attrs["feed-url"], int(attrs["feed-poll-ms"]), int(attrs["feed-limit"]),
                          int(attrs["feed-timeout-ms"])))
        self.assertEqual(C.LIVE_POLL_MS, 1000)


class BellFeedSourceTests(SimpleTestCase):
    def test_kiosk_script_starts_the_feed_and_the_motion_no_longer_comes_from_the_websocket(self):
        src = (JS / "kiosk_bells.js").read_text()
        self.assertIn("BellFeed.create(", src)
        self.assertIn("BellMotion.isStrokeOrTrigger", src)
        self.assertEqual(src.count("BellMotion.create(el)"), 1)
        self.assertNotIn("moveHost", src)
        handle = src.split("function handleMsg", 1)[1].split("function connectFarmWs", 1)[0]
        self.assertNotIn("BellMotion", handle)
        self.assertNotIn("move", handle.lower())

    def test_websocket_is_left_only_for_the_tape_messages(self):
        src = (JS / "kiosk_bells.js").read_text()
        self.assertEqual(src.count("new WebSocket("), 1)
        self.assertEqual(src.count("BellBand.setTape("), 1)
        self.assertIn("ReconnectDelay.create()", src)

    def test_feed_script_keeps_to_the_farm_pages_mechanism(self):
        src = (JS / "bell_feed.js").read_text()
        code = src.split("*/", 1)[1]
        self.assertNotIn("WebSocket", code)
        self.assertNotIn("setInterval", code)          # a chain of timeouts: never two polls at once
        self.assertIn('"?type="', code)
        self.assertIn('"&after="', code)
        self.assertIn("visibilityState", code)

    def test_one_movement_per_event_is_the_css_length(self):
        js = (JS / "bell_feed.js").read_text()
        css = (HERE / "static" / "css" / "bell_motion.css").read_text()
        move_ms = int(re.search(r"var MOVE_MS = (\d+);", js).group(1))
        self.assertEqual(re.findall(r"(\d+)ms ease-out", css), [str(move_ms)] * 2)


@skipUnless(NODE, "node is not installed")
class BellFeedEndpointTests(TestCase):
    """The endpoint's real answers, handed to bell_motion.js's rule exactly as bell_feed.js does."""

    def get(self, query):
        r = self.client.get(reverse("events:api_since") + query)
        self.assertEqual(r.status_code, 200, r.content)
        return json.loads(r.content)

    def accepted(self, events):
        code = ("const BM=require(%r);const ev=JSON.parse(process.argv[1]);"
                "console.log(JSON.stringify(ev.map(BM.isStrokeOrTrigger)))"
                % str(JS / "bell_motion.js"))
        out = subprocess.run([NODE, "-e", code, json.dumps(events)], capture_output=True,
                             text=True, timeout=30, check=True).stdout
        return json.loads(out)

    def test_first_query_gives_the_newest_id_then_only_newer_events_and_only_strokes_move(self):
        add(1)
        add(2, body={"ch": 3})
        first = self.get("?type=&limit=1")
        newest = first["latest_id"]
        self.assertEqual(len(first["events"]), 1)
        self.assertEqual(self.get("?type=&limit=50&after=%d" % newest)["events"], [])
        add(3, body={"ch": 1, "test": True, "src": "trigger"})           # a trigger plug test stroke
        add(4, type="link", body={"what": "client", "reason": "connected"})
        add(5, type="channel", body={"ch": 1, "kind": "trigger", "why": []})
        add(6)
        d = self.get("?type=&limit=50&after=%d" % newest)
        self.assertEqual([e["seq"] for e in d["events"]], [3, 4, 5, 6])
        self.assertEqual(d["latest_id"], max(e["id"] for e in d["events"]))
        self.assertEqual(self.accepted(d["events"]), [True, False, False, True])

    def test_empty_table_has_no_id_so_the_script_starts_from_zero(self):
        d = self.get("?type=&limit=1")
        self.assertEqual((d["events"], d["latest_id"]), ([], None))
