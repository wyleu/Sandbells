import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from unittest import mock

from django.db import connection
from django.test import SimpleTestCase, TestCase

from . import constants as C
from .db import apply_pragmas, on_connection_created
from .gaps import GapTracker
from .models import Event
from .parse import ParseError, parse
from .store import EventStore

# Real event from sandswing (boot 03e1420d), as received.
SAMPLE = {
    "tick_ms": 11594059, "epoch": 5, "seq": 2, "body": {"ch": 1},
    "type": "stroke", "mode": "free", "id": "sandswing-pico",
    "src": "sandswing", "boot_id": "03e1420d", "sync": "synced",
    "session": 1, "utc_ms": 1792578276496, "err_ms": 4.2004, "acc": "ms",
    "schema": "sand.event/v1",
}
SAMPLE_UTC = datetime(2026, 10, 21, 10, 24, 36, 496000, tzinfo=timezone.utc)
SRV = "192.168.0.221"
STRATUM_GPS = 1


def sample(**changes):
    d = json.loads(json.dumps(SAMPLE))
    for k, v in changes.items():
        if v is _DROP:
            d.pop(k, None)
        else:
            d[k] = v
    return d


_DROP = object()


def raw(**changes):
    return json.dumps(sample(**changes))


class ParseGood(SimpleTestCase):
    def test_real_sample(self):
        p = parse(json.dumps(SAMPLE))
        self.assertEqual((p.src, p.device_id, p.boot_id, p.seq),
                         ("sandswing", "sandswing-pico", "03e1420d", 2))
        self.assertEqual(p.type, C.TYPE_STROKE)
        self.assertTrue(p.known_type)
        self.assertEqual(p.tick_ms, 11594059)
        self.assertEqual(p.utc_ms, 1792578276496)
        self.assertIsInstance(p.utc_ms, int)
        self.assertAlmostEqual(p.err_ms, 4.2004)
        self.assertEqual((p.acc, p.sync, p.mode), ("ms", "synced", "free"))
        self.assertEqual((p.epoch, p.session), (5, 1))
        self.assertEqual(p.ch, 1)
        self.assertIsNone(p.srv)
        self.assertIsNone(p.stratum)
        self.assertEqual(p.raw, SAMPLE)

    def test_bytes_accepted(self):
        self.assertEqual(parse(raw().encode("utf-8")).seq, 2)

    def test_with_srv_and_stratum(self):
        p = parse(raw(srv=SRV, stratum=STRATUM_GPS))
        self.assertEqual((p.srv, p.stratum), (SRV, STRATUM_GPS))

    def test_unsynced_nulls(self):
        p = parse(raw(utc_ms=None, err_ms=None, acc=None, sync="unsynced",
                      srv=None, stratum=None))
        self.assertIsNone(p.utc_ms)
        self.assertIsNone(p.err_ms)
        self.assertEqual(p.sync, C.SYNC_UNSYNCED)

    def test_held_ringing(self):
        p = parse(raw(sync="held", mode="ringing"))
        self.assertEqual((p.sync, p.mode), (C.SYNC_HELD, C.MODE_RINGING))

    def test_unknown_type_flagged_not_error(self):
        p = parse(raw(type="clock", body={"note": "x"}))
        self.assertFalse(p.known_type)
        self.assertEqual(p.type, "clock")
        self.assertIsNone(p.ch)

    def test_no_body(self):
        p = parse(raw(body=_DROP))
        self.assertEqual(p.body, {})
        self.assertIsNone(p.ch)

    def test_int_err_ms_becomes_float(self):
        self.assertEqual(parse(raw(err_ms=4)).err_ms, 4.0)


class ParseBad(SimpleTestCase):
    def assertReason(self, text, reason, field=None):
        with self.assertRaises(ParseError) as cm:
            parse(text)
        self.assertEqual(cm.exception.reason, reason)
        if field is not None:
            self.assertEqual(cm.exception.field, field)

    def test_bad_schema(self):
        self.assertReason(raw(schema="sand.status/v1"), C.R_BAD_SCHEMA)
        self.assertReason(raw(schema=_DROP), C.R_BAD_SCHEMA)

    def test_missing_identity(self):
        for f in (C.F_SRC, C.F_ID, C.F_BOOT_ID, C.F_SEQ, C.F_TYPE,
                  C.F_TICK_MS):
            self.assertReason(raw(**{f: _DROP}), C.R_MISSING, f)

    def test_empty_string_identity(self):
        self.assertReason(raw(boot_id=""), C.R_MISSING, C.F_BOOT_ID)

    def test_not_json(self):
        self.assertReason("{not json", C.R_NOT_JSON)
        self.assertReason(b"\xff\xfe", C.R_NOT_UTF8)
        self.assertReason("[1, 2]", C.R_NOT_OBJECT)

    def test_float_ints_rejected(self):
        self.assertReason(raw(seq=2.0), C.R_BAD_TYPE, C.F_SEQ)
        self.assertReason(raw(tick_ms=11594059.0), C.R_BAD_TYPE, C.F_TICK_MS)
        self.assertReason(raw(utc_ms=1792578276496.0), C.R_BAD_TYPE,
                          C.F_UTC_MS)

    def test_bool_is_not_int(self):
        self.assertReason(raw(seq=True), C.R_BAD_TYPE, C.F_SEQ)
        self.assertReason(raw(stratum=True), C.R_BAD_TYPE, C.F_STRATUM)

    def test_bad_choices(self):
        self.assertReason(raw(sync="locked"), C.R_BAD_VALUE, C.F_SYNC)
        self.assertReason(raw(acc="us"), C.R_BAD_VALUE, C.F_ACC)
        self.assertReason(raw(mode="idle"), C.R_BAD_VALUE, C.F_MODE)

    def test_bad_srv_and_stratum(self):
        self.assertReason(raw(srv="sandgps3.local"), C.R_BAD_VALUE, C.F_SRV)
        self.assertReason(raw(stratum=C.STRATUM_MAX + 1), C.R_BAD_VALUE,
                          C.F_STRATUM)

    def test_bad_body(self):
        self.assertReason(raw(body=[1]), C.R_BAD_TYPE, C.F_BODY)
        self.assertReason(raw(body={"ch": "1"}), C.R_BAD_TYPE)

    def test_negative_seq(self):
        self.assertReason(raw(seq=-1), C.R_BAD_VALUE, C.F_SEQ)


