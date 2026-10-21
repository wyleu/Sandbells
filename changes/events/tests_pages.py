"""Pages patch 1: local time, ring grouping, channel map, JSON endpoints."""

import json
from datetime import date, datetime, timedelta, timezone

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from . import constants as C
from . import localtime as LT
from .ingest import Ingest
from .mapping import ChannelMapper, ch_label
from .models import ChannelMap, Event
from .parse import parse
from .rings import Stroke, group_rings, summarise
from .store import EventStore
from .tests import FakeClock, raw

UTC = timezone.utc
MIN = C.MS_PER_MINUTE
SRC, BOOT = "sandswing", "216a0e79"
TENOR = 8


def utc_ms(*args):
    return LT.dt_to_ms(datetime(*args, tzinfo=UTC))


class LocalTimeTests(SimpleTestCase):
    def test_bst_end_day_is_25_hours(self):
        a, b = LT.day_bounds_ms(date(2026, 10, 25))
        self.assertEqual(a, utc_ms(2026, 10, 24, 23))       # 00:00 BST
        self.assertEqual(b, utc_ms(2026, 10, 26, 0))        # 00:00 GMT
        self.assertEqual(b - a, 25 * 60 * MIN)

    def test_bst_start_day_is_23_hours(self):
        a, b = LT.day_bounds_ms(date(2026, 3, 29))
        self.assertEqual(b - a, 23 * 60 * MIN)

    def test_local_date_and_labels(self):
        ms = utc_ms(2026, 10, 21, 23, 30)                    # 00:30 BST next day
        self.assertEqual(LT.local_date(ms), date(2026, 10, 22))
        self.assertEqual(LT.local_hms(ms), "00:30:00")
        self.assertEqual(LT.local_iso(ms), "2026-10-22T00:30:00.000+01:00")
        self.assertEqual(LT.local_hms(utc_ms(2026, 10, 26, 9)), "09:00:00")  # GMT

    def test_repeated_hour_on_bst_end(self):
        first, second = utc_ms(2026, 10, 25, 0, 30), utc_ms(2026, 10, 25, 1, 30)
        self.assertEqual(LT.local_hms(first), LT.local_hms(second))  # 01:30 twice
        self.assertTrue(LT.local_iso(first).endswith("+01:00"))
        self.assertTrue(LT.local_iso(second).endswith("+00:00"))


def st(seq, tick_ms, ch=1, src=SRC, boot=BOOT, at_ms=None):
    return Stroke(src, boot, seq, ch, tick_ms, tick_ms if at_ms is None else at_ms)


class RingTests(SimpleTestCase):
    def test_wait_of_15_min_stays_one_ring(self):
        rings = group_rings([st(1, 0), st(2, 2000), st(3, 2000 + 15 * MIN)])
        self.assertEqual(len(rings), 1)

    def test_gap_longer_than_constant_splits(self):
        g = C.RING_GAP_MS
        rings = group_rings([st(1, 0), st(2, g), st(3, 2 * g + 1)])
        self.assertEqual([len(r.strokes) for r in rings], [2, 1])

    def test_boot_and_src_split_and_order(self):
        rings = group_rings([st(2, 10, boot="b2"), st(1, 5, boot="b2"),
                             st(1, 0), st(1, 0, src="other")])
        self.assertEqual([(r.src, r.boot_id, len(r.strokes)) for r in rings],
                         [("other", BOOT, 1), (SRC, BOOT, 1), (SRC, "b2", 2)])

    def test_summary_two_heads_on_one_bell(self):
        mapper = ChannelMapper([(SRC, 1, TENOR, 0), (SRC, 2, TENOR, 0)])
        ring = group_rings([st(1, 0, ch=1), st(2, 40, ch=2), st(3, 4000, ch=1),
                            st(4, 4030, ch=2), st(5, 8000, ch=3)])[0]
        d = summarise(ring, mapper, ch_label, events_in_span=5)
        # both heads see every stroke: the bell count is the max, not the sum
        self.assertEqual(d["bells"], [{"bell": TENOR, "chs": [1, 2],
                                       "per_ch": {1: 2, 2: 2}, "strokes": 2}])
        self.assertEqual([(c["ch"], c["bell"], c["strokes"]) for c in d["channels"]],
                         [(1, TENOR, 2), (2, TENOR, 2), (3, None, 1)])
        self.assertEqual(d["unmapped_chs"], [3])
        self.assertEqual(d["channels"][2]["label"], "ch 3")
        self.assertEqual((d["seq_missing"], d["strokes"], d["events"]), (0, 3, 5))

    def test_bell_count_is_max_of_heads(self):
        mapper = ChannelMapper([(SRC, 1, TENOR, 0), (SRC, 2, TENOR, 0)])
        ring = group_rings([st(i, i * 1000, ch=1 if i <= 41 else 2)
                            for i in range(1, 69)])[0]            # 41 + 27
        d = summarise(ring, mapper, ch_label, events_in_span=68)
        self.assertEqual(d["bells"][0]["per_ch"], {1: 41, 2: 27})
        self.assertEqual((d["bells"][0]["strokes"], d["strokes"], d["events"]),
                         (41, 41, 68))

    def test_summary_missing(self):
        ring = group_rings([st(1, 0), st(10, 100)])[0]
        self.assertEqual(summarise(ring, ChannelMapper(), ch_label, 3)["seq_missing"], 7)


