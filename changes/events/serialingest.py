"""serialingest.py -- the Pico's status over its USB data port -> one tmpfs
file, with no Wi-Fi.  Run by manage.py ingest_serial.  No Django import here.

sandswing serial_status.py writes its slim heartbeat (sand.panel/v1, type
"heartbeat", "via": "usb_cdc", plus a "serial" block of its own counters)
as one JSON line every serial_status.period_s (10 s) on usb_cdc.data.  This
reads those lines and keeps the newest good one in SERIAL_STATUS_PATH
(serial_status.json, next to ingest_udp's status.json and ingest_midi's
midi_status.json; same IngestStatus file, written atomically).  Nothing is
stored in the DB and the link state (link.json) is not touched: the
sandswing status page and the Ingest page read the file.

Finding the data port (find_port): usb_cdc.data is the Pico's second CDC
interface.  /sys/class/tty/ttyACM*: the one whose USB product or
manufacturer contains one of SERIAL_PRODUCT_MATCH and whose interface name
contains SERIAL_DATA_IF_NAME ("CircuitPython CDC2 control"); if the name is
not given, bInterfaceNumber SERIAL_DATA_IF_NUM; else /dev/serial/by-id/
...-if02.  The REPL console (bInterfaceNumber 0, normally /dev/ttyACM0) is
never picked, not even by --device.  MIDI (/dev/snd) is not touched.
--device / SANDBELLS_SERIAL_DEVICE names a tty outright.

Reading: os.open + termios raw (no pyserial), select, os.read.  Unplugged
(EIO, EOF, the node gone): close, look again every SERIAL_RECONNECT_S.

LED echo: sandswing also sends {"t":"led","n","p","s"} on each panel change
(serial_status.leds, at most 4 a second).  The newest goes to a second,
small file, SERIAL_LEDS_PATH (LedsFile; also rewritten on each heartbeat and
on a disconnect, so its reader can tell whether the echo is live: leds()).
"""

import errno
import glob
import json
import logging
import os
import select
import time
from collections import deque, namedtuple

from . import constants as C
from .ingeststatus import IngestStatus, read_ingest_status, write_json_atomic

log = logging.getLogger(C.LOGGER_NAME + ".serial")   # under setup_logging()'s handler

# device: /dev/ttyACMn; how: what picked it (for the log / status)
Port = namedtuple("Port", "device how")


class Disconnected(Exception):
    """The port went away (unplugged, EOF)."""


class ConsoleRefused(Exception):
    """The tty asked for is the Pico's REPL console."""


# ---- finding the data port ---------------------------------------------------
def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except (OSError, UnicodeDecodeError):
        return ""


def tty_info(tty_dir):
    """/sys/class/tty/ttyACMn -> {tty, device, if_num, if_name, product}
    (if_num None when sysfs does not say)."""
    ifdir = os.path.realpath(os.path.join(tty_dir, "device"))
    usb = os.path.dirname(ifdir)
    num = _read(os.path.join(ifdir, "bInterfaceNumber"))
    try:
        num = int(num, 16)
    except ValueError:
        num = None
    name = os.path.basename(tty_dir)
    return {"tty": name, "device": os.path.join(C.SERIAL_DEV_DIR, name), "if_num": num,
            "if_name": _read(os.path.join(ifdir, "interface")),
            "product": " ".join(x for x in (_read(os.path.join(usb, "manufacturer")),
                                            _read(os.path.join(usb, "product"))) if x)}


def _is_pico(info, match):
    text = info["product"] + " " + info["if_name"]
    return any(m in text for m in match)


def _is_console(info):
    return info["if_num"] == C.SERIAL_CONSOLE_IF_NUM


