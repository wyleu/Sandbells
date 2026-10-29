"""The home page's bell movement is driven by Sandbells' own event feed (static/js/bell_feed.js
polling /events/api/since/, the farm page's live-list endpoint), not by a WebSocket to a Pico.
The poll logic is tested in js_tests/bell_feed.test.js (run by AlignJsTests / PowerJsTests with
the rest of js_tests); here: the page hands the script the farm page's endpoint and poll
period, loads it in order, and the endpoint's answer is what the script expects: each stroke
carries the bell its channel is mapped to, and a stroke on an unmapped channel moves nothing."""
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest import skipUnless

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from events import constants as C
from events.models import ChannelMap, Event
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


def mapped(ch, bell):
    """ch -> bell from well before the test events' times."""
    ChannelMap.objects.create(ch=ch, bell=bell, valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc))


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
            "quiver-ms": str(C.BELL_QUIVER_MS),
            "quiver-px": str(C.BELL_QUIVER_PX),
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
        self.assertIn("BellMotion.isBellStroke", src)
        self.assertEqual(src.count("BellMotion.create(el, look)"), 1)
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
        # one number, data-quiver-ms: the feed's spacing and the movement's length (via --bell-motion-ms)
        kiosk = (JS / "kiosk_bells.js").read_text()
        self.assertIn("var look = { ms: +d.quiverMs, px: +d.quiverPx };", kiosk)
        self.assertIn("moveMs: look.ms,", kiosk)
        feed = (JS / "bell_feed.js").read_text().split("*/", 1)[1]
        self.assertIn("later(playNext, o.moveMs)", feed)
        self.assertNotIn("MOVE_MS", feed)
        motion = (JS / "bell_motion.js").read_text().split("*/", 1)[1]
        self.assertIn('"--bell-motion-ms", look.ms + "ms"', motion)
        self.assertIn('"--bell-motion-px", look.px + "px"', motion)


@skipUnless(NODE, "node is not installed")
class BellFeedEndpointTests(TestCase):
    """The endpoint's real answers, handed to bell_motion.js's rule exactly as bell_feed.js does."""

    def get(self, query):
        r = self.client.get(reverse("events:api_since") + query)
        self.assertEqual(r.status_code, 200, r.content)
        return json.loads(r.content)

    def accepted(self, events):
        code = ("const BM=require(%r);const ev=JSON.parse(process.argv[1]);"
                "console.log(JSON.stringify(ev.map(BM.isBellStroke)))"
                % str(JS / "bell_motion.js"))
        out = subprocess.run([NODE, "-e", code, json.dumps(events)], capture_output=True,
                             text=True, timeout=30, check=True).stdout
        return json.loads(out)

    def test_first_query_gives_the_newest_id_then_only_newer_events_and_only_strokes_move(self):
        mapped(1, 8)
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

    def test_each_stroke_names_its_bell_from_the_channel_map_and_an_unmapped_one_moves_nothing(self):
        mapped(1, 8)                                 # ch 1 -> bell 8 (the brown one)
        mapped(2, 3)
        newest = self.get("?type=&limit=1")["latest_id"] or 0
        add(11, body={"ch": 1})
        add(12, body={"ch": 2, "test": True, "src": "trigger"})
        add(13, body={"ch": 7})                      # no mapping for ch 7
        d = self.get("?type=&limit=50&after=%d" % newest)
        self.assertEqual([(e["ch"], e["bell"]) for e in d["events"]], [(1, 8), (2, 3), (7, None)])
        self.assertEqual(self.accepted(d["events"]), [True, True, False])

    def test_empty_table_has_no_id_so_the_script_starts_from_zero(self):
        d = self.get("?type=&limit=1")
        self.assertEqual((d["events"], d["latest_id"]), ([], None))
