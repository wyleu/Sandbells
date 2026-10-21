"""Ingest path without a network: fake socket, fake clock, fake stop."""

import json
import logging
import signal
import socket
import tempfile
import threading
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from . import constants as C
from . import wsclient
from .backoff import Backoff
from .config import resolve_url, url_from_settings
from .ingest import Ingest
from .parse import parse
from .management.commands import ingest_events as cmd
from .models import Event
from .store import EventStore
from .tests import FakeClock, raw

SANDSWING_URL = "ws://192.168.0.81/ws"
_quiet = {}


def setUpModule():
    """Keep test output clean; assertLogs still sees records."""
    log = logging.getLogger(C.LOGGER_NAME)
    _quiet.update(handlers=log.handlers[:], propagate=log.propagate,
                  level=log.level)
    log.handlers = [logging.NullHandler()]
    log.propagate = False
    log.setLevel(logging.CRITICAL)


def tearDownModule():
    log = logging.getLogger(C.LOGGER_NAME)
    log.handlers = _quiet["handlers"]
    log.propagate = _quiet["propagate"]
    log.setLevel(_quiet["level"])


class FakeWs:
    """recv() plays a script: str/bytes -> frame, TIMEOUT -> timeout,
    a callable -> called, then a timeout.  Script exhausted -> closed."""
    TIMEOUT = object()

    def __init__(self, script):
        self.script = list(script)
        self.connected = True
        self.closed = False
        self.timeout = None

    def settimeout(self, t):
        self.timeout = t

    def recv(self):
        if not self.script:
            self.connected = False
            raise ConnectionResetError("closed")
        item = self.script.pop(0)
        if item is self.TIMEOUT:
            raise socket.timeout()
        if callable(item):
            item()
            raise socket.timeout()
        return item

    def close(self):
        self.closed = True
        self.connected = False


class StopAfter:
    """threading.Event stand-in: wait() records delays, sets after n waits."""

    def __init__(self, waits=0):
        self.delays = []
        self._left = waits
        self._set = False

    def is_set(self):
        return self._set

    def set(self):
        self._set = True

    def wait(self, delay):
        self.delays.append(delay)
        self._left -= 1
        if self._left <= 0:
            self._set = True
        return self._set


def make_ingest(**store_kw):
    clock = FakeClock()
    store_kw.setdefault("flush_count", 1000)
    store = EventStore(clock=clock, host="sandbells2", **store_kw)
    return Ingest(store, clock=clock), clock


class BackoffTests(SimpleTestCase):
    def test_sequence_doubles_and_caps(self):
        b = Backoff(initial_s=1, factor=2, max_s=10)
        self.assertEqual([b.next() for _ in range(6)], [1, 2, 4, 8, 10, 10])

    def test_reset(self):
        b = Backoff(initial_s=1, factor=2, max_s=10)
        b.next(), b.next()
        b.reset()
        self.assertEqual(b.next(), 1)

    def test_defaults_are_named_constants(self):
        b = Backoff()
        self.assertEqual(b.next(), C.BACKOFF_INITIAL_S)
        for _ in range(100):
            d = b.next()
        self.assertEqual(d, C.BACKOFF_MAX_S)


class FrameTests(TestCase):
    def test_frames_parsed_tracked_stored(self):
        ing, _ = make_ingest()
        for seq in (1, 2, 5):
            ing.handle_frame(raw(seq=seq))
        ing.handle_frame("not json")
        ing.handle_frame(raw(schema="other"))
        self.assertEqual(ing.frames, 5)
        self.assertEqual(ing.rejects, {C.R_NOT_JSON: 1, C.R_BAD_SCHEMA: 1})
        self.assertEqual(ing.tracker.missing_total, 2)
        self.assertEqual(ing.flush(), 3)
        self.assertEqual(sorted(Event.objects.values_list("seq", flat=True)),
                         [1, 2, 5])

    def test_reject_warning_rate_limited(self):
        ing, clock = make_ingest()
        with self.assertLogs(C.LOGGER_NAME, "WARNING") as cm:
            for _ in range(5):
                ing.handle_frame("x")
            clock.t += C.REJECT_LOG_INTERVAL_S
            ing.handle_frame("x")
        self.assertEqual(len(cm.output), 2)
        self.assertEqual(ing.rejects[C.R_NOT_JSON], 6)

    def test_gap_logged(self):
        ing, _ = make_ingest()
        ing.handle_frame(raw(seq=1))
        with self.assertLogs(C.LOGGER_NAME, "WARNING") as cm:
            ing.handle_frame(raw(seq=4))
        self.assertIn("missing seq 2-3", cm.output[0])

    def test_summary_periodic(self):
        ing, clock = make_ingest()
        self.assertFalse(ing.maybe_summary())
        clock.t += C.SUMMARY_INTERVAL_S
        with self.assertLogs(C.LOGGER_NAME, "INFO") as cm:
            self.assertTrue(ing.maybe_summary())
        self.assertIn("frames 0", cm.output[0])

    def test_db_error_logged_not_raised(self):
        ing, _ = make_ingest()
        ing.handle_frame(raw(seq=1))
        with mock.patch.object(Event.objects, "bulk_create",
                               side_effect=RuntimeError("locked")):
            with self.assertLogs(C.LOGGER_NAME, "ERROR"):
                self.assertEqual(ing.flush(), 0)
        self.assertEqual(len(ing.store), 1)
        self.assertEqual(ing.flush(), 1)