def find_port(match=C.SERIAL_PRODUCT_MATCH, device=None, sys_glob=C.SERIAL_SYS_TTY_GLOB,
              by_id_glob=C.SERIAL_BY_ID_GLOB):
    """-> Port or None.  ConsoleRefused if device is the Pico's REPL."""
    infos = [tty_info(t) for t in sorted(glob.glob(sys_glob))]
    if device:
        real = os.path.realpath(device)
        for info in infos:
            if os.path.realpath(info["device"]) == real and _is_console(info) \
                    and _is_pico(info, match):
                raise ConsoleRefused("%s is the Pico's REPL console (interface %d), "
                                     "not its data port" % (device, info["if_num"]))
        return Port(device, "--device") if os.path.exists(device) else None
    named = numbered = other = None
    for info in infos:
        if not _is_pico(info, match) or _is_console(info) or info["if_num"] is None:
            continue
        if C.SERIAL_DATA_IF_NAME in info["if_name"]:
            named = named or info
        elif info["if_num"] == C.SERIAL_DATA_IF_NUM:
            numbered = numbered or info
        else:
            other = other or info               # the Pico's only other CDC
    pick = named or numbered or other
    if pick is not None:
        return Port(pick["device"], "interface %s %r" % (pick["if_num"], pick["if_name"]))
    tokens = [m.replace(" ", "_") for m in match]
    for link in sorted(glob.glob(by_id_glob)):
        base = os.path.basename(link)
        if base.endswith(C.SERIAL_BY_ID_DATA_SUFFIX) and any(t in base for t in tokens):
            return Port(os.path.realpath(link), "by-id " + base)
    return None


# ---- reading it ----------------------------------------------------------------
def _raw(fd):
    """termios raw: no echo back to the Pico, no line editing, 8 bits.
    Not a tty (tests: a file / pipe): left as it is."""
    try:
        import termios
        a = termios.tcgetattr(fd)
    except Exception:                          # ImportError, termios.error, OSError
        return False
    iflag, oflag, cflag, lflag = a[0], a[1], a[2], a[3]
    iflag &= ~(termios.IGNBRK | termios.BRKINT | termios.PARMRK | termios.ISTRIP
               | termios.INLCR | termios.IGNCR | termios.ICRNL | termios.IXON)
    oflag &= ~termios.OPOST
    lflag &= ~(termios.ECHO | termios.ECHONL | termios.ICANON | termios.ISIG | termios.IEXTEN)
    cflag &= ~(termios.CSIZE | termios.PARENB)
    cflag |= termios.CS8 | termios.CREAD | termios.CLOCAL
    a[0], a[1], a[2], a[3] = iflag, oflag, cflag, lflag
    try:
        termios.tcsetattr(fd, termios.TCSANOW, a)
        termios.tcflush(fd, termios.TCIFLUSH)       # whatever waited is old
    except Exception:
        return False
    return True


class SerialSource:
    """One open data port.  read() -> bytes (b"" = nothing yet)."""
    transport = "tty"

    def __init__(self, device):
        self.device = device
        self.label = C.SERIAL_URL_FORMAT % device
        self.fd = os.open(device, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
        self.raw = _raw(self.fd)

    def fileno(self):
        return self.fd

    def read(self):
        try:
            data = os.read(self.fd, C.SERIAL_READ_B)
        except OSError as e:
            if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EINTR):
                return b""
            raise Disconnected("read %s: %s" % (self.device, e))
        if not data:
            raise Disconnected("EOF on %s" % self.device)
        return data

    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass


def open_source(port):
    return SerialSource(port.device)


class LineSplitter:
    """bytes in -> whole lines out (no newline).  A line longer than max_b
    is thrown away up to its newline (counted)."""

    def __init__(self, max_b=C.SERIAL_LINE_MAX_B):
        self.max_b = max_b
        self.buf = bytearray()
        self.skipping = False
        self.too_long = 0

    def reset(self):
        self.buf = bytearray()
        self.skipping = False

    def feed(self, data):
        out = []
        self.buf += data
        while True:
            i = self.buf.find(b"\n")
            if i < 0:
                break
            line = bytes(self.buf[:i])
            del self.buf[:i + 1]
            if self.skipping:
                self.skipping = False
                continue
            out.append(line)
        if len(self.buf) > self.max_b:
            self.too_long += 1
            self.buf = bytearray()
            self.skipping = True
        return out


