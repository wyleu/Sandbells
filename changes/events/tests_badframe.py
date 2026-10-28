"""Frames the ingest cannot decode: skipped and counted, the link kept
until BAD_FRAME_LIMIT in a row (framestate.py, Ingest, wsclient)."""

import json
import sys
from unittest import mock

from django.test import SimpleTestCase, TestCase

from . import constants as C
from . import wsclient
from .backoff import Backoff
from .framestate import FrameGuard, build_table
from .models import Event
from .tests import raw
from .tests_ingest import (SANDSWING_URL, FakeWs, SendingWs, StopAfter,
                           make_ingest, panel_hb, setUpModule, tearDownModule)  # noqa: F401  (quiet log)

LIMIT = C.BAD_FRAME_LIMIT
GOOD, BAD = C.FRAME_GOOD, C.FRAME_BAD


def long_heartbeat(size=1400):
    """A sand.panel/v1 heartbeat of about `size` bytes, padded in body.net."""
    d = json.loads(panel_hb())
    d["body"]["pad"] = "x" * size
    return json.dumps(d)


def cut_off(text, at=1400):
    """The heartbeat as seen in the field: cut off mid-string."""
    return text[:at]


def payload_error(data):
    """What websocket-client raises for text that is not valid UTF-8."""
    import websocket
    return websocket.WebSocketPayloadException("cannot decode: %r" % data)


def utf8_error(data):
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as e:
        return e
    raise AssertionError("data was valid UTF-8")


BAD_UTF8 = b'{"schema":"sand.panel/v1","body":{"s":"caf\xc3'      # cut inside a character


class FrameTableTests(SimpleTestCase):
    def test_default_limit_is_the_documented_first_guess(self):
        self.assertEqual(C.BAD_FRAME_LIMIT, 5)
        self.assertEqual(FrameGuard().limit, 5)

    def test_table_for_limit_3_is_exactly_this(self):
        self.assertEqual(build_table(3), {
            (0, GOOD): (0, ("reset",)), (0, BAD): (1, ("count",)),
            (1, GOOD): (0, ("reset",)), (1, BAD): (2, ("count",)),
            (2, GOOD): (0, ("reset",)), (2, BAD): (3, ("count", "disconnect")),
            (3, GOOD): (0, ("reset",)), (3, BAD): (3, ("count", "disconnect")),
        })

    def test_every_state_and_event_has_a_row(self):
        table = build_table(LIMIT)
        self.assertEqual(set(table), {(s, e) for s in range(LIMIT + 1)
                                      for e in (GOOD, BAD)})

    def test_disconnect_only_on_the_nth_bad_frame_in_a_row(self):
        g = FrameGuard(LIMIT)
        for i in range(1, LIMIT):
            self.assertEqual(g.feed(BAD), (C.ACT_COUNT,), "bad frame %d" % i)
            self.assertEqual(g.state, i)
        self.assertEqual(g.feed(BAD), (C.ACT_COUNT, C.ACT_DISCONNECT))

    def test_good_frame_resets_the_run(self):
        g = FrameGuard(LIMIT)
        for _ in range(LIMIT - 1):
            g.feed(BAD)
        self.assertEqual(g.feed(GOOD), (C.ACT_RESET,))
        self.assertEqual(g.state, 0)
        for _ in range(LIMIT - 1):
            self.assertNotIn(C.ACT_DISCONNECT, g.feed(BAD))

    def test_new_connection_starts_clean(self):
        g = FrameGuard(2)
        g.feed(BAD)
        g.reset()
        self.assertEqual(g.feed(BAD), (C.ACT_COUNT,))


