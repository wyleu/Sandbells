"""Live list on the sandswing farm page: /events/api/since contract, panel."""

import json
from datetime import datetime, timezone
from unittest import mock

from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from . import constants as C
from .api import time_ok
from .models import ChannelMap, Event
from .queries import current_ring, events_after, reset_ring_cache
from .tests_pages import BOOT, SRC, TENOR, add_strokes, utc_ms

T0 = utc_ms(2026, 10, 22, 10)                 # 11:00 BST Thu 22 Oct
TOLL_MS = 12400                               # one tenor stroke every 12.4 s
HEAD_LAG_MS = 40                              # ch2 sees it 40 ms after ch1


def tolling(n, first_seq=1, t0=T0):
    """n strokes on bell 8, each seen by both heads -> 2n events."""
    specs, seq = [], first_seq
    for i in range(n):
        t = t0 + i * TOLL_MS
        specs += [(seq, t, 1), (seq + 1, t + HEAD_LAG_MS, 2)]
        seq += 2
    return specs


class TimeOkTests(SimpleTestCase):
    def test_marker_rule(self):
        self.assertTrue(time_ok(C.ACC_MS, C.SYNC_SYNCED))
        self.assertTrue(time_ok(C.ACC_MS, C.SYNC_HELD))
        self.assertFalse(time_ok(C.ACC_MS, C.SYNC_STALE))
        self.assertFalse(time_ok(C.ACC_S, C.SYNC_SYNCED))
        self.assertFalse(time_ok(None, C.SYNC_UNSYNCED))


class SinceLiveTests(TestCase):
    def setUp(self):
        reset_ring_cache()
        for ch in (1, 2):
            ChannelMap.objects.create(src=SRC, ch=ch, bell=TENOR,
                                      valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc))

    def get(self, **params):
        r = self.client.get(reverse("events:api_since"), dict(type=C.TYPE_STROKE, **params))
        self.assertEqual(r.status_code, 200, r.content)
        return json.loads(r.content)

    def test_first_load_rows_intervals_and_ring(self):
        add_strokes(tolling(15), other_types=[(100, T0 + 1)])
        d = self.get(limit=C.LIVE_FIRST_LOAD)
        evs = d["events"]
        self.assertEqual(len(evs), C.LIVE_FIRST_LOAD)
        self.assertTrue(all(e["type"] == C.TYPE_STROKE for e in evs))
        last = evs[-1]                                    # newest: seq 30, ch2
        self.assertEqual((last["seq"], last["ch"], last["bell_label"]), (30, 2, "Bell 8"))
        self.assertEqual(last["at_hms_ms"], "11:02:53.640")
        self.assertEqual(last["interval_ms"], TOLL_MS)    # same ch, from the DB
        self.assertTrue(last["time_ok"])
        self.assertIsInstance(d["server_ms"], int)
        ring = d["ring"]
        self.assertEqual((ring["strokes"], ring["events"]), (15, 30))
        self.assertEqual(ring["bells"][0]["per_ch"], {"1": 15, "2": 15})
        self.assertEqual(ring["start_hms"], "11:00:00")

    def test_poll_with_nothing_new_is_cheap_and_has_no_ring(self):
        add_strokes(tolling(3))
        latest = Event.objects.order_by("-id").first().id
        with CaptureQueriesContext(connection) as q:
            d = self.get(after=latest)
        self.assertEqual((d["events"], d["latest_id"]), ([], latest))
        self.assertNotIn("ring", d)
        self.assertLessEqual(len(q), 2)                  # events + channel map
        self.assertIn('"id" >', q[0]["sql"])

    def test_new_stroke_extends_cached_ring(self):
        add_strokes(tolling(3))
        latest = self.get(limit=C.LIVE_FIRST_LOAD)["latest_id"]
        add_strokes(tolling(1, first_seq=7, t0=T0 + 3 * TOLL_MS))
        d = self.get(after=latest)
        self.assertEqual([e["seq"] for e in d["events"]], [7, 8])
        self.assertEqual([e["interval_ms"] for e in d["events"]], [TOLL_MS, TOLL_MS])
        self.assertEqual(d["ring"]["strokes"], 4)

    def test_pause_longer_than_ring_gap_starts_new_ring(self):
        add_strokes(tolling(3))
        latest = self.get(limit=C.LIVE_FIRST_LOAD)["latest_id"]
        later = T0 + 2 * TOLL_MS + HEAD_LAG_MS + C.RING_GAP_MS + 1
        add_strokes(tolling(1, first_seq=7, t0=later))
        d = self.get(after=latest)
        self.assertEqual(d["events"][0]["interval_ms"], None)   # new ring: no interval
        self.assertEqual((d["ring"]["strokes"], d["ring"]["seq_first"]), (1, 7))

    def test_unsynced_stroke_is_dimmed(self):
        Event.objects.bulk_create([Event(src=SRC, device_id="p", boot_id=BOOT, seq=1,
                                         type=C.TYPE_STROKE, ch=1, tick_ms=5,
                                         acc=None, sync=C.SYNC_UNSYNCED, host="x")])
        e = self.get()["events"][0]
        self.assertFalse(e["time_ok"])
        self.assertIsNotNone(e["at_hms_ms"])                     # by received time


class CurrentRingTests(TestCase):
    def setUp(self):
        reset_ring_cache()

    def test_walk_back_stops_at_gap(self):
        add_strokes([(1, T0, 1), (2, T0 + C.RING_GAP_MS + 1, 1), (3, T0 + C.RING_GAP_MS + 2, 1)])
        ring = current_ring(SRC, BOOT, 3)
        self.assertEqual([s.seq for s in ring.strokes], [2, 3])

    def test_snapshot_not_shared(self):
        add_strokes([(1, T0, 1)])
        a = current_ring(SRC, BOOT, 1)
        add_strokes([(2, T0 + 1, 1)])
        current_ring(SRC, BOOT, 2)
        self.assertEqual(len(a.strokes), 1)

    def test_events_after_uses_id_order(self):
        add_strokes([(1, T0, 1), (2, T0 + 1, 1)], other_types=[(3, T0 + 2)])
        rows = events_after(None, None, 5, C.TYPE_STROKE)
        self.assertEqual([r.seq for r in rows], [1, 2])


FARM = [{"id": "sandswing", "name": "sandswing", "family": "sandswing",
         "kind": "pico", "status_url": "http://192.168.0.81/status", "ws_url": "",
         "poll_hint_sec": 5},
        {"id": "sandbells", "name": "sandbells", "family": "sandbells", "kind": "host",
         "status_url": "", "ws_url": "", "poll_hint_sec": 5}]


@mock.patch("bells.views.load_farm_instances", return_value=FARM)
class FarmPagePanelTests(TestCase):
    def test_panel_only_on_sandswing_page(self, _):
        r = self.client.get(reverse("farm_status_index", args=[0]))
        self.assertContains(r, 'id="live-events"')
        self.assertContains(r, 'class="with-live"')
        self.assertContains(r, 'data-url="%s"' % reverse("events:api_since"))
        self.assertContains(r, 'data-first="%d"' % C.LIVE_FIRST_LOAD)
        self.assertContains(r, "FarmStatus.start(")              # existing page intact
        r = self.client.get(reverse("farm_status_index", args=[1]))
        self.assertNotContains(r, "live-events")
        self.assertNotContains(r, "with-live")
        self.assertContains(r, "FarmStatus.start(")