# ---- the status file -------------------------------------------------------
def serial_status_path():
    return os.environ.get(C.SERIAL_STATUS_ENV) or C.SERIAL_STATUS_PATH


def serial_leds_path():
    return os.environ.get(C.SERIAL_LEDS_ENV) or C.SERIAL_LEDS_PATH


def stale_ms_of(hb):
    """A heartbeat line's own period -> how old it may be and still count."""
    try:
        period = float((hb.get("serial") or {}).get("period_s") or C.SERIAL_PERIOD_DEFAULT_S)
    except (TypeError, ValueError, AttributeError):
        period = C.SERIAL_PERIOD_DEFAULT_S
    return period, int(period * C.MS_PER_S * C.SERIAL_STALE_PERIODS) + C.SERIAL_STALE_SLACK_MS


def _led_line(doc):
    """A parsed line -> True if it is a well-formed LED echo line."""
    if not (isinstance(doc, dict) and doc.get("t") == C.SERIAL_LED_TYPE):
        return False
    p, st = doc.get("p"), doc.get("s")
    return (isinstance(p, list) and len(p) == C.SERIAL_LEDS_N and isinstance(st, list)
            and all(isinstance(c, list) and len(c) == 3
                    and all(isinstance(x, int) for x in c) for c in p))


class LedsFile:
    """The newest LED echo line, and whether the heartbeat behind it says
    the echo is on, in SERIAL_LEDS_PATH.  Never raises (errors counted)."""

    def __init__(self, path, wall=time.time):
        self.path = path
        self.wall = wall
        self.writes = 0
        self.errors = 0
        self.doc = {"schema": C.SERIAL_LEDS_SCHEMA, "connected": False, "echo": False,
                    "panel": None, "panel_state": None, "n": None, "led_ms": None,
                    "hb_ms": None, "stale_ms": None, "port": None}

    def _write(self):
        if not self.path:
            return
        try:
            write_json_atomic(self.path, self.doc, prefix=".leds-")
            self.writes += 1
        except Exception as e:
            self.errors += 1
            if self.errors == 1:
                log.warning("LED file %s: %s", self.path, e)

    def led(self, doc, now_ms):
        self.doc.update(panel=doc["p"], panel_state=doc["s"], n=doc.get("n"), led_ms=now_ms,
                        connected=True)
        self._write()

    def heartbeat(self, hb, now_ms, port=None):
        echo = isinstance((hb.get("serial") or {}).get("leds"), dict)
        self.doc.update(echo=echo, hb_ms=now_ms, stale_ms=stale_ms_of(hb)[1], port=port,
                        connected=True)
        if not echo:
            self.doc.update(panel=None, panel_state=None, n=None, led_ms=None)
        self._write()

    def disconnected(self):
        self.doc.update(connected=False, panel=None, panel_state=None, n=None, led_ms=None)
        self._write()