class EventModel(TestCase):
    def test_from_parsed_round_trip(self):
        ev = Event.from_parsed(parse(raw(srv=SRV, stratum=STRATUM_GPS)),
                               host="sandbells2")
        self.assertIsNone(ev.pk)                 # not saved by from_parsed
        ev.save()
        got = Event.objects.get(pk=ev.pk)
        self.assertEqual(got.utc_ms, 1792578276496)
        self.assertEqual(got.tick_ms, 11594059)
        self.assertEqual((got.srv, got.stratum, got.ch), (SRV, STRATUM_GPS, 1))
        self.assertEqual(got.host, "sandbells2")
        self.assertEqual(got.raw[C.F_SCHEMA], C.SCHEMA_EVENT_V1)

    def test_utc_property(self):
        ev = Event.from_parsed(parse(raw()))
        self.assertEqual(ev.utc, SAMPLE_UTC)
        self.assertEqual(ev.utc.tzinfo, timezone.utc)
        ev.utc_ms = None
        self.assertIsNone(ev.utc)

    def test_host_defaults_to_this_machine(self):
        self.assertTrue(Event.from_parsed(parse(raw())).host)

    def test_duplicate_ignored(self):
        p = parse(raw())
        Event.objects.bulk_create([Event.from_parsed(p, host="sandbells")])
        Event.objects.bulk_create(
            [Event.from_parsed(p, host="sandbells2"),          # same key
             Event.from_parsed(parse(raw(seq=3)), host="sandbells2")],
            ignore_conflicts=True)
        self.assertEqual(Event.objects.count(), 2)
        self.assertEqual(Event.objects.get(seq=2).host, "sandbells")

    def test_same_seq_new_boot_is_new_row(self):
        Event.objects.bulk_create([Event.from_parsed(parse(raw())),
                                   Event.from_parsed(parse(raw(boot_id="b2")))],
                                  ignore_conflicts=True)
        self.assertEqual(Event.objects.count(), 2)


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def stroke(seq, boot_id="03e1420d"):
    return parse(raw(seq=seq, boot_id=boot_id))


class StoreTests(TestCase):
    COUNT = 4
    INTERVAL_S = 10.0

    def make(self, **kw):
        self.clock = FakeClock()
        kw.setdefault("flush_count", self.COUNT)
        kw.setdefault("flush_interval_s", self.INTERVAL_S)
        return EventStore(clock=self.clock, host="sandbells2", **kw)

    def test_buffers_below_thresholds(self):
        st = self.make()
        for seq in range(1, self.COUNT):
            self.assertEqual(st.add(stroke(seq)), 0)
        self.assertEqual(len(st), self.COUNT - 1)
        self.assertEqual(Event.objects.count(), 0)

    def test_flush_on_count(self):
        st = self.make()
        for seq in range(1, self.COUNT):
            st.add(stroke(seq))
        self.assertEqual(st.add(stroke(self.COUNT)), self.COUNT)
        self.assertEqual(len(st), 0)
        self.assertEqual(Event.objects.count(), self.COUNT)
        self.assertEqual(st.stats["flushes"], 1)
        self.assertEqual(Event.objects.first().host, "sandbells2")

    def test_flush_on_interval_measured_from_oldest(self):
        st = self.make()
        self.clock.t = 100.0                     # long idle before: no effect
        st.add(stroke(1))
        self.assertEqual(Event.objects.count(), 0)
        self.clock.t += self.INTERVAL_S - 1
        self.assertEqual(st.add(stroke(2)), 0)
        self.clock.t += 1
        self.assertTrue(st.due())
        self.assertEqual(st.poll(), 2)
        self.assertEqual(Event.objects.count(), 2)
        self.assertFalse(st.due())
        self.assertEqual(st.poll(), 0)

    def test_explicit_flush_and_empty_flush(self):
        st = self.make()
        self.assertEqual(st.flush(), 0)
        st.add(stroke(1))
        self.assertEqual(st.flush(), 1)
        self.assertEqual(Event.objects.count(), 1)

    def test_duplicates_ignored_across_batches(self):
        st = self.make()
        st.add(stroke(1))
        st.add(stroke(2))
        st.flush()
        st.add(stroke(2))                        # resend after reconnect
        st.add(stroke(3))
        st.flush()
        self.assertEqual(sorted(Event.objects.values_list("seq", flat=True)),
                         [1, 2, 3])

    def test_db_error_keeps_buffer(self):
        st = self.make()
        st.add(stroke(1))
        with mock.patch.object(Event.objects, "bulk_create",
                               side_effect=RuntimeError("locked")):
            with self.assertRaises(RuntimeError):
                st.flush()
        self.assertEqual((len(st), st.stats["errors"]), (1, 1))
        self.assertEqual(st.flush(), 1)          # retry succeeds

    def test_max_buffered_drops_oldest(self):
        cap = 3
        st = self.make(flush_count=cap * 10, max_buffered=cap)
        for seq in range(1, cap + 3):
            st.add(stroke(seq))
        self.assertEqual((len(st), st.stats["dropped"]), (cap, 2))
        st.flush()
        self.assertEqual(sorted(Event.objects.values_list("seq", flat=True)),
                         [3, 4, 5])