class MapperTests(SimpleTestCase):
    def test_history_and_unmap(self):
        m = ChannelMapper([(SRC, 1, 3, 1000), (SRC, 1, TENOR, 5000),
                           (SRC, 1, None, 9000)])
        self.assertIsNone(m.bell_for(SRC, 1, 999))
        self.assertEqual(m.bell_for(SRC, 1, 1000), 3)
        self.assertEqual(m.bell_for(SRC, 1, 8999), TENOR)
        self.assertIsNone(m.bell_for(SRC, 1, 9000))
        self.assertIsNone(m.bell_for(SRC, 2, 5000))
        self.assertIsNone(m.bell_for("other", 1, 5000))


def add_strokes(specs, boot=BOOT, src=SRC, other_types=()):
    """specs: [(seq, utc_ms, ch)].  tick_ms = utc_ms (one clean boot)."""
    rows = [Event.from_parsed(parse(raw(seq=seq, utc_ms=ms, tick_ms=ms,
                                        boot_id=boot, src=src, body={"ch": ch})),
                              host="sandbells")
            for seq, ms, ch in specs]
    rows += [Event.from_parsed(parse(raw(seq=seq, utc_ms=ms, tick_ms=ms, boot_id=boot,
                                         type="tower", body={"state": "active"})),
                               host="sandbells")
             for seq, ms in other_types]
    Event.objects.bulk_create(rows)


class DaysApiTests(TestCase):
    def get_days(self, **params):
        r = self.client.get(reverse("events:api_days"), params)
        self.assertEqual(r.status_code, 200, r.content)
        return json.loads(r.content)

    def test_midnight_ring_listed_once_under_start_day(self):
        t = utc_ms(2026, 10, 22, 22, 50)                 # 23:50 BST Thu 22
        add_strokes([(1, t, 1), (2, t + 5 * MIN, 1), (3, t + 20 * MIN, 1),
                     (4, t + 45 * MIN, 1)])              # 00:35 BST Fri 23
        d = self.get_days(**{"from": "2026-10-22", "to": "2026-10-23"})
        self.assertEqual([x["date"] for x in d["days"]], ["2026-10-22"])
        ring = d["days"][0]["rings"][0]
        self.assertEqual((ring["start_hms"], ring["end_hms"]), ("23:50:00", "00:35:00"))
        self.assertEqual(ring["strokes"], 4)

    def test_next_day_alone_completes_and_skips_earlier_ring(self):
        t = utc_ms(2026, 10, 22, 22, 50)
        add_strokes([(1, t, 1), (2, t + 20 * MIN, 1), (3, t + 45 * MIN, 1)])
        d = self.get_days(**{"from": "2026-10-23", "to": "2026-10-23"})
        self.assertEqual(d["days"], [])                  # belongs to Thu 22
        d = self.get_days(**{"from": "2026-10-22", "to": "2026-10-22"})
        self.assertEqual(d["days"][0]["rings"][0]["strokes"], 3)   # tail followed

    def test_bst_end_day_rings(self):
        a = utc_ms(2026, 10, 25, 0, 30)                  # 01:30 BST
        b = utc_ms(2026, 10, 25, 23, 30)                 # 23:30 GMT, same local day
        add_strokes([(1, a, 1), (2, a + MIN, 1), (3, b, 2)])
        d = self.get_days(**{"from": "2026-10-25", "to": "2026-10-25"})
        rings = d["days"][0]["rings"]
        self.assertEqual([r["start_local"][11:] for r in rings],
                         ["01:30:00.000+01:00", "23:30:00.000+00:00"])

    def test_mapping_coverage_and_two_heads(self):
        t = utc_ms(2026, 10, 22, 10, 0)
        ChannelMap.objects.create(src=SRC, ch=1, bell=TENOR,
                                  valid_from=datetime(2026, 10, 21, tzinfo=UTC))
        ChannelMap.objects.create(src=SRC, ch=2, bell=TENOR,
                                  valid_from=datetime(2026, 10, 21, tzinfo=UTC))
        add_strokes([(1, t, 1), (2, t + 30, 2), (5, t + 6000, 1), (6, t + 6040, 2)],
                    other_types=[(3, t + 3000)])          # seq 4 lost
        ring = self.get_days(**{"from": "2026-10-22", "to": "2026-10-22"})["days"][0]["rings"][0]
        self.assertEqual(ring["bells"], [{"bell": TENOR, "chs": [1, 2],
                                          "per_ch": {"1": 2, "2": 2}, "strokes": 2}])
        self.assertEqual((ring["strokes"], ring["events"]), (2, 4))
        self.assertEqual(ring["seq_missing"], 1)
        self.assertEqual(ring["key"], "%s/%s/1" % (SRC, BOOT))

    def test_bad_args(self):
        url = reverse("events:api_days")
        with self.assertLogs("django.request", "WARNING"):
            self.assertEqual(self.client.get(url, {"from": "22/10/2026"}).status_code, 400)
            self.assertEqual(self.client.get(url, {"from": "2026-01-01",
                                                   "to": "2026-10-22"}).status_code, 400)

    def test_default_window_ok_when_empty(self):
        self.assertEqual(self.get_days()["days"], [])