class IngestBadFrameTests(TestCase):
    def test_truncated_heartbeat_is_skipped_counted_and_logged_once(self):
        ing, _ = make_ingest()
        frame = cut_off(long_heartbeat())
        self.assertEqual(len(frame), 1400)
        with self.assertLogs(C.LOGGER_NAME, "WARNING") as cm:
            self.assertIsNone(ing.handle_frame(frame))
        self.assertEqual(len(cm.output), 1)
        line = cm.output[0]
        self.assertIn("bad frame skipped (not_json)", line)
        self.assertIn("len 1400", line)
        b = frame.encode()
        self.assertIn(repr(b[:60]), line)
        self.assertIn(repr(b[-60:]), line)
        self.assertNotIn(frame[100:200], line)          # only the two ends
        self.assertIn("1 in a row, 1 total", line)
        self.assertEqual((ing.bad, ing.guard.state, ing.drop_reason), (1, 1, None))
        self.assertEqual(ing.rejects, {C.R_NOT_JSON: 1})
        self.assertEqual(len(ing.store), 0)

    def test_summary_has_bad_count(self):
        ing, _ = make_ingest()
        ing.handle_frame("{")
        ing.handle_frame("{")
        self.assertIn("frames 2, ignored 0, bad 2, accepted 0", ing.summary())

    def test_burst_logs_once_then_again_after_the_interval(self):
        ing, clock = make_ingest()
        with self.assertLogs(C.LOGGER_NAME, "WARNING") as cm:
            for _ in range(LIMIT - 1):
                ing.handle_frame("{")
            clock.t += C.BAD_FRAME_LOG_INTERVAL_S
            ing.handle_frame(raw(seq=1))               # a good one: run restarts
            ing.handle_frame("{")
        self.assertEqual(len(cm.output), 2)
        self.assertIn("3 more not logged", cm.output[1])
        self.assertIn("1 in a row, 5 total", cm.output[1])

    def test_not_utf8_bytes_are_bad_too(self):
        ing, _ = make_ingest()
        with self.assertLogs(C.LOGGER_NAME, "WARNING") as cm:
            ing.handle_frame(BAD_UTF8)
        self.assertIn("(not_utf8)", cm.output[0])
        self.assertEqual(ing.bad, 1)

    def test_other_rejects_are_not_bad_frames(self):
        ing, _ = make_ingest()
        for _ in range(LIMIT + 2):
            ing.handle_frame(raw(schema="other"))
        self.assertEqual((ing.bad, ing.guard.state, ing.drop_reason), (0, 0, None))

    def test_limit_in_a_row_sets_drop_reason(self):
        ing, _ = make_ingest()
        for _ in range(LIMIT - 1):
            ing.handle_frame("{")
        self.assertIsNone(ing.drop_reason)
        ing.handle_frame("{")
        self.assertEqual(ing.drop_reason, "%d bad frames in a row" % LIMIT)

    def test_good_frame_resets_the_run(self):
        ing, _ = make_ingest()
        seq = 0
        for _ in range(3):
            for _ in range(LIMIT - 1):
                ing.handle_frame("{")
            seq += 1
            ing.handle_frame(raw(seq=seq))
        self.assertEqual((ing.bad, ing.guard.state, ing.drop_reason),
                         (3 * (LIMIT - 1), 0, None))

    def test_panel_heartbeat_and_other_rejects_count_as_good(self):
        ing, _ = make_ingest()
        for good in (panel_hb(), raw(schema="other")):
            for _ in range(LIMIT - 1):
                ing.handle_frame("{")
            ing.handle_frame(good)
            self.assertEqual(ing.guard.state, 0)
        self.assertIsNone(ing.drop_reason)

    def test_skipped_event_frame_shows_as_a_gap_and_the_rest_is_stored(self):
        ing, _ = make_ingest()
        ing.handle_frame(raw(seq=1))
        ing.handle_frame(raw(seq=2)[:60])               # cut off: skipped
        with self.assertLogs(C.LOGGER_NAME, "WARNING") as cm:
            ing.handle_frame(raw(seq=3))
        self.assertIn("missing seq 2-2", cm.output[0])
        self.assertEqual((ing.tracker.missing_total, ing.bad), (1, 1))
        ing.flush()
        self.assertEqual(sorted(Event.objects.values_list("seq", flat=True)), [1, 3])

    def test_skipped_heartbeat_is_no_gap(self):
        ing, _ = make_ingest()
        ing.handle_frame(raw(seq=1))
        ing.handle_frame(cut_off(long_heartbeat()))
        ing.handle_frame(raw(seq=2))
        self.assertEqual(ing.tracker.missing_total, 0)

    def test_transport_bad_frame_counts_in_frames_and_summary(self):
        ing, _ = make_ingest()
        with self.assertLogs(C.LOGGER_NAME, "WARNING") as cm:
            self.assertFalse(ing.bad_frame(BAD_UTF8))
        self.assertIn("bad frame skipped (cannot decode)", cm.output[0])
        self.assertIn("len %d" % len(BAD_UTF8), cm.output[0])
        self.assertIn("frames 1, ignored 0, bad 1", ing.summary())

    def test_new_connection_clears_the_run_and_the_reason(self):
        ing, _ = make_ingest()
        for _ in range(LIMIT):
            ing.handle_frame("{")
        ing.new_connection()
        self.assertEqual((ing.guard.state, ing.drop_reason), (0, None))