class ResumeTests(TestCase):
    BOOT = "216a0e79"

    def store_rows(self, seqs, boot_id=BOOT):
        Event.objects.bulk_create(
            [Event.from_parsed(parse(raw(seq=s, boot_id=boot_id)), host="x")
             for s in seqs])

    def test_resume_after_stored_max_no_missed_start(self):
        self.store_rows(range(3, 22))                  # earlier manual run
        ing, _ = make_ingest()
        with self.assertLogs(C.LOGGER_NAME, "INFO") as cm:
            obs = ing.handle_frame(raw(seq=22, boot_id=self.BOOT))
        self.assertEqual((obs.kind, obs.missing), (C.GAP_OK, None))
        self.assertIn("resume sandswing/%s after seq 21 (stored)" % self.BOOT,
                      cm.output[0])
        self.assertEqual(ing.tracker.missing_total, 0)

    def test_resume_then_real_gap(self):
        self.store_rows([1, 2, 3])
        ing, _ = make_ingest()
        obs = ing.handle_frame(raw(seq=6, boot_id=self.BOOT))
        self.assertEqual((obs.kind, obs.missing), (C.GAP_GAP, (4, 5)))

    def test_nothing_stored_reports_missed_start(self):
        self.store_rows([1, 2], boot_id="otherboot")    # other boot ignored
        ing, _ = make_ingest()
        obs = ing.handle_frame(raw(seq=22, boot_id=self.BOOT))
        self.assertEqual((obs.kind, obs.missing), (C.GAP_FIRST, (1, 21)))

    def test_one_lookup_per_boot(self):
        self.store_rows([1])
        ing, _ = make_ingest()
        with self.assertNumQueries(1):
            for s in (2, 3, 4):
                ing.handle_frame(raw(seq=s, boot_id=self.BOOT))

    def test_lookup_error_falls_back_unseeded(self):
        def broken(src, boot_id):
            raise RuntimeError("locked")
        clock = FakeClock()
        ing = Ingest(EventStore(clock=clock, host="x"), clock=clock,
                     last_stored=broken)
        with self.assertLogs(C.LOGGER_NAME, "WARNING"):
            obs = ing.handle_frame(raw(seq=5, boot_id=self.BOOT))
        self.assertEqual(obs.kind, C.GAP_FIRST)


class ClientLoopTests(TestCase):
    def test_reads_frames_idles_on_timeout_and_flushes_on_disconnect(self):
        ing, _ = make_ingest()
        ws = FakeWs([raw(seq=1), FakeWs.TIMEOUT, raw(seq=2).encode(), "",
                     raw(seq=3)])
        stop = StopAfter(waits=1)
        with mock.patch.object(ing, "idle", wraps=ing.idle) as idle:
            wsclient.run(SANDSWING_URL, ing, stop,
                         connect=lambda url, t: ws, backoff=Backoff(1, 2, 8))
        self.assertGreaterEqual(idle.call_count, 1)
        self.assertEqual(ws.timeout, C.WS_RECV_TIMEOUT_S)
        self.assertTrue(ws.closed)
        self.assertEqual(Event.objects.count(), 3)
        self.assertEqual(stop.delays, [1])       # one reconnect wait

    def test_connect_failures_back_off(self):
        ing, _ = make_ingest()
        stop = StopAfter(waits=4)

        def refuse(url, t):
            raise ConnectionRefusedError("refused")

        wsclient.run(SANDSWING_URL, ing, stop, connect=refuse,
                     backoff=Backoff(1, 2, 4))
        self.assertEqual(stop.delays, [1, 2, 4, 4])

    def test_backoff_resets_after_good_connection(self):
        ing, _ = make_ingest()
        stop = StopAfter(waits=3)
        attempts = iter([ConnectionRefusedError("x"), FakeWs([raw(seq=1)]),
                         ConnectionRefusedError("x")])

        def connect(url, t):
            r = next(attempts)
            if isinstance(r, Exception):
                raise r
            return r

        wsclient.run(SANDSWING_URL, ing, stop, connect=connect,
                     backoff=Backoff(1, 2, 8))
        self.assertEqual(stop.delays, [1, 1, 2])

    def test_stop_signal_flushes_buffer(self):
        ing, _ = make_ingest()
        stop = threading.Event()
        handler = cmd.make_stop_handler(stop)
        # SIGTERM arrives while the socket is open and idle
        ws = FakeWs([raw(seq=1), raw(seq=2),
                     lambda: handler(signal.SIGTERM, None), raw(seq=3)])
        with self.assertLogs(C.LOGGER_NAME, "INFO"):
            wsclient.run(SANDSWING_URL, ing, stop, connect=lambda url, t: ws)
        self.assertTrue(stop.is_set() and ws.closed)
        self.assertEqual(len(ing.store), 0)
        self.assertEqual(sorted(Event.objects.values_list("seq", flat=True)),
                         [1, 2])                 # seq 3 never read


