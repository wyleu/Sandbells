"""Pages patch 2: /events/days/ and /events/ring/... HTML pages."""

from datetime import date
from unittest import mock

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from . import constants as C
from . import localtime as LT
from .models import ChannelMap
from .tests_pages import BOOT, MIN, SRC, TENOR, add_strokes, utc_ms

THU = utc_ms(2026, 10, 22, 15, 30)                       # 16:30 BST Thu 22 Oct
NOW = utc_ms(2026, 10, 23, 12, 0)                        # Fri 23 Oct
S = C.MS_PER_S


def at_now(ms=NOW):
    return mock.patch("events.views._now_ms", return_value=ms)


class FormatTests(SimpleTestCase):
    def test_duration(self):
        self.assertEqual(LT.format_duration(2069), "34:29")
        self.assertEqual(LT.format_duration(3725), "1:02:05")
        self.assertEqual(LT.format_duration(0.4), "0:00")

    def test_hms_ms_and_day_label(self):
        self.assertEqual(LT.local_hms_ms(THU + 250), "16:30:00.250")
        self.assertIsNone(LT.local_hms_ms(None))
        self.assertEqual(LT.day_label(date(2026, 10, 22)), "Thu 22 Oct 2026")


def two_heads():
    for ch in (1, 2):
        ChannelMap.objects.create(src=SRC, ch=ch, bell=TENOR,
                                  valid_from=LT.ms_to_local(THU - MIN))


class DaysPageTests(TestCase):
    def get(self, **params):
        with at_now():
            return self.client.get(reverse("events:days"), params)

    def test_empty(self):
        r = self.get()
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "No strokes in the last 31 days.")
        self.assertContains(r, "No rings on this day.")

    def test_default_is_latest_day_with_two_heads_note(self):
        two_heads()
        add_strokes([(1, THU, 1), (2, THU + 40, 2), (3, THU + 2 * S, 1),
                     (4, THU + 2 * S + 30, 2), (5, THU + 4 * S, 1)])
        add_strokes([(1, utc_ms(2026, 10, 20, 9), 1)], boot="b0")
        r = self.get()
        self.assertEqual(r.context["chosen_iso"], "2026-10-22")
        self.assertEqual([d["iso"] for d in r.context["days"]],
                         ["2026-10-22", "2026-10-20"])
        ring = r.context["rings"][0]
        self.assertEqual((ring["start_hms"], ring["strokes"], ring["seq_missing"]),
                         ("16:30:00", 3, 0))
        self.assertContains(r, "Thu 22 Oct 2026")
        self.assertContains(r, "Bell 8")
        self.assertContains(r, "two heads: ch 1: 3, ch 2: 2")
        self.assertContains(r, reverse("events:ring", args=[SRC, BOOT, 1]))

    def test_chosen_date_missing_seq_and_unmapped(self):
        add_strokes([(1, THU, 3), (4, THU + S, 3)])
        add_strokes([(1, utc_ms(2026, 10, 22, 23, 30), 1)], boot="late")  # Fri BST
        r = self.get(date="2026-10-22")
        self.assertEqual(len(r.context["rings"]), 1)
        ring = r.context["rings"][0]
        self.assertEqual(ring["seq_missing"], 2)
        self.assertEqual(ring["bell_rows"], [{"name": "ch 3", "strokes": 2, "heads": []}])
        self.assertNotContains(r, "two heads:")

    def test_older_than_31_days_not_listed(self):
        add_strokes([(1, NOW - 40 * 24 * 60 * MIN, 1)])
        self.assertEqual(self.get().context["days"], [])

    def test_bad_date(self):
        with self.assertLogs("django.request", "WARNING"):
            self.assertEqual(self.get(date="22/10/2026").status_code, 400)


class RingPageTests(TestCase):
    def get(self, src=SRC, boot=BOOT, seq=1):
        return self.client.get(reverse("events:ring", args=[src, boot, seq]))

    def test_strokes_table_with_per_ch_intervals(self):
        two_heads()
        add_strokes([(1, THU, 1), (2, THU + 40, 2), (3, THU + 2100, 1),
                     (4, THU + 2125, 2), (5, THU + 4000, 1),
                     (6, THU + C.RING_GAP_MS + 4001, 1)])     # next ring
        r = self.get()
        self.assertEqual(r.status_code, 200)
        rows = r.context["rows"]
        self.assertEqual([(x["time"], x["bell"], x["ch"], x["interval_ms"]) for x in rows],
                         [("16:30:00.000", TENOR, 1, None),
                          ("16:30:00.040", TENOR, 2, None),
                          ("16:30:02.100", TENOR, 1, 2100),
                          ("16:30:02.125", TENOR, 2, 2085),
                          ("16:30:04.000", TENOR, 1, 1900)])
        self.assertContains(r, "16:30:02.125")
        self.assertContains(r, "two heads: ch 1: 3, ch 2: 2")
        self.assertContains(r, "?date=2026-10-22")

    def test_rows_carry_gaps_for_the_gold_beat_mark(self):
        add_strokes([(1, THU, 1), (2, THU + 2000, 1), (3, THU + 4000, 1)])
        r = self.get()
        self.assertContains(r, 'class="beat"', count=3)
        self.assertContains(r, 'data-ch="1" data-gap=""')
        self.assertContains(r, 'data-ch="1" data-gap="2000"')
        self.assertContains(r, "createBeat")              # beat.js inlined
        self.assertContains(r, 'class="navbtn on"')

    def test_unmapped_bell_shown_as_dash(self):
        add_strokes([(7, THU, 4)])
        r = self.get(seq=7)
        self.assertEqual(r.context["rows"][0]["bell"], None)
        self.assertContains(r, "—")

    def test_not_a_ring_start_or_unknown(self):
        add_strokes([(1, THU, 1), (2, THU + S, 1)])
        with self.assertLogs("django.request", "WARNING"):
            self.assertEqual(self.get(seq=5).status_code, 404)
        with self.assertLogs("django.request", "WARNING"):
            self.assertEqual(self.get(boot="nope").status_code, 404)

    @mock.patch.object(C, "RING_TABLE_MAX_ROWS", 2)
    def test_long_ring_truncated(self):
        add_strokes([(i, THU + i * S, 1) for i in range(1, 5)])
        r = self.get()
        self.assertEqual(len(r.context["rows"]), 2)
        self.assertContains(r, "First 2 strokes shown.")