class SerialStatus(IngestStatus):
    """status.json's doc (state, pid, written_ms, ...) plus a "serial"
    section (port, connected, line counters, errors) and "heartbeat": the
    newest good line as the Pico sent it, "heartbeat_ms" when it came."""

    def __init__(self, path=None, leds_path=None, **kw):
        kw.setdefault("mode", C.INGEST_MODE_SERIAL)
        super().__init__(path, **kw)
        self.leds = LedsFile(leds_path, wall=self.wall)   # leds_path None: not written
        self.errors = deque(maxlen=C.SERIAL_STATUS_RECENT_ERRORS)
        self.serial = {
            "looking_for": None, "port": None, "how": None, "connected": False,
            "since_ms": None, "lines": 0, "good": 0, "bad": 0, "not_heartbeat": 0,
            "too_long": 0, "last_line_ms": None, "last_good_ms": None,
            "connects": 0, "disconnects": 0, "errors": 0, "recent_errors": [],
            "led_lines": 0, "last_led_ms": None,
        }
        self.doc["serial"] = self.serial
        self.doc["heartbeat"] = None
        self.doc["heartbeat_ms"] = None

    def _now_ms(self):
        return int(self.wall() * C.MS_PER_S)

    def connected(self, source, how=None):
        self.serial.update(port=source.label, how=how, connected=True,
                           since_ms=self._now_ms(), connects=self.serial["connects"] + 1)
        self._changed = True

    def disconnected(self, why=None):
        was = self.serial["connected"]
        self.serial.update(connected=False, since_ms=self._now_ms() if was else None)
        if was:
            self.serial["disconnects"] += 1
            self.leds.disconnected()
        if why:
            self.error(why)
        self._changed = True

    def error(self, why):
        self.serial["errors"] += 1
        self.errors.append({"ms": self._now_ms(), "error": str(why)[:C.INGEST_STATUS_EXCERPT]})
        self._changed = True

    def line(self, raw, splitter=None):
        """One line from the Pico.  -> True if it was a good heartbeat."""
        s = self.serial
        if splitter is not None:
            s["too_long"] = splitter.too_long
        if not raw.strip():
            return False                      # the Pico's fresh-line newline
        now = self._now_ms()
        s["lines"] += 1
        s["last_line_ms"] = now
        self._changed = True
        try:
            doc = json.loads(raw.decode(C.TEXT_ENCODING))
        except (UnicodeDecodeError, ValueError):
            s["bad"] += 1                     # cut short (connect mid-line, a given-up line)
            self.rejected("not json", raw)
            return False
        if _led_line(doc):
            s["led_lines"] += 1
            s["last_led_ms"] = now
            self.leds.led(doc, now)
            return False
        if not (isinstance(doc, dict) and doc.get(C.F_SCHEMA) == C.SERIAL_HB_SCHEMA
                and doc.get(C.F_TYPE) == C.SERIAL_HB_TYPE and isinstance(doc.get(C.F_BODY), dict)):
            s["not_heartbeat"] += 1
            self.rejected("not a sand.panel/v1 heartbeat", raw)
            return False
        s["good"] += 1
        s["last_good_ms"] = now
        self.doc["heartbeat"] = doc
        self.doc["heartbeat_ms"] = now
        self.leds.heartbeat(doc, now, s["port"])
        return True

    def snapshot(self, ingest=None):
        """No Ingest here: the counters are this reader's own."""
        s = self.serial
        self.doc["counters"] = {"lines": s["lines"], "good": s["good"], "bad": s["bad"],
                                "not_heartbeat": s["not_heartbeat"], "too_long": s["too_long"],
                                "errors": s["errors"], "led_lines": s["led_lines"]}
        s["recent_errors"] = list(self.errors)
        self.doc["recent_rejects"] = list(self.recent)


# ---- the loop ----------------------------------------------------------------
def serve(source, stop, status, splitter, find=None, idle_s=C.SERIAL_IDLE_S,
          check_s=C.SERIAL_RECONNECT_S, clock=time.monotonic, selector=select.select):
    """Read lines until stop or Disconnected."""
    checked = clock()
    while not stop.is_set():
        try:
            ready, _, _ = selector([source], [], [], idle_s)
        except (OSError, ValueError) as e:
            raise Disconnected("select: %s" % e)
        if ready:
            for raw in splitter.feed(source.read()):
                if status.line(raw, splitter):
                    log.debug("heartbeat seq %s", status.doc["heartbeat"].get(C.F_SEQ))
        if clock() - checked >= check_s:
            checked = clock()
            if not os.path.exists(source.device):
                raise Disconnected("%s gone" % source.device)
        status.maybe_write(None)