class ConfigTests(SimpleTestCase):
    def write(self, d, cfg):
        p = Path(d) / "settings.json"
        p.write_text(json.dumps(cfg))
        return p

    def test_option_wins(self):
        self.assertEqual(resolve_url("ws://10.0.0.9/ws", path="/nonexistent"),
                         ("ws://10.0.0.9/ws", "option"))

    def test_settings_device(self):
        with tempfile.TemporaryDirectory() as d:
            p = self.write(d, {"status": {"devices": [
                {"family": "sandsense", "ws_url": "ws://192.168.0.154/ws"},
                {"family": "sandswing", "ws_url": SANDSWING_URL}]}})
            self.assertEqual(url_from_settings(p), SANDSWING_URL)
            self.assertEqual(resolve_url(None, path=p),
                             (SANDSWING_URL, "settings"))

    def test_default_when_absent_or_broken(self):
        with tempfile.TemporaryDirectory() as d:
            p = self.write(d, {"status": {"devices": [{"family": "sandswing"}]}})
            self.assertEqual(resolve_url(None, path=p),
                             (C.WS_DEFAULT_URL, "default"))
            bad = Path(d) / "bad.json"
            bad.write_text("{")
            self.assertEqual(resolve_url(None, path=bad)[1], "default")
        self.assertEqual(resolve_url(None, path="/nonexistent")[1], "default")


class CommandTests(SimpleTestCase):
    def run_cmd(self, *args):
        with mock.patch.object(cmd.wsclient, "run") as run, \
                mock.patch.object(cmd, "EventStore"), \
                mock.patch.object(cmd, "setup_logging",
                                  return_value=logging.getLogger(C.LOGGER_NAME)):
            call_command("ingest_events", *args)
        return run.call_args[0]

    def test_url_option(self):
        url, ingest, stop = self.run_cmd("--url", "ws://10.42.0.50/ws")
        self.assertEqual(url, "ws://10.42.0.50/ws")
        self.assertIsInstance(ingest, Ingest)
        self.assertFalse(stop.is_set())

    def test_default_url(self):
        with mock.patch.dict("os.environ",
                             {C.SANDBELLS_SETTINGS_ENV: "/nonexistent.json"}):
            url, _, _ = self.run_cmd()
        self.assertEqual(url, C.WS_DEFAULT_URL)

    def test_signal_handlers_restored(self):
        before = signal.getsignal(signal.SIGTERM)
        self.run_cmd("--url", SANDSWING_URL)
        self.assertEqual(signal.getsignal(signal.SIGTERM), before)

    def test_setup_logging_levels(self):
        log = logging.getLogger(C.LOGGER_NAME)
        saved_handlers, saved_level = log.handlers[:], log.level
        try:
            log.handlers = []
            self.assertEqual(cmd.setup_logging(1).level, logging.INFO)
            self.assertEqual(cmd.setup_logging(cmd.VERBOSITY_DEBUG).level,
                             logging.DEBUG)
            self.assertEqual(len(log.handlers), 1)   # not added twice
        finally:
            log.handlers = saved_handlers
            log.setLevel(saved_level)
            log.propagate = False

    def test_handler_sets_stop(self):
        stop = threading.Event()
        with self.assertLogs(C.LOGGER_NAME, "INFO"):
            cmd.make_stop_handler(stop)(signal.SIGTERM, None)
        self.assertTrue(stop.is_set())
