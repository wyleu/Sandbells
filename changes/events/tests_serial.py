"""manage.py ingest_serial: finding the Pico's USB data port (never the
REPL), lines -> serial_status.json, a real pty, and the sandswing status
page / Ingest page reading it (no hardware)."""

import io
import json
import logging
import os
import shutil
import tempfile
import threading
import time
from unittest import mock

from django.core.management import call_command
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from . import constants as C
from . import serialingest as S

UID = "7091CDAB9DBD5305"
_quiet = {}


def setUpModule():
    for name in (C.LOGGER_NAME, C.LOGGER_NAME + ".serial"):
        log = logging.getLogger(name)
        _quiet[name] = (log.handlers[:], log.propagate)
        log.handlers, log.propagate = [logging.NullHandler()], False


def tearDownModule():
    for name, (h, p) in _quiet.items():
        log = logging.getLogger(name)
        log.handlers, log.propagate = h, p


class TmpDir:
    def tmpdir(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        return d


def heartbeat(seq=7, period_s=10, uid=UID, **body):
    b = {"panel": [[0, 40, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [40, 0, 0]],
         "panel_state": ["ok", "off", "off", "off", "off", "unsynced"],
         "sync": "synced", "uid": uid, "chan": [["new", None], ["fault", "no beam"]],
         "link": "no_wifi", "tower": "inactive", "last_seq": 3, "uptime_s": 4000,
         "last_reset": "POWER_ON", "net": {"drops": 0}, "wifi": {"ip": None, "rssi": None},
         "time": {"srv": "10.42.0.1", "stratum": 1}, "mem_free": 51200, "gc_heap_kb": 90,
         "edges_lost": 0, "late_drains": 0, "strokes_undelivered": 0, "watchdog": True}
    b.update(body)
    return {"schema": "sand.panel/v1", "type": "heartbeat", "src": "sandswing",
            "id": "sandswing-pico", "boot_id": "b007", "seq": seq, "via": "usb_cdc",
            "body": b, "serial": {"period_s": period_s, "lines": 41, "cut": 0, "errors": 0}}


def line(**kw):
    return (json.dumps(heartbeat(**kw), separators=(",", ":")) + "\n").encode()


# ---- finding the data port ---------------------------------------------------
class FakeSys(TmpDir):
    """/sys/class/tty/ttyACMn -> device -> a USB interface dir, as on the Pi."""

    def make(self, ttys):
        root = self.tmpdir()
        cls = os.path.join(root, "class", "tty")
        os.makedirs(cls)
        for tty, (usb, num, name, product) in ttys.items():
            udir = os.path.join(root, "devices", usb)
            ifdir = os.path.join(udir, "%s:1.%d" % (usb, num))
            os.makedirs(ifdir, exist_ok=True)
            with open(os.path.join(ifdir, "bInterfaceNumber"), "w") as f:
                f.write("%02x\n" % num)
            if name is not None:
                with open(os.path.join(ifdir, "interface"), "w") as f:
                    f.write(name + "\n")
            with open(os.path.join(udir, "product"), "w") as f:
                f.write(product + "\n")
            with open(os.path.join(udir, "manufacturer"), "w") as f:
                f.write("Raspberry Pi\n")
            os.makedirs(os.path.join(cls, tty))
            os.symlink(ifdir, os.path.join(cls, tty, "device"))
        return os.path.join(cls, "ttyACM*"), os.path.join(root, "by-id", "*")


PICO = "Pico 2 W"


class FindPortTests(SimpleTestCase, FakeSys):
    def test_named_data_interface_never_the_console(self):
        g, by_id = self.make({
            "ttyACM0": ("1-1.3", 0, "CircuitPython CDC control", PICO),
            "ttyACM1": ("1-1.3", 2, "CircuitPython CDC2 control", PICO)})
        p = S.find_port(sys_glob=g, by_id_glob=by_id)
        self.assertEqual(p.device, "/dev/ttyACM1")
        self.assertIn("CDC2", p.how)

    def test_numbering_can_differ_still_the_data_one(self):
        g, by_id = self.make({
            "ttyACM0": ("1-1.2", 0, None, "Some modem"),          # not a Pico
            "ttyACM1": ("1-1.3", 0, "CircuitPython CDC control", PICO),
            "ttyACM2": ("1-1.3", 2, "CircuitPython CDC2 control", PICO)})
        self.assertEqual(S.find_port(sys_glob=g, by_id_glob=by_id).device, "/dev/ttyACM2")

    def test_no_interface_names_interface_two(self):
        g, by_id = self.make({
            "ttyACM0": ("1-1.3", 0, None, PICO),
            "ttyACM1": ("1-1.3", 2, None, PICO)})
        self.assertEqual(S.find_port(sys_glob=g, by_id_glob=by_id).device, "/dev/ttyACM1")

    def test_console_only_none(self):
        g, by_id = self.make({"ttyACM0": ("1-1.3", 0, "CircuitPython CDC control", PICO)})
        self.assertIsNone(S.find_port(sys_glob=g, by_id_glob=by_id))

    def test_other_usb_serial_ignored(self):
        g, by_id = self.make({"ttyACM0": ("1-1.2", 2, "CDC2 thing", "Arduino")})
        self.assertIsNone(S.find_port(sys_glob=g, by_id_glob=by_id))

    def test_device_override_refuses_the_repl(self):
        g, by_id = self.make({
            "ttyACM0": ("1-1.3", 0, "CircuitPython CDC control", PICO),
            "ttyACM1": ("1-1.3", 2, "CircuitPython CDC2 control", PICO)})
        with self.assertRaises(S.ConsoleRefused):
            S.find_port(device="/dev/ttyACM0", sys_glob=g, by_id_glob=by_id)

    def test_device_override_used_when_it_exists(self):
        d = self.tmpdir()
        dev = os.path.join(d, "ttyX")
        open(dev, "w").close()
        g = os.path.join(d, "none*")
        self.assertEqual(S.find_port(device=dev, sys_glob=g).device, dev)
        self.assertIsNone(S.find_port(device=dev + "-gone", sys_glob=g))

    def test_by_id_fallback_if02_only(self):
        d = self.tmpdir()
        os.makedirs(os.path.join(d, "by-id"))
        target = os.path.join(d, "ttyACM7")
        open(target, "w").close()
        base = "usb-Raspberry_Pi_Pico_2_W_E66164084F5F2A28-if0%d"
        for n in (0, 2):
            os.symlink(target if n == 2 else os.path.join(d, "ttyACM6"),
                       os.path.join(d, "by-id", base % n))
        p = S.find_port(sys_glob=os.path.join(d, "none*"), by_id_glob=os.path.join(d, "by-id", "*"))
        self.assertEqual(p.device, target)


# ---- lines ---------------------------------------------------------------------
class SplitterTests(SimpleTestCase):
    def test_whole_lines_and_a_partial_kept(self):
        sp = S.LineSplitter()
        self.assertEqual(sp.feed(b"a\nb"), [b"a"])
        self.assertEqual(sp.feed(b"c\n\n"), [b"bc", b""])

    def test_too_long_dropped_to_its_newline(self):
        sp = S.LineSplitter(max_b=10)
        self.assertEqual(sp.feed(b"x" * 11), [])
        self.assertEqual(sp.too_long, 1)
        self.assertEqual(sp.feed(b"yy\nok\n"), [b"ok"])


class StatusTests(SimpleTestCase, TmpDir):
    def test_good_bad_other_and_file(self):
        path = os.path.join(self.tmpdir(), "serial_status.json")
        st = S.SerialStatus(path)
        self.assertTrue(st.line(line().strip()))
        self.assertFalse(st.line(b'{"schema":"sand.pan'))       # cut short
        self.assertFalse(st.line(b'{"schema":"sand.event/v1","type":"stroke","body":{}}'))
        self.assertFalse(st.line(b""))                           # the fresh-line newline
        st.maybe_write(None, force=True)
        with open(path) as f:
            doc = json.load(f)
        self.assertEqual(doc["mode"], C.INGEST_MODE_SERIAL)
        self.assertEqual((doc["serial"]["good"], doc["serial"]["bad"],
                          doc["serial"]["not_heartbeat"], doc["serial"]["lines"]), (1, 1, 1, 3))
        self.assertEqual(doc["heartbeat"]["body"]["uid"], UID)
        self.assertEqual(doc["counters"]["good"], 1)
        self.assertEqual(len(doc["recent_rejects"]), 2)

    def test_latest_fresh_then_stale_by_period(self):
        path = os.path.join(self.tmpdir(), "serial_status.json")
        st = S.SerialStatus(path)
        st.line(line(period_s=10).strip())
        st.maybe_write(None, force=True)
        at = st.doc["heartbeat_ms"]
        L = S.latest(at + 1000, path)
        self.assertFalse(L["stale"])
        self.assertEqual(L["stale_ms"], 10 * 1000 * C.SERIAL_STALE_PERIODS + C.SERIAL_STALE_SLACK_MS)
        self.assertTrue(S.latest(at + L["stale_ms"] + 1, path)["stale"])
        st.stopped(None)
        self.assertTrue(S.latest(at + 1000, path)["stale"])      # ingest_serial stopped

    def test_latest_none_without_a_good_line(self):
        path = os.path.join(self.tmpdir(), "serial_status.json")
        self.assertIsNone(S.latest(path=path))
        st = S.SerialStatus(path)
        st.maybe_write(None, force=True)
        self.assertIsNone(S.latest(path=path))


# ---- LED echo -----------------------------------------------------------------
LED = {"t": "led", "n": 4, "p": [[0, 32, 0], [48, 48, 48], [0, 0, 0], [24, 12, 0], [24, 12, 0], [8, 8, 8]],
       "s": ["ws_client", "response", "no_board", "empty", "empty", "heartbeat"]}


def led_line(**kw):
    return json.dumps(dict(LED, **kw), separators=(",", ":")).encode()


def echo_hb(**kw):
    hb = heartbeat(**kw)
    hb["serial"]["leds"] = {"lines": 3, "dropped": 0, "min_s": 0.25}
    return (json.dumps(hb, separators=(",", ":"))).encode()


class LedEchoTests(SimpleTestCase, TmpDir):
    def setUp(self):
        d = self.tmpdir()
        self.path, self.lpath = os.path.join(d, "serial_status.json"), os.path.join(d, "leds.json")
        self.st = S.SerialStatus(self.path, leds_path=self.lpath)
        self.st.serial["port"] = "serial:/dev/ttyACM1"
        self.st.serial["connected"] = True

    def now(self):
        return int(time.time() * C.MS_PER_S)

    def test_led_line_written_and_live_after_an_echo_heartbeat(self):
        self.assertTrue(self.st.line(echo_hb()))
        self.assertFalse(S.leds(path=self.lpath)["live"])         # echo on, no line yet
        self.assertFalse(self.st.line(led_line()))                # not a heartbeat ...
        L = S.leds(path=self.lpath)
        self.assertTrue(L["live"], L)
        self.assertEqual((L["panel"], L["panel_state"], L["n"]), (LED["p"], LED["s"], 4))
        self.assertEqual(self.st.doc["heartbeat"]["seq"], 7)      # ... and leaves the heartbeat alone
        self.assertEqual((self.st.serial["led_lines"], self.st.serial["not_heartbeat"],
                          self.st.serial["good"]), (1, 0, 1))
        self.st.line(led_line(n=5, p=[[0, 0, 24]] * 6))
        self.assertEqual(S.leds(path=self.lpath)["panel"][0], [0, 0, 24])

    def test_recent_lines_kept_trimmed_and_cleared(self):
        self.st.line(echo_hb())
        for n in range(1, C.SERIAL_LEDS_RECENT + 3):
            self.st.line(led_line(n=n, p=[[0, 0, n]] * 6))
        L = S.leds(path=self.lpath)
        self.assertEqual([r["n"] for r in L["recent"]],
                         list(range(3, C.SERIAL_LEDS_RECENT + 3)))     # oldest first, newest = n
        self.assertEqual(L["recent"][-1]["p"], L["panel"])
        self.assertEqual(L["recent"][-1]["s"], LED["s"])
        self.st.disconnected("EOF")
        self.assertEqual(self.st.leds.doc["recent"], [])
        self.assertEqual(S.leds(path=self.lpath)["recent"], [])

    def test_not_live_stale_off_or_disconnected(self):
        self.st.line(echo_hb(period_s=10))
        self.st.line(led_line())
        hb_ms = self.st.leds.doc["hb_ms"]
        stale = 10 * C.MS_PER_S * C.SERIAL_STALE_PERIODS + C.SERIAL_STALE_SLACK_MS
        self.assertTrue(S.leds(hb_ms + stale, self.lpath)["live"])
        L = S.leds(hb_ms + stale + 1, self.lpath)
        self.assertFalse(L["live"])
        self.assertIsNone(L["panel"])
        self.st.line(line())                                      # a heartbeat with the echo off
        self.assertFalse(S.leds(path=self.lpath)["live"])
        self.st.line(echo_hb())
        self.st.line(led_line())
        self.assertTrue(S.leds(path=self.lpath)["live"])
        self.st.disconnected("EOF")
        self.assertFalse(S.leds(path=self.lpath)["live"])
        self.assertFalse(S.leds(path=os.path.join(self.tmpdir(), "none.json"))["live"])

    def test_malformed_led_lines_are_rejected(self):
        self.st.line(echo_hb())
        for bad in (led_line(p=[[0, 0, 0]] * 5), led_line(p="x"), led_line(s=None),
                    led_line(p=[[0, 0, "x"]] * 6), led_line(t="LED")):
            self.assertFalse(self.st.line(bad))
        self.assertEqual((self.st.serial["led_lines"], self.st.serial["not_heartbeat"]), (0, 5))
        self.assertFalse(S.leds(path=self.lpath)["live"])

    def test_no_leds_path_writes_nothing(self):
        st = S.SerialStatus(self.path)
        st.line(echo_hb())
        st.line(led_line())
        self.assertEqual(st.serial["led_lines"], 1)
        self.assertEqual(st.leds.writes, 0)

    def test_api_leds_and_link_leds_live(self):
        self.st.line(echo_hb())
        self.st.line(led_line())
        self.st.maybe_write(None, force=True)
        d = self.tmpdir()
        with mock.patch.dict(os.environ, {C.SERIAL_LEDS_ENV: self.lpath,
                                          C.SERIAL_STATUS_ENV: self.path,
                                          C.LINK_STATE_ENV: os.path.join(d, "link.json"),
                                          C.MIDI_STATUS_ENV: os.path.join(d, "midi.json")}):
            r = self.client.get(reverse("events:api_leds")).json()
            self.assertTrue(r["live"])
            self.assertEqual(r["panel"], LED["p"])
            self.assertEqual(set(r), {"live", "panel", "panel_state", "n", "recent",
                                      "led_age_ms", "hb_age_ms"})
            self.assertTrue(self.client.get(reverse("events:api_link")).json()["leds_live"])
        with mock.patch.dict(os.environ, {C.SERIAL_LEDS_ENV: os.path.join(d, "none.json")}):
            r = self.client.get(reverse("events:api_leds")).json()
            self.assertEqual((r["live"], r["panel"]), (False, None))

    def test_poll_no_slower_than_the_picos_hold(self):
        self.assertLessEqual(C.LINK_LED_POLL_MS, C.SERIAL_LED_MIN_S * C.MS_PER_S)


# ---- the loop: a file, then a real pty ---------------------------------------------
class RunTests(TestCase, TmpDir):
    def test_command_once_on_a_file(self):
        d = self.tmpdir()
        dev, path = os.path.join(d, "ttyFake"), os.path.join(d, "serial_status.json")
        with open(dev, "wb") as f:
            f.write(b'tail of a line cut at connect}\n' + line(seq=1) + line(seq=2))
        with mock.patch.dict(os.environ, {C.SERIAL_STATUS_ENV: path}), \
                mock.patch("events.management.commands.ingest_serial.setup_logging",
                           return_value=logging.getLogger(C.LOGGER_NAME)):
            call_command("ingest_serial", device=dev, once=True)
        with open(path) as f:
            doc = json.load(f)
        self.assertEqual(doc["state"], C.INGEST_STATE_STOPPED)
        self.assertEqual((doc["serial"]["good"], doc["serial"]["bad"]), (2, 1))
        self.assertEqual(doc["heartbeat"]["seq"], 2)
        self.assertEqual(doc["serial"]["port"], "serial:" + dev)
        self.assertEqual(doc["serial"]["disconnects"], 1)          # EOF = unplugged

    def test_refuses_the_console_and_stops(self):
        st = S.SerialStatus(None)

        def find():
            raise S.ConsoleRefused("/dev/ttyACM0 is the Pico's REPL console")
        opened = []
        S.run(threading.Event(), st, find=find, opener=opened.append, once=True)
        self.assertEqual(opened, [])
        self.assertEqual(st.serial["errors"], 1)

    def test_real_pty_raw_no_echo_and_unplug(self):
        import pty
        import select
        master, slave = pty.openpty()
        name = os.ttyname(slave)
        st = S.SerialStatus(None)
        stop = threading.Event()
        opens = []

        def opener(port):
            src = S.SerialSource(port.device)
            opens.append(src)
            return src
        t = threading.Thread(target=S.run, args=(stop, st),
                             kwargs=dict(find=lambda: S.Port(name, "test"), opener=opener,
                                         reconnect_s=0.05, idle_s=0.05))
        t.start()
        try:
            _wait(lambda: opens)
            self.assertTrue(opens[0].raw)                      # termios raw on a real tty
            os.write(master, line(seq=5))
            _wait(lambda: st.serial["good"] == 1)
            self.assertEqual(st.doc["heartbeat"]["seq"], 5)
            # raw: nothing was echoed back towards the Pico
            self.assertEqual(select.select([master], [], [], 0.1)[0], [])
            os.close(slave)
            os.close(master)                                   # the "unplug": EIO
            _wait(lambda: st.serial["disconnects"] >= 1)
            self.assertFalse(st.serial["connected"] and st.serial["disconnects"] == 0)
        finally:
            stop.set()
            t.join(5)
        self.assertFalse(t.is_alive())


def _wait(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    raise AssertionError("timed out")


# ---- the pages ------------------------------------------------------------------
class FarmSerialStatusTests(SimpleTestCase, TmpDir):
    HOME = "http://192.168.0.81/status"

    def setUp(self):
        self.path = os.path.join(self.tmpdir(), "serial_status.json")
        env = mock.patch.dict(os.environ, {C.SERIAL_STATUS_ENV: self.path})
        env.start()
        self.addCleanup(env.stop)

    def write(self, age_s=0, **kw):
        st = S.SerialStatus(self.path)
        st.line(line(**kw).strip())
        st.doc["heartbeat_ms"] -= int(age_s * C.MS_PER_S)
        st.serial["port"] = "serial:/dev/ttyACM1"
        st.maybe_write(None, force=True)

    def fetch(self, entry=None, wifi=b'{"schema": "sand.status/v1", "name": "wifi"}'):
        from bells import views
        calls = []

        def fake_open(url, timeout=0):
            calls.append(url)
            if wifi is None:
                raise OSError("timed out")
            return io.BytesIO(wifi)
        entry = entry or {"id": "sandswing", "name": "sandswing", "family": "sandswing",
                          "status_url": self.HOME}
        views._LAST_GOOD.clear()
        with mock.patch.object(views, "load_farm_instances", return_value=[entry]), \
                mock.patch.object(views, "urlopen", side_effect=fake_open):
            r = views.farm_device_status(RequestFactory().get("/", {"url": self.HOME}))
        return r, json.loads(r.content), calls

    def test_fresh_serial_is_used_wifi_not_asked(self):
        self.write(age_s=2)
        r, doc, calls = self.fetch()
        self.assertEqual((r.status_code, calls), (200, []))
        self.assertEqual((doc["schema"], doc["via"], doc["stale"]), ("sand.status/v1", "usb serial", False))
        ids = [s["id"] for s in doc["sections"]]
        self.assertEqual(ids[0], "serial")
        for sid in ("panel", "time", "heads", "tower", "network", "concentrator"):
            self.assertIn(sid, ids)
        src = {i["key"]: i for i in doc["sections"][0]["items"]}
        self.assertIn("/dev/ttyACM1", src["source"]["value"])
        self.assertEqual(src["age"]["value"], "2 s ago")
        heads = {i["key"]: i for s in doc["sections"] if s["id"] == "heads" for i in s["items"]}
        self.assertEqual(heads["ch2"]["level"], "error")
        self.assertIn("no beam", heads["ch2"]["value"])
        panel = [s for s in doc["sections"] if s["id"] == "panel"][0]["items"]
        self.assertEqual(panel[0]["color"], "rgb(0,255,0)")      # scaled like link_widget.js
        self.assertEqual(panel[1]["color"], C.PANEL_CSS_DARK)     # off
        self.assertIn("USB serial, 2 s ago", doc["summary"])

    def test_stale_serial_wifi_first_then_serial_marked_stale(self):
        self.write(age_s=600)
        r, doc, calls = self.fetch()
        self.assertEqual((calls, doc["name"]), ([self.HOME], "wifi"))      # Wi-Fi answered
        r, doc, calls = self.fetch(wifi=None)
        self.assertEqual(r.status_code, 200)
        self.assertEqual((doc["via"], doc["stale"], doc["level"]), ("usb serial", True, "warn"))
        self.assertIn("STALE", doc["summary"])

    def test_no_serial_no_wifi_still_504(self):
        r, doc, calls = self.fetch(wifi=None)
        self.assertEqual(r.status_code, 504)

    def test_other_pico_uid_or_family_not_used(self):
        self.write(age_s=1)
        _, doc, calls = self.fetch(entry={"id": "s", "family": "sandswing", "uid": "0F8A68C934D3A61C",
                                          "status_url": self.HOME})
        self.assertEqual((calls, doc.get("via")), ([self.HOME], None))
        _, doc, calls = self.fetch(entry={"id": "s", "family": "sandswing", "uid": UID.lower(),
                                          "status_url": self.HOME})
        self.assertEqual((calls, doc["via"]), ([], "usb serial"))
        _, doc, calls = self.fetch(entry={"id": "m", "family": "sandmon", "status_url": self.HOME})
        self.assertEqual(calls, [self.HOME])


class IngestPageSerialTests(TestCase, TmpDir):
    def setUp(self):
        d = self.tmpdir()
        self.path = os.path.join(d, "serial_status.json")
        env = mock.patch.dict(os.environ, {C.SERIAL_STATUS_ENV: self.path,
                                           C.INGEST_STATUS_ENV: os.path.join(d, "status.json"),
                                           C.MIDI_STATUS_ENV: os.path.join(d, "midi_status.json")})
        env.start()
        self.addCleanup(env.stop)
        run = mock.patch("events.ingestpage.subprocess.run", side_effect=FileNotFoundError)
        run.start()
        self.addCleanup(run.stop)

    def test_serial_section(self):
        r = self.client.get(reverse("events:ingest"))
        self.assertContains(r, "No serial status file")
        st = S.SerialStatus(self.path)
        st.connected(type("Src", (), {"label": "serial:/dev/ttyACM1"})(), "interface 2 'CircuitPython CDC2 control'")
        st.line(line().strip())
        st.line(b"{cut")
        st.maybe_write(None, force=True)
        r = self.client.get(reverse("events:ingest"))
        self.assertFalse(r.context["serial_hb_stale"])
        for text in ("USB serial status (ingest_serial)", "serial:/dev/ttyACM1", ">yes<",
                     "sandbells-ingest-serial.service"):
            self.assertContains(r, text)


class PanelColourTests(SimpleTestCase):
    """The farm page's Panel LEDs (status_schema.panel_css) and the Strokes
    page's strip (link_widget.js cssColour) colour an LED the same way."""
    SAMPLES = [[0, 32, 0], [0, 0, 24], [24, 0, 48], [24, 12, 0], [24, 48, 0], [40, 20, 0],
               [0, 0, 0], [1, 1, 1], [48, 47, 1], [7, 3, 0]]

    def test_python_rule(self):
        from bells.status_schema import panel_css
        self.assertEqual(panel_css([0, 32, 0]), "rgb(0,%d,0)" % C.PANEL_CSS_FULL)
        self.assertEqual(panel_css([24, 12, 0]), "rgb(255,128,0)")    # 127.5 rounds up
        self.assertEqual(panel_css([0, 0, 0]), C.PANEL_CSS_DARK)
        for bad in (None, [], ["x", 1, 2], 5):
            self.assertEqual(panel_css(bad), C.PANEL_CSS_DARK)

    def test_same_as_link_widget_js(self):
        import shutil
        import subprocess
        from pathlib import Path
        from unittest import SkipTest
        from bells.status_schema import panel_css
        node = shutil.which("node")
        if not node:
            raise SkipTest("node not installed")
        js = Path(__file__).resolve().parent / "templates" / "events" / "link_widget.js"
        script = ("const lw = require(%s); console.log(JSON.stringify(%s.map(lw.cssColour)));"
                  % (json.dumps(str(js)), json.dumps(self.SAMPLES)))
        p = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout), [panel_css(c) for c in self.SAMPLES])