def run(stop, status, find=find_port, opener=open_source, reconnect_s=C.SERIAL_RECONNECT_S,
        idle_s=C.SERIAL_IDLE_S, once=False, selector=select.select):
    """Find the data port, read it, and again after an unplug, until stop.
    once: return after the first disconnect (tests, a manual check)."""
    splitter = LineSplitter()
    waiting_logged = False
    try:
        while not stop.is_set():
            try:
                port = find()
            except ConsoleRefused as e:
                log.error("%s: not opening it", e)
                status.error(e)
                status.maybe_write(None, force=True)
                return
            if port is None:
                if not waiting_logged:
                    log.info("no Pico data port yet (looking every %.0f s)", reconnect_s)
                    waiting_logged = True
                status.maybe_write(None)
                if once:
                    return
                stop.wait(reconnect_s)
                continue
            try:
                source = opener(port)
            except OSError as e:
                log.warning("cannot open %s: %s (again in %.0f s)", port.device, e, reconnect_s)
                status.serial["port"] = C.SERIAL_URL_FORMAT % port.device
                status.error("open %s: %s" % (port.device, e))
                status.maybe_write(None)
                if once:
                    return
                stop.wait(reconnect_s)
                continue
            waiting_logged = False
            log.info("serial status connected: %s (%s)", source.label, port.how)
            splitter.reset()
            status.connected(source, port.how)
            status.maybe_write(None, force=True)
            try:
                serve(source, stop, status, splitter, find=find, idle_s=idle_s,
                      check_s=reconnect_s, selector=selector)
            except Disconnected as e:
                log.warning("serial status disconnected: %s", e)
                status.disconnected(e)
            finally:
                source.close()
                status.maybe_write(None, force=True)
            if once:
                return
            if not stop.is_set():
                stop.wait(reconnect_s)
    finally:
        if status.serial["connected"]:
            status.disconnected()


# ---- for the pages -------------------------------------------------------------
def latest(now_ms=None, path=None):
    """The newest serial heartbeat, for the sandswing status page and the
    Ingest page: {heartbeat, age_ms, stale, stale_ms, period_s, port,
    connected, file_age_ms, serial} or None (no file, no good line yet)."""
    doc, file_age = read_ingest_status(path or serial_status_path())
    if not doc or not isinstance(doc.get("heartbeat"), dict):
        return None
    now = int(time.time() * C.MS_PER_S) if now_ms is None else now_ms
    hb = doc["heartbeat"]
    at = doc.get("heartbeat_ms")
    age = None if at is None else max(0, now - at)
    period, stale_ms = stale_ms_of(hb)
    serial = doc.get("serial") or {}
    stale = (age is None or age > stale_ms or file_age is None
             or file_age > C.INGEST_STATUS_STALE_MS or doc.get("state") == C.INGEST_STATE_STOPPED)
    return {"heartbeat": hb, "at_ms": at, "age_ms": age, "stale": stale, "stale_ms": stale_ms,
            "period_s": period, "port": serial.get("port"), "connected": serial.get("connected"),
            "file_age_ms": file_age, "serial": serial, "state": doc.get("state")}


def leds(now_ms=None, path=None):
    """The LED echo for /events/api/leds/: {"live", "panel", "panel_state",
    "n", "led_age_ms", "hb_age_ms"}.  live: the port is open, the newest
    heartbeat (younger than its stale_ms) says the echo is on, and a line
    has come (since the port opened).  Not live: panel None (show the
    heartbeat's)."""
    doc, file_age = read_ingest_status(path or serial_leds_path())
    now = int(time.time() * C.MS_PER_S) if now_ms is None else now_ms
    d = doc or {}
    hb_age = None if d.get("hb_ms") is None else max(0, now - d["hb_ms"])
    led_age = None if d.get("led_ms") is None else max(0, now - d["led_ms"])
    live = bool(d.get("connected") and d.get("echo") and d.get("panel")
                and hb_age is not None and d.get("stale_ms") is not None
                and hb_age <= d["stale_ms"])
    return {"live": live, "panel": d.get("panel") if live else None,
            "panel_state": d.get("panel_state") if live else None, "n": d.get("n"),
            "led_age_ms": led_age, "hb_age_ms": hb_age}
