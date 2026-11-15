"""The sandheads page over USB (no Wi-Fi): page commands -> ingest_serial's
socket (serialheads), the Pico's MIDI CC readings -> align docs (headscc,
midiparse, ingest_midi's pairer), the PT level log (headlog) and the views."""

import json
import os
import shutil
import tempfile
import time
from unittest import mock

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from . import constants as C
from . import headlog, headscc, midiingest, serialheads
from .midiparse import CcMessage, MidiParser, parse_seq_line

# bytes from sandswing heads_cc.CcOut (src/heads_cc.py at the same commit):
# frame(1, CLEAR|QUIET|SCOPE, thr 32768, rb 23500, drv 65535, 4.9 mA, 1.18 V, 0.05 V)
FULL = bytes.fromhex("bf6601bf6719bf143fbf347fbf152dbf3572bf167fbf367e"
                     "bf1703bf376abf1809bf381cbf1900bf3932bf6a01")
# frame(1, BUSY, ..., 1.31 V, span None, full=False): strokes in progress
RINGING = bytes.fromhex("bf6601bf6704bf180abf381ebf197fbf397fbf6a02")
# ack(1, "thr_mid", ok, 32768, 65535, QUIET)
ACK_MID = bytes.fromhex("bf6601bf6708bf6805bf6900bf143fbf347fbf167fbf367ebf6a01")
# ack(2, "thr", "tower not quiet: ...", 30000, 60000, 0)
ACK_NO = bytes.fromhex("bf6602bf6700bf6801bf6902bf143abf344bbf1675bf3616bf6a02")


def decode(*chunks, t0=1000, step=500):
    docs = []
    d = headscc.HeadsCcDecoder(docs.append)
    p = MidiParser()
    for i, b in enumerate(chunks):
        for m in p.feed(b):
            d.cc(m, t0 + i * step)
    return d, docs


class CcParse(SimpleTestCase):
    def test_raw_and_aseqdump(self):
        msgs = MidiParser().feed(bytes([0xBF, 102, 1, 103, 9, 0x9F, 60, 100]))
        self.assertEqual(msgs[0], CcMessage(C.MIDI_CC, 16, 102, 1))
        self.assertEqual(msgs[1], CcMessage(C.MIDI_CC, 16, 103, 9))      # running status
        self.assertEqual((msgs[2].kind, msgs[2].note), ("on", 60))
        self.assertEqual(parse_seq_line(" 28:0   Control change         15, controller 106, value 3"),
                         CcMessage(C.MIDI_CC, 16, 106, 3))

    def test_pairer_never_makes_a_stroke_of_a_cc(self):
        got, seen = [], []

        class Ing:
            def add(self, *a, **k):
                got.append(a)

        status = mock.Mock()
        pairer = midiingest.StampPairer(Ing(), midiingest.StrokeMaker(), status)
        pairer.cc_sink = lambda m, ms: seen.append(m)
        self.assertEqual(pairer.handle(MidiParser().feed(FULL), 5000, 10), 0)
        self.assertEqual(len(seen), 15)
        self.assertEqual(pairer.ccs, 15)
        self.assertEqual(got, [])
        self.assertEqual(pairer.pending, {})
        pairer.cc_sink = lambda m, ms: 1 / 0                              # a broken sink: not fatal
        with self.assertLogs(C.LOGGER_NAME, "WARNING") as cm:
            pairer.handle(MidiParser().feed(FULL), 5000, 10)
        self.assertEqual((pairer.cc_errors, len(cm.output)), (15, 1))     # logged once, counted