class SinceApiTests(TestCase):
    def test_after_id_limit_and_mapping(self):
        ChannelMap.objects.create(src=SRC, ch=1, bell=TENOR,
                                  valid_from=datetime(2026, 1, 1, tzinfo=UTC))
        t = utc_ms(2026, 10, 22, 10)
        add_strokes([(s, t + s * 1000, 1 + s % 2) for s in range(1, 6)])
        url = reverse("events:api_since")
        d = json.loads(self.client.get(url, {"limit": 2}).content)
        self.assertEqual([e["seq"] for e in d["events"]], [4, 5])
        first_id = Event.objects.order_by("id").first().id
        d = json.loads(self.client.get(url, {"after": first_id, "limit": 2}).content)
        self.assertEqual([e["seq"] for e in d["events"]], [2, 3])
        self.assertEqual(d["latest_id"], d["events"][-1]["id"])
        e2, e3 = d["events"]
        self.assertEqual((e2["ch"], e2["bell"], e3["ch"], e3["bell"]), (1, TENOR, 2, None))
        self.assertEqual(e3["label"], "ch 2")
        self.assertEqual(e2["at_local"], "2026-10-22T11:00:02.000+01:00")
        d = json.loads(self.client.get(url, {"after": d["latest_id"] + 100}).content)
        self.assertEqual((d["events"], d["latest_id"]), ([], d["latest_id"]))

    def test_bad_after(self):
        with self.assertLogs("django.request", "WARNING"):
            self.assertEqual(self.client.get(reverse("events:api_since"),
                                             {"after": "x"}).status_code, 400)


class PanelIgnoredTests(TestCase):
    def test_panel_frame_dropped_silently(self):
        clock = FakeClock()
        ing = Ingest(EventStore(clock=clock, host="x"), clock=clock)
        frame = json.dumps({"schema": C.SCHEMA_PANEL_V1, "src": SRC,
                            "rgb": [[0, 0, 32]] * 6})
        with self.assertNoLogs(C.LOGGER_NAME, "WARNING"):
            self.assertIsNone(ing.handle_frame(frame))
        self.assertEqual((ing.ignored, ing.rejects, len(ing.store)), (1, {}, 0))
        self.assertIn("ignored 1", ing.summary())


class ChannelMapModelTests(TestCase):
    def test_str_and_ms(self):
        m = ChannelMap.objects.create(src=SRC, ch=2, bell=TENOR,
                                      valid_from=datetime(1970, 1, 1, 0, 0, 1, tzinfo=UTC))
        self.assertEqual(str(m), "sandswing ch 2 -> bell 8")
        self.assertEqual(m.valid_from_ms, 1000)
        self.assertEqual(ChannelMapper.from_db().bell_for(SRC, 2, None), TENOR)
