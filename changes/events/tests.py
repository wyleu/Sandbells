import json
from datetime import datetime, timezone

from django.test import SimpleTestCase, TestCase

from . import constants as C
from .models import Event
from .parse import ParseError, parse

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