class GapTests(SimpleTestCase):
    def test_contiguous(self):
        g = GapTracker()
        kinds = [g.observe("sw", "b1", s).kind for s in (1, 2, 3)]
        self.assertEqual(kinds, [C.GAP_FIRST, C.GAP_OK, C.GAP_OK])
        self.assertEqual(g.missing_total, 0)

    def test_gap_reports_missing_range(self):
        g = GapTracker()
        g.observe("sw", "b1", 1)
        obs = g.observe("sw", "b1", 5)
        self.assertEqual((obs.kind, obs.missing, obs.missing_count),
                         (C.GAP_GAP, (2, 4), 3))
        self.assertEqual(g.observe("sw", "b1", 6).kind, C.GAP_OK)
        self.assertEqual(g.missing_total, 3)

    def test_duplicate_and_out_of_order(self):
        g = GapTracker()
        for s in (1, 2, 3):
            g.observe("sw", "b1", s)
        self.assertEqual(g.observe("sw", "b1", 3).kind, C.GAP_DUPLICATE)
        self.assertEqual(g.observe("sw", "b1", 2).kind, C.GAP_OUT_OF_ORDER)
        self.assertEqual(g.observe("sw", "b1", 4).kind, C.GAP_OK)  # last kept

    def test_new_boot_is_reset_not_gap(self):
        g = GapTracker()
        for s in (1, 2, 3, 4):
            g.observe("sw", "b1", s)
        obs = g.observe("sw", "b2", 1)
        self.assertEqual((obs.kind, obs.missing), (C.GAP_RESET, None))
        self.assertEqual(g.observe("sw", "b2", 2).kind, C.GAP_OK)
        self.assertEqual(g.missing_total, 0)

    def test_reset_mid_boot_reports_missed_start(self):
        g = GapTracker()
        g.observe("sw", "b1", 1)
        obs = g.observe("sw", "b2", 4)           # connected late after reboot
        self.assertEqual((obs.kind, obs.missing), (C.GAP_RESET, (1, 3)))

    def test_first_seen_mid_boot(self):
        obs = GapTracker().observe("sw", "b1", 10)
        self.assertEqual((obs.kind, obs.missing), (C.GAP_FIRST, (1, 9)))

    def test_sources_independent(self):
        g = GapTracker()
        g.observe("sw", "b1", 1)
        self.assertEqual(g.observe("sense", "x", 1).kind, C.GAP_FIRST)
        self.assertEqual(g.observe("sw", "b1", 2).kind, C.GAP_OK)


class PragmaTests(TestCase):
    def test_file_db_gets_wal_normal_busy_timeout(self):
        with tempfile.TemporaryDirectory() as d:
            con = sqlite3.connect(os.path.join(d, "t.sqlite3"))
            try:
                apply_pragmas(con)
                q = lambda p: con.execute("PRAGMA %s" % p).fetchone()[0]
                self.assertEqual(q("journal_mode").upper(), C.SQLITE_JOURNAL_MODE)
                self.assertEqual(q("synchronous"), 1)          # 1 = NORMAL
                self.assertEqual(q("busy_timeout"), C.SQLITE_BUSY_TIMEOUT_MS)
            finally:
                con.close()

    def test_signal_applied_to_django_connection(self):
        with connection.cursor() as cur:
            cur.execute("PRAGMA busy_timeout")
            self.assertEqual(cur.fetchone()[0], C.SQLITE_BUSY_TIMEOUT_MS)

    def test_other_vendors_untouched(self):
        other = mock.Mock(vendor="postgresql")
        on_connection_created(sender=None, connection=other)
        other.cursor.assert_not_called()