class Decoder(SimpleTestCase):
    def test_full_report(self):
        d, docs = decode(FULL)
        self.assertEqual(len(docs), 1)
        m = docs[0]
        self.assertEqual((m["schema"], m["type"]), (C.SERIAL_HB_SCHEMA, "align"))
        b = m["body"]
        self.assertEqual((b["ch"], b["thr"], b["drv"], b["ma"], b["pt"], b["pt_span"]),
                         (1, 32768, 65535, 4.9, 1.18, 0.05))
        self.assertLessEqual(abs(b["rb"] - 23500), 4)                     # 4-count steps
        self.assertEqual((b["tower"], b["busy"], b["n"], b["bits"]), ("inactive", False, 1, "80"))

    def test_ringing_report_keeps_the_last_readings_marked_busy(self):
        d, docs = decode(FULL, RINGING)
        b = docs[1]["body"]
        self.assertEqual((b["thr"], b["ma"], b["pt"], b["pt_span"]), (32768, 4.9, 1.31, None))
        self.assertEqual((b["tower"], b["busy"]), ("active", True))
        self.assertEqual((b["n"], b["dt"], b["bits"]), (2, 500.0, "80"))  # second sample low

    def test_trace_window(self):
        d, docs = decode(*([FULL] * 10), step=500)
        self.assertEqual(docs[-1]["body"]["n"], C.HEADS_TRACE_MS // 500 + 1)

    def test_acks(self):
        d, docs = decode(ACK_MID, ACK_NO)
        a, r = docs[0]["body"], docs[1]["body"]
        self.assertEqual(docs[0]["type"], "align_ack")
        self.assertEqual((a["what"], a["ok"], a["why"], a["thr"], a["ch"]), ("thr_mid", True, None, 32768, 1))
        self.assertEqual((r["what"], r["ok"], r["ch"]), ("thr", False, 2))
        self.assertTrue(r["why"].startswith("tower not quiet"))

    def test_cut_reports_other_channels_and_strays(self):
        d, docs = decode(FULL[:12], FULL, bytes([0xB0, 102, 1, 0xB0, 106, 1]), bytes([0xBF, 106, 9]))
        self.assertEqual(len(docs), 1)
        self.assertEqual((d.partial, d.reports), (1, 1))
        self.assertEqual(d.ignored, 3)


class Commands(SimpleTestCase):
    def test_check(self):
        ok = serialheads.check_command
        self.assertEqual(ok({"cmd": "align", "ch": 1, "thr_mid": True}), b'{"cmd":"align","ch":1,"thr_mid":true}')
        self.assertEqual(ok({"cmd": "align", "ch": 2, "thr": -1}), b'{"cmd":"align","ch":2,"thr":-1}')
        self.assertEqual(ok({"cmd": "align", "info": True}), b'{"cmd":"align","info":true}')
        self.assertEqual(ok({"cmd": "align", "ch": 3, "scope": False}), b'{"cmd":"align","ch":3,"scope":false}')
        for bad in ({"cmd": "tune", "ch": 1, "thr": 1}, {"cmd": "align", "ch": 0, "thr": 1},
                    {"cmd": "align", "ch": 17, "thr": 1}, {"cmd": "align", "ch": 1, "thr": 5},
                    {"cmd": "align", "ch": 1, "thr": True}, {"cmd": "align", "ch": 1},
                    {"cmd": "align", "ch": 1, "thr_mid": 1}, {"cmd": "align", "ch": 1, "pin": 3},
                    {"cmd": "align", "ch": 1, "scope": "yes"}, [1]):
            with self.assertRaises(ValueError, msg=bad):
                ok(bad)

    def test_socket_round_trip(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        path = os.path.join(tmp, "cmd.sock")
        inbox = serialheads.CommandInbox(path).open()
        self.addCleanup(inbox.close)
        self.assertEqual(os.stat(path).st_mode & 0o777, C.SERIAL_CMD_SOCK_MODE)
        serialheads.send_command(b'{"cmd":"align","ch":1,"thr_mid":true}', path)
        serialheads.send_command(b'{"cmd":"rm"}', path)                    # re-checked: refused
        serialheads.send_command(b"x" * (C.SERIAL_CMD_MAX_B + 1), path)
        self.assertEqual(inbox.take(), [b'{"cmd":"align","ch":1,"thr_mid":true}\n'])
        self.assertEqual((inbox.received, inbox.refused), (3, 2))
        inbox.close()
        self.assertFalse(os.path.exists(path))
        with self.assertRaises(OSError):
            serialheads.send_command(b"{}", path)

    def test_heads_file(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        path = os.path.join(tmp, "h.json")
        self.assertFalse(serialheads.heads(0, path=path)["running"])
        f = serialheads.HeadsFile(path)
        f.connected(True)
        for i in range(C.SERIAL_HEADS_KEEP + 3):
            f.line({"i": i})
        h = serialheads.heads(C.SERIAL_HEADS_KEEP + 1, path=path)
        self.assertEqual((h["running"], h["connected"], h["n"]), (True, True, C.SERIAL_HEADS_KEEP + 3))
        self.assertEqual([x["i"] for x in h["items"]], [C.SERIAL_HEADS_KEEP + 1, C.SERIAL_HEADS_KEEP + 2])
        f.connected(False)
        self.assertEqual(serialheads.heads(0, path=path)["items"], [])


HB = {"schema": C.SERIAL_HB_SCHEMA, "type": C.SERIAL_HB_TYPE,
      "body": {"uid": "7091CDAB9DBD5305", "tower": "inactive", "pt": [5, 1.234, 0.02],
               "thr": {"target": [None, None, None, None, 32768], "readback": [None, None, None, None, 32700]},
               "chan": [["head_old"], ["empty"], ["empty"], ["empty"], ["head_new"]]}}


class PtLog(TestCase):
    def test_reading(self):
        self.assertEqual(headlog.reading(HB), {"uid": "7091CDAB9DBD5305", "ch": 5, "pt_v": 1.234,
                                               "pt_span": 0.02, "thr": 32768, "thr_rb": 32700,
                                               "tower": "inactive"})
        for bad in ({}, {"body": {}}, {"body": {"pt": None}}, {"body": {"pt": [99, 1.0, 0]}},
                    {"body": {"pt": ["x", 1.0]}}):
            self.assertIsNone(headlog.reading(bad))

    def test_rate_and_csv(self):
        now = [0.0]
        lg = headlog.PtLogger(every_s=300, clock=lambda: now[0])
        self.assertTrue(lg.heartbeat(HB))
        now[0] = 299
        self.assertFalse(lg.heartbeat(HB))
        now[0] = 301
        self.assertTrue(lg.heartbeat(HB))
        r = self.client.get(reverse("farm_heads_pt_log") + "?days=999")
        self.assertEqual(r.status_code, 200)
        lines = r.content.decode().strip().splitlines()
        self.assertEqual(lines[0], ",".join(headlog.CSV_FIELDS))
        self.assertEqual(len(lines), 3)
        self.assertIn(",5,1.234,0.02,32768,32700,inactive", lines[1])
        self.assertEqual(self.client.get(reverse("farm_heads_pt_log") + "?days=x").status_code, 400)

    def test_failed_save_never_raises(self):
        lg = headlog.PtLogger(save=lambda r: 1 / 0)
        self.assertFalse(lg.heartbeat(HB))
        self.assertEqual(lg.failed, 1)


class Views(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.sock = os.path.join(self.tmp, "cmd.sock")
        env = {C.SERIAL_CMD_SOCK_ENV: self.sock, C.SERIAL_HEADS_ENV: os.path.join(self.tmp, "s.json"),
               C.MIDI_HEADS_ENV: os.path.join(self.tmp, "m.json")}
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)

    def post(self, doc):
        return self.client.post(reverse("farm_heads_serial_cmd"), json.dumps(doc),
                                content_type="application/json")

    def test_cmd(self):
        self.assertEqual(self.post({"cmd": "align", "ch": 1, "thr_mid": True}).status_code, 503)
        inbox = serialheads.CommandInbox(self.sock).open()
        self.addCleanup(inbox.close)
        r = self.post({"cmd": "align", "ch": 1, "thr_mid": True})
        self.assertEqual((r.status_code, r.json()), (200, {"ok": True}))
        self.assertEqual(inbox.take(), [b'{"cmd":"align","ch":1,"thr_mid":true}\n'])
        self.assertEqual(self.post({"cmd": "align", "ch": 1, "laser": 1}).status_code, 400)
        self.assertEqual(self.client.get(reverse("farm_heads_serial_cmd")).status_code, 405)

    def test_poll_merges_midi_and_serial(self):
        r = self.client.get(reverse("farm_heads_serial"))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["running"])
        f = serialheads.HeadsFile(os.environ[C.SERIAL_HEADS_ENV])
        f.connected(True)
        m = serialheads.HeadsFile(os.environ[C.MIDI_HEADS_ENV])
        m.connected(True)
        d = headscc.HeadsCcDecoder(m.line)
        for msg in MidiParser().feed(FULL + ACK_MID):
            d.cc(msg, 1000)
        j = self.client.get(reverse("farm_heads_serial") + "?midi_after=1").json()
        self.assertTrue(j["running"] and j["connected"])
        self.assertEqual([x["type"] for x in j["midi"]["items"]], ["align_ack"])
        self.assertEqual(j["midi"]["n"], 2)
        self.assertEqual(self.client.get(reverse("farm_heads_serial") + "?midi_after=z").status_code, 400)


class SerialSide(SimpleTestCase):
    """ingest_serial: the port's other lines, the command relay, the reopen watchdog."""

    def status(self, **kw):
        from . import serialingest as S
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        self.heads_path = os.path.join(tmp, "h.json")
        return S, S.SerialStatus(os.path.join(tmp, "s.json"), heads_path=self.heads_path, **kw)

    def test_line_routing(self):
        seen = []
        S, st = self.status(on_heartbeat=lambda d, ms: seen.append(d["body"]["pt"]))
        frame = {"schema": C.SERIAL_HB_SCHEMA, "type": "align", "body": {"ch": 1}}
        self.assertFalse(st.line(json.dumps(frame).encode()))
        self.assertEqual(st.serial["heads_lines"], 1)
        with self.assertLogs(C.LOGGER_NAME, "WARNING"):
            self.assertFalse(st.line(b'{"t":"serr","n":1,"e":"MemoryError()"}'))
        self.assertEqual((st.serial["pico_errors"], st.serial["pico_last_error"]), (1, "MemoryError()"))
        self.assertTrue(st.line(json.dumps(HB).encode()))
        self.assertEqual(seen, [[5, 1.234, 0.02]])
        st.on_heartbeat = lambda d, ms: 1 / 0                     # a broken log: still a good line
        self.assertTrue(st.line(json.dumps(HB).encode()))
        self.assertEqual(st.serial["errors"], 1)
        self.assertEqual(serialheads.heads(0, path=self.heads_path)["items"], [frame])

    def test_outbox_bounded_and_partial_writes(self):
        S, _ = self.status()
        ob = S.Outbox(max_b=10)
        self.assertEqual(ob.add([b"12345\n", b"abcd\n", b"x\n"]), (2, 1))

        class Src:
            out = b""

            def write(self, d):
                n = min(3, len(d))
                self.out += d[:n]
                return n
        src = Src()
        ob.flush(src)
        self.assertEqual((src.out, bytes(ob.buf)), (b"12345\nx\n", b""))   # whole lines only

    def test_serve_relays_commands_and_reopens_without_heartbeats(self):
        import threading
        S, st = self.status()
        tmp = os.path.dirname(self.heads_path)
        inbox = serialheads.CommandInbox(os.path.join(tmp, "c.sock")).open()
        self.addCleanup(inbox.close)
        serialheads.send_command(b'{"cmd":"align","ch":5,"thr_mid":true}', inbox.path)

        class Src:
            device = tmp
            label = "fake"
            written = b""

            def read(self):
                return b""

            def write(self, d):
                self.written += d
                return len(d)
        src = Src()
        st.serial["connected"] = True
        now = [0.0]

        def selector(r, w, x, t):
            now[0] += 1.0
            return [i for i in r if i is inbox and now[0] < 2], [], []
        with self.assertRaises(S.Disconnected) as cm:
            S.serve(src, threading.Event(), st, S.LineSplitter(), selector=selector,
                    inbox=inbox, clock=lambda: now[0], check_s=1e9)
        self.assertEqual(src.written, b'{"cmd":"align","ch":5,"thr_mid":true}\n')
        self.assertIn("reopening", str(cm.exception))
        self.assertEqual(st.serial["reopens"], 1)
        self.assertEqual(S._reopen_after_ms(st), 2 * st.stale_ms())   # doubles while it does not help


class Page(TestCase):
    def test_pick_via(self):
        from bells import align
        inst = {"ws_url": "ws://x/ws"}
        self.assertEqual(align.pick_via(inst, True), align.VIA_SERIAL)
        self.assertEqual(align.pick_via(inst, False), align.VIA_WS)
        self.assertEqual(align.pick_via({}, False), align.VIA_SERIAL)
        self.assertEqual(align.pick_via(inst, True, "ws"), align.VIA_WS)
        self.assertEqual(align.pick_via(inst, False, "nonsense"), align.VIA_WS)

    def test_page_sets_the_csrf_cookie(self):
        r = self.client.get(reverse("farm_heads") + "?via=serial")
        self.assertEqual(r.status_code, 200)
        self.assertIn("csrftoken", r.cookies)
