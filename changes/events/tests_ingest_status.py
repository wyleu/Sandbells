"""The Ingest page (/events/ingest/) and ingest_udp's status file."""

import json
import logging
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from unittest import mock

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from . import constants as C
from . import ingestpage, udpingest
from .ingest import Ingest
from .ingeststatus import IngestStatus, read_ingest_status
from .models import Event
from .tests import FakeClock, raw, stroke

PEER = "192.168.0.81"
UID = "7091CDAB9DBD5305"


def heartbeat(seq=7, boot_id="b007"):
    return json.dumps({"schema": C.SCHEMA_PANEL_V1, "type": C.TYPE_HEARTBEAT,
                       "src": "sandswing", "id": "sandswing-pico",
                       "boot_id": boot_id, "seq": seq, "body": {C.BODY_UID: UID}})


_quiet = {}


def setUpModule():
    """Keep test output clean (bad frame WARNINGs are expected here)."""
    log = logging.getLogger(C.LOGGER_NAME)
    _quiet.update(handlers=log.handlers[:], propagate=log.propagate)
    log.handlers, log.propagate = [logging.NullHandler()], False


def tearDownModule():
    log = logging.getLogger(C.LOGGER_NAME)
    log.handlers, log.propagate = _quiet["handlers"], _quiet["propagate"]


