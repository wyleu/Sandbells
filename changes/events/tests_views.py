"""Pages patch 2: /events/days/ and /events/ring/... HTML pages."""

from datetime import date
from unittest import mock, skipUnless

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from . import constants as C
from . import localtime as LT
from .models import ChannelMap
from .tests_pages import BOOT, MIN, SRC, TENOR, add_strokes, utc_ms
from .tests_strokes_page import NODE, run_page

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
    """The ring page is the Strokes page's panel and list (strokes.html,
    live_panel.html, live_list.js) given one stored ring, drawn once."""

    def get(self, src=SRC, boot=BOOT, seq=1):
        return self.client.get(reverse("events:ring", args=[src, boot, seq]))

    def events(self, r):
        return [(e["at_hms_ms"], e["bell"], e["ch"], e["interval_ms"])
                for e in r.context["ring"]["data"]["events"]]

    def test_strokes_as_the_live_feed_gives_them_with_per_ch_intervals(self):
        two_heads()
        add_strokes([(1, THU, 1), (2, THU + 40, 2), (3, THU + 2100, 1),
                     (4, THU + 2125, 2), (5, THU + 4000, 1),
                     (6, THU + C.RING_GAP_MS + 4001, 1)])     # next ring
        r = self.get()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.events(r),
                         [("16:30:00.000", TENOR, 1, None),
                          ("16:30:00.040", TENOR, 2, None),
                          ("16:30:02.100", TENOR, 1, 2100),
                          ("16:30:02.125", TENOR, 2, 2085),
                          ("16:30:04.000", TENOR, 1, 1900)])
        e = r.context["ring"]["data"]["events"][0]
        self.assertEqual((e["bell_label"], e["src"], e["boot_id"], e["time_ok"]),
                         ("Bell 8", SRC, BOOT, True))
        self.assertEqual(r.context["ring"]["data"]["ring"]["strokes"], 3)
        self.assertContains(r, "?date=2026-10-22")
        self.assertContains(r, "Thu 22 Oct 2026")

    def test_same_panel_as_the_strokes_page_without_clock_link_or_polling(self):
        add_strokes([(1, THU, 1), (2, THU + 2000, 1), (3, THU + 4000, 1)])
        r = self.get()
        for same in ('id="live-events"', 'id="live-table"', 'id="live-rows"', "beat-scale",
                     "early · lead", "late · lag", "createBeat", 'id="ring-data"',
                     'data-static="ring-data"', 'class="navbtn days on"'):
            self.assertContains(r, same)
        for live_only in ('id="live-clock"', 'id="link-widget"', "link_widget.js",
                          'id="live-since"', 'class="navbtn strokes on"'):
            self.assertNotContains(r, live_only)
        self.assertContains(r, "16:30:00<small>to 16:30:04")       # the ring's span, top left

    @skipUnless(NODE, "node not installed")
    def test_page_draws_every_stroke_and_the_bell_line_and_fetches_nothing(self):
        add_strokes([(i, THU + (i - 1) * 3200, 4) for i in range(1, 154)])
        ChannelMap.objects.create(src=SRC, ch=4, bell=TENOR,
                                  valid_from=LT.ms_to_local(THU + 46 * 3200 - 1600))
        out = run_page(self.get().content.decode())
        self.assertEqual((out["errors"], out["fetches"], out["sockets"]), ([], [], []))
        self.assertEqual(out["rows"], 153)                          # not cut to the live 50
        self.assertEqual(str(out["count"]), "153")
        self.assertEqual(out["heads"], "Bell 8: 107 · ch 4: 46 (from 16:30:00)")
        self.assertEqual(out["firstRow"][:2], ["16:38:06.400", "Bell 8"])   # newest on top
        self.assertEqual(out["firstRow"][3], "3200 ms")

    def test_channel_bound_mid_ring_days_page_counts_once(self):
        add_strokes([(i, THU + (i - 1) * 3200, 4) for i in range(1, 154)])
        ChannelMap.objects.create(src=SRC, ch=4, bell=TENOR,
                                  valid_from=LT.ms_to_local(THU + 46 * 3200 - 1600))
        with at_now():
            days = self.client.get(reverse("events:days"), {"date": "2026-10-22"})
        self.assertEqual([r["strokes"] for r in days.context["rings"]], [153])
        self.assertEqual([(b["name"], b["strokes"]) for b in days.context["rings"][0]["bell_rows"]],
                         [("Bell 8", 107), ("ch 4", 46)])
        self.assertEqual(self.get().context["ring"]["summary"]["strokes"], 153)

    def test_unmapped_bell_is_none(self):
        add_strokes([(7, THU, 4)])
        r = self.get(seq=7)
        self.assertEqual(self.events(r), [("16:30:00.000", None, 4, None)])

    def test_not_a_ring_start_or_unknown(self):
        add_strokes([(1, THU, 1), (2, THU + S, 1)])
        with self.assertLogs("django.request", "WARNING"):
            self.assertEqual(self.get(seq=5).status_code, 404)
        with self.assertLogs("django.request", "WARNING"):
            self.assertEqual(self.get(boot="nope").status_code, 404)

    @mock.patch.object(C, "RING_TABLE_MAX_ROWS", 2)
    def test_long_ring_shows_its_last_strokes(self):
        add_strokes([(i, THU + i * S, 1) for i in range(1, 5)])
        r = self.get()
        self.assertEqual([e["seq"] for e in r.context["ring"]["data"]["events"]], [3, 4])
        self.assertEqual(self.events(r)[0][3], 1000)       # its gap from seq 2, outside the list
        self.assertEqual(r.context["ring"]["summary"]["strokes"], 4)
        self.assertContains(r, "Last 2 strokes shown.")
        self.assertContains(r, 'data-rows="2"')