class UndecodableBytesTests(SimpleTestCase):
    def test_from_unicode_decode_error(self):
        self.assertEqual(wsclient.undecodable_bytes(utf8_error(BAD_UTF8)), BAD_UTF8)

    def test_from_library_payload_exception(self):
        self.assertEqual(wsclient.undecodable_bytes(payload_error(BAD_UTF8)), BAD_UTF8)

    def test_unparsable_message_falls_back_to_its_text(self):
        e = payload_error(b"x")
        e.args = ("cannot decode: b'unterminated",)
        self.assertEqual(wsclient.undecodable_bytes(e), b"cannot decode: b'unterminated")

    def test_default_connect_skips_the_librarys_utf8_check(self):
        fake = mock.Mock()
        with mock.patch.dict(sys.modules, {"websocket": fake}):
            wsclient.default_connect("ws://x/ws", 5)
        self.assertIs(fake.create_connection.call_args.kwargs["skip_utf8_validation"], True)


class ClientBadFrameTests(TestCase):
    def read(self, script, ing=None):
        ing = ing or make_ingest()[0]
        ws = SendingWs(script)
        n = wsclient.read_frames(ws, ing, StopAfter(waits=99),
                                 wsclient.timeout_errors())
        return ing, n

    def test_undecodable_frames_do_not_disconnect(self):
        ing, n = self.read([raw(seq=1), payload_error(BAD_UTF8), raw(seq=2),
                            utf8_error(BAD_UTF8), cut_off(long_heartbeat()),
                            raw(seq=3)])
        self.assertEqual(wsclient.read_frames.reason, "closed")     # the script ended
        self.assertEqual(ing.bad, 3)
        self.assertEqual(ing.tracker.missing_total, 0)
        ing.flush()
        self.assertEqual(Event.objects.filter(src="sandswing").count(), 3)

    def test_limit_in_a_row_disconnects_with_a_reason(self):
        script = [raw(seq=1)] + [payload_error(BAD_UTF8)] * LIMIT + [raw(seq=2)]
        with self.assertLogs(C.LOGGER_NAME, "WARNING") as cm:
            ing, n = self.read(script)
        self.assertEqual(wsclient.read_frames.reason,
                         "%d bad frames in a row" % LIMIT)
        self.assertEqual(n, 1)
        self.assertIn("disconnected: %d bad frames in a row" % LIMIT, cm.output[-1])
        ing.flush()
        self.assertEqual(Event.objects.filter(src="sandswing").count(), 1)

    def test_limit_in_a_row_of_cut_off_json_disconnects_too(self):
        with self.assertLogs(C.LOGGER_NAME, "WARNING"):
            ing, n = self.read([cut_off(long_heartbeat())] * LIMIT + [raw(seq=1)])
        self.assertEqual(wsclient.read_frames.reason,
                         "%d bad frames in a row" % LIMIT)
        self.assertEqual(n, LIMIT)

    def test_good_frames_between_bad_ones_keep_the_link(self):
        script = []
        for seq in range(1, 4):
            script += [payload_error(BAD_UTF8)] * (LIMIT - 1) + [raw(seq=seq)]
        ing, n = self.read(script)
        self.assertEqual(wsclient.read_frames.reason, "closed")
        self.assertEqual(ing.bad, 3 * (LIMIT - 1))

    def test_bad_frame_keeps_the_peer_silence_clock_alive(self):
        ing, _ = make_ingest()
        t = [0.0]

        def later():
            t[0] += C.PEER_SILENT_S - 1

        ws = SendingWs([panel_hb(), later, payload_error(BAD_UTF8), later,
                        FakeWs.TIMEOUT, raw(seq=1)])
        wsclient.read_frames(ws, ing, StopAfter(waits=99),
                             wsclient.timeout_errors(), clock=lambda: t[0])
        self.assertEqual(wsclient.read_frames.reason, "closed")     # not "peer silent"

    def test_a_new_connection_starts_the_run_again(self):
        ing, _ = make_ingest()
        for _ in range(LIMIT - 1):
            ing.handle_frame("{")
        ing, n = self.read([payload_error(BAD_UTF8)] * (LIMIT - 1), ing)
        self.assertEqual(wsclient.read_frames.reason, "closed")

    def test_run_notes_the_reason_and_reconnects(self):
        ing, _ = make_ingest()
        socks = iter([FakeWs([raw(seq=1)] + [payload_error(BAD_UTF8)] * LIMIT),
                      FakeWs([raw(seq=2)])])
        stop = StopAfter(waits=2)
        wsclient.run(SANDSWING_URL, ing, stop, connect=lambda u, t: next(socks),
                     backoff=Backoff(1, 2, 8))
        reasons = list(Event.objects.filter(src=C.INGEST_SRC, body__what="disconnected")
                       .order_by("seq").values_list("body__reason", flat=True))
        self.assertEqual(reasons, ["%d bad frames in a row" % LIMIT, "closed"])
        self.assertEqual(Event.objects.filter(src="sandswing").count(), 2)