class TmpDir:
    def tmpdir(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        return d


class FakeStore:
    def __init__(self):
        self.added, self.stats = [], {"added": 0, "written": 0, "dropped": 0,
                                      "errors": 0, "flushes": 0}

    def __len__(self):
        return 0

    def add(self, p):
        self.added.append(p)
        self.stats["added"] += 1
        return 0

    def poll(self):
        return 0

    def flush(self):
        return 0


def make_ingest(path, clock):
    status = IngestStatus(path, host="0.0.0.0", port=C.UDP_INGEST_PORT, clock=clock)
    return Ingest(FakeStore(), clock=clock, last_stored=lambda s, b: None,
                  status=status), status


class WriterTests(SimpleTestCase, TmpDir):
    def test_counters_last_datagram_and_rejects_go_to_the_file(self):
        path = os.path.join(self.tmpdir(), "status.json")
        clock = FakeClock()
        ing, status = make_ingest(path, clock)
        ing.handle_frame(raw(seq=1), peer=PEER)
        ing.handle_frame(raw(seq=3), peer=PEER)          # seq 2 lost
        ing.handle_frame("{not json", peer="10.0.0.9")
        ing.bad_frame(b"\xff\xfe", C.R_NOT_UTF8, peer="10.0.0.9")
        ing.handle_frame(heartbeat(), peer=PEER)
        status.maybe_write(ing, force=True)
        doc, age = read_ingest_status(path)
        self.assertEqual(doc["schema"], C.INGEST_STATUS_SCHEMA)
        self.assertEqual((doc["mode"], doc["host"], doc["port"]),
                         (C.INGEST_MODE_UDP, "0.0.0.0", C.UDP_INGEST_PORT))
        c = doc["counters"]
        self.assertEqual((c["frames"], c["ignored"], c["bad"], c["accepted"]), (5, 1, 2, 2))
        self.assertEqual((c["seq_gaps"], c["seq_missing"]), (1, 1))
        self.assertEqual(doc["last"]["peer"], PEER)
        self.assertEqual((doc["last"]["uid"], doc["last"]["boot_id"]), (UID, "b007"))
        reasons = [r["reason"] for r in doc["recent_rejects"]]
        self.assertEqual(reasons, [C.R_NOT_JSON, C.R_NOT_UTF8])
        self.assertEqual(doc["recent_rejects"][0]["peer"], "10.0.0.9")
        self.assertLess(age, C.INGEST_STATUS_STALE_MS)
        self.assertEqual(os.stat(path).st_mode & 0o777, C.LINK_STATE_MODE)
        self.assertEqual(os.listdir(os.path.dirname(path)), ["status.json"])  # no temp left

    def test_event_identity_is_its_device_id_and_boot(self):
        ing, status = make_ingest(None, FakeClock())
        ing.handle_frame(raw(seq=1, boot_id="abcd1234"), peer=PEER)
        self.assertEqual((status.last["uid"], status.last["boot_id"], status.last["seq"]),
                         ("sandswing-pico", "abcd1234", 1))

    def test_writes_are_rate_limited(self):
        path = os.path.join(self.tmpdir(), "status.json")
        clock = FakeClock()
        ing, status = make_ingest(path, clock)
        ing.handle_frame(raw(seq=1), peer=PEER)              # first: written
        self.assertEqual(status.writes, 1)
        for seq in range(2, 20):                              # same instant: not again
            ing.handle_frame(raw(seq=seq), peer=PEER)
        self.assertEqual(status.writes, 1)
        clock.t += C.INGEST_STATUS_CHANGE_S                   # changed + 1 s: written
        ing.handle_frame(raw(seq=20), peer=PEER)
        self.assertEqual(status.writes, 2)
        clock.t += C.INGEST_STATUS_CHANGE_S
        ing.idle()                                            # quiet, nothing new: not yet
        self.assertEqual(status.writes, 2)
        clock.t += C.INGEST_STATUS_WRITE_S
        ing.idle()                                            # quiet 5 s: alive mark
        self.assertEqual(status.writes, 3)

    def test_recent_rejects_are_bounded(self):
        ing, status = make_ingest(None, FakeClock())
        for _ in range(C.INGEST_STATUS_RECENT + 5):
            ing.handle_frame("x" * 500, peer=PEER)
        status.snapshot(ing)
        self.assertEqual(len(status.doc["recent_rejects"]), C.INGEST_STATUS_RECENT)
        self.assertLessEqual(len(status.doc["recent_rejects"][0]["excerpt"]),
                             C.INGEST_STATUS_EXCERPT + 1)

    def test_unwritable_path_never_raises_into_the_receive_path(self):
        path = os.path.join(self.tmpdir(), "no", "such", "dir", "status.json")
        ing, status = make_ingest(path, FakeClock())
        obs = ing.handle_frame(raw(seq=1), peer=PEER)
        self.assertEqual(obs.kind, C.GAP_FIRST)
        self.assertEqual(len(ing.store.added), 1)
        self.assertFalse(status.maybe_write(ing, force=True))

    def test_a_broken_snapshot_never_raises_into_the_receive_path(self):
        ing, status = make_ingest(None, FakeClock())
        ing.store.stats = None                                # snapshot would TypeError
        obs = ing.handle_frame(raw(seq=1), peer=PEER)
        self.assertEqual(obs.kind, C.GAP_FIRST)
        self.assertFalse(status.maybe_write(ing, force=True))
        ing.idle()                                            # nor from the idle path

    def test_stopped_is_written(self):
        path = os.path.join(self.tmpdir(), "status.json")
        ing, status = make_ingest(path, FakeClock())
        status.stopped(ing)
        doc, _ = read_ingest_status(path)
        self.assertEqual(doc["state"], C.INGEST_STATE_STOPPED)

    def test_udp_serve_passes_the_peer_of_a_non_utf8_datagram(self):
        class Sock:
            def __init__(self, stop):
                self.items, self.stop = [b"\xff\xfe"], stop

            def recvfrom(self, n):
                if not self.items:
                    self.stop.set()
                    raise socket.timeout()
                return self.items.pop(0), (PEER, 1234)

        stop = threading.Event()
        ing, status = make_ingest(None, FakeClock())
        udpingest.serve(Sock(stop), ing, stop)
        self.assertEqual(ing.bad, 1)
        self.assertEqual(list(status.recent)[0]["peer"], PEER)
        self.assertEqual(list(status.recent)[0]["reason"], C.R_NOT_UTF8)


def no_systemd(cmd, **kw):
    raise FileNotFoundError(cmd[0])


def fake_systemctl(answers):
    """answers: {(verb, unit): stdout}; anything else: not found."""
    def run(cmd, **kw):
        if cmd[0] == "hostname":
            return subprocess.CompletedProcess(cmd, 0, "192.168.0.22 fe80::1\n", "")
        out = answers.get((cmd[1], cmd[2]))
        if out is None:
            return subprocess.CompletedProcess(
                cmd, 1, "", "Failed to get unit file state for %s: No such file or directory\n" % cmd[2])
        return subprocess.CompletedProcess(cmd, 0, out + "\n", "")
    return run


class UnitProbeTests(SimpleTestCase):
    def test_no_systemd(self):
        u = ingestpage.units(run=no_systemd)
        self.assertEqual([x["enabled"] for x in u], [ingestpage.NO_SYSTEMD] * len(C.INGEST_UNITS))
        self.assertIsNone(u[0]["installed"])

    def test_timeout(self):
        def slow(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))
        self.assertEqual(ingestpage.systemctl("is-active", "x", run=slow), "timeout")

    def test_enabled_active_and_not_found(self):
        u = ingestpage.units(run=fake_systemctl({
            ("is-enabled", "sandbells-ingest-udp.service"): "enabled",
            ("is-active", "sandbells-ingest-udp.service"): "active",
            ("is-active", "sandbells-ingest.service"): "inactive"}))
        udp, ws, midi, serial = u
        self.assertEqual((udp["installed"], udp["enabled"], udp["active"]), (True, "enabled", "active"))
        self.assertEqual((ws["installed"], ws["enabled"], ws["active"]), (False, "not-found", "inactive"))
        self.assertEqual((midi["unit"], midi["installed"]), ("sandbells-ingest-midi.service", False))
        self.assertIn("ingest_midi", midi["mode"])
        self.assertEqual((serial["unit"], serial["installed"]), ("sandbells-ingest-serial.service", False))
        self.assertIn("ingest_serial", serial["mode"])

    def test_udp_bound_from_proc(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        p = os.path.join(d, "udp")
        with open(p, "w") as f:
            f.write("  sl  local_address rem_address   st\n"
                    "  1: 00000000:%04X 00000000:0000 07\n" % C.UDP_INGEST_PORT)
        self.assertTrue(ingestpage.udp_bound(C.UDP_INGEST_PORT, p))
        self.assertFalse(ingestpage.udp_bound(C.UDP_INGEST_PORT + 1, p))
        self.assertIsNone(ingestpage.udp_bound(C.UDP_INGEST_PORT, os.path.join(d, "none")))


class IngestPageTests(TestCase, TmpDir):
    def setUp(self):
        self.path = os.path.join(self.tmpdir(), "status.json")
        self.midi_path = os.path.join(os.path.dirname(self.path), "midi_status.json")
        env = mock.patch.dict(os.environ, {C.INGEST_STATUS_ENV: self.path,
                                           C.MIDI_STATUS_ENV: self.midi_path})
        env.start()
        self.addCleanup(env.stop)
        run = mock.patch("events.ingestpage.subprocess.run", side_effect=no_systemd)
        run.start()
        self.addCleanup(run.stop)

    def write_status(self, age_s=0, last_ago_s=1, **doc):
        clock = FakeClock()
        status = IngestStatus(self.path, host="0.0.0.0", port=C.UDP_INGEST_PORT, clock=clock)
        ing = Ingest(FakeStore(), clock=clock, last_stored=lambda s, b: None, status=status)
        ing.handle_frame("{oops", peer="10.9.9.9")
        ing.handle_frame(heartbeat(), peer=PEER)              # the last datagram
        status.last["ms"] = int((time.time() - last_ago_s) * C.MS_PER_S)
        status.doc.update(doc)
        status.maybe_write(ing, force=True)
        if age_s:
            t = time.time() - age_s
            os.utime(self.path, (t, t))

    def get(self):
        r = self.client.get(reverse("events:ingest"))
        self.assertEqual(r.status_code, 200)
        return r

    def test_url(self):
        self.assertEqual(reverse("events:ingest"), "/events/ingest/")

    def test_midi_section_shows_the_midi_status(self):
        r = self.get()
        self.assertContains(r, "No MIDI status file")
        with open(self.midi_path, "w") as f:
            json.dump({"midi": {"port": "midi:/dev/snd/midiC3D0", "connected": True,
                                "strokes": 176, "errors": 0, "disconnects": 2,
                                "stamp": {"stamped": 175, "unstamped": 1, "clocks": 30,
                                          "offset_spread": 55}}}, f)
        r = self.get()
        self.assertFalse(r.context["midi_stale"])
        for text in ("midi:/dev/snd/midiC3D0", ">yes<", ">176<", "175 ·", ">1<",
                     ">30", "55 ms", "0 · 2"):
            self.assertContains(r, text)

    def test_fresh_status_file_is_ok_with_counters_and_last_datagram(self):
        self.write_status()
        r = self.get()
        self.assertEqual(r.context["verdict"], ingestpage.V_OK)
        self.assertContains(r, 'class="verdict v-OK"')
        self.assertContains(r, PEER)
        self.assertContains(r, UID)
        self.assertContains(r, "b007")
        self.assertContains(r, C.R_NOT_JSON)                  # the rejected datagram
        self.assertContains(r, "10.9.9.9")
        self.assertEqual(r.context["counters"]["frames"], 2)
        self.assertContains(r, 'class="navbtn ingest on"')    # the top line button
        self.assertContains(r, ingestpage.NO_SYSTEMD)         # no systemd here: still renders
        self.assertContains(r, '<meta http-equiv="refresh" content="%d">' % C.INGEST_PAGE_REFRESH_S)

    def test_acks_are_on_the_page(self):
        self.write_status()
        doc, _ = read_ingest_status(self.path)
        doc["counters"].update(acks_sent=41, ack_errors=2)
        with open(self.path, "w") as f:
            json.dump(doc, f)
        r = self.get()
        self.assertContains(r, "acks sent")
        self.assertContains(r, "1 · 41")                       # heartbeats · acks sent
        self.assertContains(r, "(2 failed)")

    def test_running_but_no_recent_datagram_is_quiet(self):
        self.write_status(last_ago_s=C.INGEST_QUIET_MS // C.MS_PER_S + 5)
        self.assertEqual(self.get().context["verdict"], ingestpage.V_QUIET)

    def test_stale_status_file(self):
        self.write_status(age_s=C.INGEST_STATUS_STALE_MS // C.MS_PER_S + 5)
        r = self.get()
        self.assertEqual(r.context["verdict"], ingestpage.V_STALE)
        self.assertContains(r, 'class="verdict v-STALE"')

    def test_missing_status_file_is_down(self):
        r = self.get()
        self.assertEqual(r.context["verdict"], ingestpage.V_DOWN)
        self.assertContains(r, 'class="verdict v-DOWN"')
        self.assertContains(r, "no status file")
        self.assertContains(r, "No strokes stored.")

    def test_stopped_is_down(self):
        self.write_status(state=C.INGEST_STATE_STOPPED)
        self.assertEqual(self.get().context["verdict"], ingestpage.V_DOWN)

    def test_last_stroke_in_the_db(self):
        Event.objects.bulk_create([Event.from_parsed(stroke(n), host="test")
                                   for n in (41, 42)])
        r = self.get()
        self.assertEqual(r.context["stroke"]["seq"], 42)

    def test_db_error_still_renders(self):
        with mock.patch("events.ingestpage.last_stroke", side_effect=RuntimeError("database is locked")):
            r = self.get()
        self.assertContains(r, "DB not readable: database is locked")

    def test_units_shown(self):
        with mock.patch("events.ingestpage.subprocess.run", side_effect=fake_systemctl({
                ("is-enabled", "sandbells-ingest-udp.service"): "enabled",
                ("is-active", "sandbells-ingest-udp.service"): "active",
                ("is-enabled", "sandbells-ingest.service"): "disabled",
                ("is-active", "sandbells-ingest.service"): "inactive"})):
            r = self.get()
        self.assertContains(r, "sandbells-ingest-udp.service")
        self.assertContains(r, '<td class="good">active</td>')
        self.assertContains(r, "192.168.0.22")


class TopMenuTests(TestCase):
    def test_other_pages_link_to_ingest(self):
        r = self.client.get(reverse("events:strokes"))
        self.assertContains(r, 'href="/events/ingest/"')
        r = self.client.get(reverse("events:days"))
        self.assertContains(r, 'href="/events/ingest/"')


class IngestUdpCommandTests(TestCase, TmpDir):
    def test_link_is_connected_while_bound_and_both_files_say_stopped_after(self):
        from django.core.management import call_command
        from .linkstate import read_link_state
        d = self.tmpdir()
        link_path, status_path = os.path.join(d, "link.json"), os.path.join(d, "status.json")
        seen = {}

        def serve(sock, ingest, stop):
            seen["link"] = dict(ingest.link.ingest)
            seen["status"] = read_ingest_status(status_path)[0]

        env = {C.LINK_STATE_ENV: link_path, C.INGEST_STATUS_ENV: status_path}
        with mock.patch.dict(os.environ, env), \
                mock.patch("events.udpingest.serve", side_effect=serve), \
                mock.patch("events.management.commands.ingest_udp.setup_logging",
                           return_value=logging.getLogger(C.LOGGER_NAME)):
            call_command("ingest_udp", host="127.0.0.1", port=0)
        self.assertEqual(seen["link"]["state"], C.LINK_CONNECTED)
        self.assertEqual(seen["link"]["url"], "udp://127.0.0.1:0")
        self.assertEqual(seen["status"]["state"], C.INGEST_STATE_RUNNING)
        self.assertEqual(read_ingest_status(status_path)[0]["state"], C.INGEST_STATE_STOPPED)
        self.assertEqual(read_link_state(link_path)[0]["ingest"]["state"], C.LINK_STOPPED)


class AckSock:
    """recvfrom from a list, sendto recorded (or raising)."""
    def __init__(self, items, stop, fail=None):
        self.items, self.stop, self.fail, self.sent = list(items), stop, fail, []

    def recvfrom(self, n):
        if not self.items:
            self.stop.set()
            raise socket.timeout()
        return self.items.pop(0)

    def sendto(self, data, peer):
        if self.fail:
            raise self.fail
        self.sent.append((data, peer))
        return len(data)


class AckTests(SimpleTestCase, TmpDir):
    def serve(self, items, clock=None, fail=None):
        stop = threading.Event()
        clock = clock or FakeClock()
        ing, status = make_ingest(None, clock)
        sock = AckSock(items, stop, fail)
        udpingest.serve(sock, ing, stop, acker=udpingest.Acker(clock=clock))
        return ing, status, sock

    def test_each_heartbeat_gets_one_small_ack_to_its_ip_and_port(self):
        ing, status, sock = self.serve([(heartbeat(7).encode(), (PEER, 50123))])
        self.assertEqual(len(sock.sent), 1)
        data, peer = sock.sent[0]
        self.assertEqual(peer, (PEER, 50123))                 # where it came from, not 5055
        self.assertLess(len(data), C.UDP_ACK_MAX_B)
        self.assertEqual(json.loads(data), {"schema": C.SCHEMA_ACK_V1, "boot_id": "b007", "seq": 7})
        self.assertEqual((ing.acks_sent, ing.ack_errors, ing.pico_heartbeats), (1, 0, 1))
        status.snapshot(ing)
        self.assertEqual(status.doc["counters"]["acks_sent"], 1)
        self.assertEqual(status.doc["counters"]["ack_errors"], 0)

    def test_events_and_bad_datagrams_get_no_ack(self):
        ing, _, sock = self.serve([(raw(seq=1).encode(), (PEER, 1)), (b"\xff", (PEER, 1)),
                                   (b"not json", (PEER, 1))])
        self.assertEqual(sock.sent, [])
        self.assertEqual(ing.acks_sent, 0)

    def test_at_most_one_ack_per_sender_per_min_s(self):
        clock = FakeClock()
        items = [(heartbeat(1).encode(), (PEER, 1)), (heartbeat(2).encode(), (PEER, 1)),
                 (heartbeat(9).encode(), ("10.42.0.81", 1))]
        ing, _, sock = self.serve(items, clock)
        self.assertEqual([json.loads(d)["seq"] for d, _ in sock.sent], [1, 9])
        self.assertEqual(ing.acks_limited, 1)
        acker = udpingest.Acker(clock=clock)
        ing2, _ = make_ingest(None, clock)
        s2 = AckSock([], threading.Event())
        for seq in (1, 2):
            ing2.handle_frame(heartbeat(seq), peer=PEER)
            acker(s2, ing2, (PEER, 1))
            clock.t += C.UDP_ACK_MIN_S
        self.assertEqual(ing2.acks_sent, 2)                   # 5 s apart in life: every one

    def test_a_failed_sendto_is_counted_and_the_loop_goes_on(self):
        ing, status, sock = self.serve([(heartbeat(1).encode(), (PEER, 1)),
                                        (raw(seq=1).encode(), (PEER, 1))],
                                       fail=OSError(101, "Network is unreachable"))
        self.assertEqual((ing.acks_sent, ing.ack_errors), (0, 1))
        self.assertEqual(ing.store.stats["added"], 1)        # the event after it still stored
        status.snapshot(ing)
        self.assertEqual(status.doc["counters"]["ack_errors"], 1)

    def test_real_socket_the_sender_reads_its_ack_on_its_own_socket(self):
        s = udpingest.open_socket("127.0.0.1", 0, 0.05)
        port = s.getsockname()[1]
        pico = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        pico.settimeout(2)
        pico.sendto(heartbeat(3).encode(), ("127.0.0.1", port))
        stop = threading.Event()
        ing, _ = make_ingest(None, FakeClock())
        orig = ing.idle
        ing.idle = lambda: (orig(), stop.set())
        udpingest.serve(s, ing, stop)
        s.close()
        data, src = pico.recvfrom(256)
        pico.close()
        self.assertEqual(src[1], port)
        self.assertEqual(json.loads(data)["seq"], 3)
