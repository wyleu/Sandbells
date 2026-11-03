"""midiingest.py -- the Pico's USB MIDI on this Pi -> strokes in the Event
table, with no Wi-Fi.  Run by manage.py ingest_midi.  No Django import here.

sandswing sends one USB MIDI NoteOn per bell stroke (ring.py, and a trigger
plug press since sandswing 0cfd112): channel MIDI_CHANNEL, note per channel
MIDI_NOTE_TO_CH.  Each NoteOn (velocity > 0) on that channel becomes one
sand.event/v1 "stroke" {src MIDI_SRC, body {"ch", "note", "vel", "via"}},
stamped with this Pi's clock at the read (MIDI carries no time), and goes
through the same Ingest (parse, gap tracker, EventStore batches) as
ingest_udp.  NoteOffs, other channels and unmapped notes are counted only.

Finding the Pico: the first ALSA card in /proc/asound/cards whose lines (or
its /proc/asound/cardN/midiD files) contain one of MIDI_CARD_MATCH
("Pico 2 W", "CircuitPython"); --card / SANDBELLS_MIDI_CARD gives another
substring, --device / SANDBELLS_MIDI_DEVICE a rawmidi device outright.

Reading it (--transport):
  raw   /dev/snd/midiC<card>D<dev>, os.read, no package needed.  The rawmidi
        input is exclusive: if PipeWire's (or anyone's) ALSA seq bridge is
        subscribed to the Pico, open() fails with EBUSY.
  seq   `aseqdump -p "<card name>"` (alsa-utils), read line by line: a
        sequencer subscriber, shares the port with PipeWire.
  auto  raw; on EBUSY, seq (if aseqdump is installed).
Unplugged (read error, EOF, aseqdump exit, or the card gone from
/proc/asound/cards): close, then look again every MIDI_RECONNECT_S.
"""

import errno
import glob
import json
import logging
import os
import re
import select
import shutil
import subprocess
import time
from collections import deque, namedtuple

from . import constants as C
from .ingeststatus import IngestStatus
from .midiparse import MidiParser, parse_seq_line

log = logging.getLogger(C.LOGGER_NAME + ".midi")   # under setup_logging()'s handler

# card: ALSA card number (None for a --device override); name: its short
# name (the seq client name, for aseqdump); device: the rawmidi node
Port = namedtuple("Port", "card name device")

_CARD_LINE = re.compile(r"^\s*(\d+)\s+\[(.*?)\s*\]:\s*(.*)$")


class Disconnected(Exception):
    """The port went away (unplugged, EOF, aseqdump ended)."""


# ---- finding the Pico -------------------------------------------------------
def read_cards(path=C.MIDI_PROC_CARDS):
    """/proc/asound/cards -> [(number, text of its lines, short name)]."""
    try:
        with open(path) as f:
            lines = f.read().splitlines()
    except OSError:
        return []
    cards = []
    for line in lines:
        m = _CARD_LINE.match(line)
        if m:
            rest = m.group(3)
            short = rest.split(" - ", 1)[1].strip() if " - " in rest else rest.strip()
            cards.append([int(m.group(1)), line, short])
        elif cards:
            cards[-1][1] += "\n" + line
    return [tuple(c) for c in cards]


def midi_devices(card, card_dir=C.MIDI_PROC_CARD_DIR):
    """[(device number, text of /proc/asound/cardN/midiD)] of one card."""
    out = []
    for p in glob.glob(os.path.join(card_dir % card, C.MIDI_PROC_MIDI_GLOB)):
        d = os.path.basename(p)[len("midi"):]
        if not d.isdigit():
            continue
        try:
            with open(p) as f:
                text = f.read()
        except OSError:
            text = ""
        out.append((int(d), text))
    return sorted(out)


def find_port(match=C.MIDI_CARD_MATCH, device=None, cards_path=C.MIDI_PROC_CARDS,
              card_dir=C.MIDI_PROC_CARD_DIR, dev_format=C.MIDI_DEV_FORMAT):
    """-> Port of the Pico, or None (not plugged in)."""
    if device:
        if not os.path.exists(device):
            return None
        m = re.search(r"midiC(\d+)D\d+$", device)
        card = int(m.group(1)) if m else None
        name = None
        if card is not None:
            name = next((s for n, _, s in read_cards(cards_path) if n == card), None)
        return Port(card, name, device)
    for num, text, short in read_cards(cards_path):
        devs = midi_devices(num, card_dir)
        if not devs:
            continue
        hay = "\n".join([text] + [t for _, t in devs])
        if any(s and s in hay for s in match):
            return Port(num, short, dev_format % (num, devs[0][0]))
    return None


# ---- reading it ---------------------------------------------------------------
class RawSource:
    """The rawmidi device, read with os.read (non-blocking, select)."""
    transport = C.MIDI_TRANSPORT_RAW

    def __init__(self, path, fd=None):
        self.path = path
        self.fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK) if fd is None else fd
        self.parser = MidiParser()
        self.label = C.MIDI_URL_FORMAT % path

    def fileno(self):
        return self.fd

    def read(self):
        """-> NoteMessages from the bytes waiting.  Disconnected at EOF / error."""
        try:
            data = os.read(self.fd, C.MIDI_READ_B)
        except BlockingIOError:
            return []
        except OSError as e:                       # ENODEV / EIO: unplugged
            raise Disconnected("%s: %s" % (self.path, e))
        if not data:
            raise Disconnected("%s: end of file" % self.path)
        return self.parser.feed(data)

    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass


class SeqSource:
    """`aseqdump -p <port>`: the ALSA sequencer (shares the port with PipeWire)."""
    transport = C.MIDI_TRANSPORT_SEQ

    def __init__(self, port_name, popen=subprocess.Popen, which=shutil.which):
        cmd = [C.MIDI_SEQ_DUMP, "-p", port_name]
        if which(C.MIDI_SEQ_LINEBUF[0]):
            cmd = list(C.MIDI_SEQ_LINEBUF) + cmd
        self.proc = popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          stdin=subprocess.DEVNULL, bufsize=0)
        self.fd = self.proc.stdout.fileno()
        os.set_blocking(self.fd, False)
        self.buf = b""
        self.label = C.MIDI_URL_FORMAT % ("seq:" + port_name)

    def fileno(self):
        return self.fd

    def read(self):
        try:
            data = os.read(self.fd, C.MIDI_READ_B)
        except BlockingIOError:
            return []
        except OSError as e:
            raise Disconnected("aseqdump: %s" % e)
        if not data:
            err = b""
            try:
                err = self.proc.stderr.read() or b""
            except (OSError, ValueError):
                pass
            raise Disconnected("aseqdump ended (%s) %s" % (
                self.proc.poll(), err.decode(C.TEXT_ENCODING, "replace").strip()))
        self.buf += data
        *lines, self.buf = self.buf.split(b"\n")
        return [m for m in (parse_seq_line(l) for l in lines) if m is not None]

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(C.MIDI_STOP_WAIT_S)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        for f in (self.proc.stdout, self.proc.stderr):
            try:
                f.close()
            except (OSError, AttributeError):
                pass


def open_source(port, transport=C.MIDI_TRANSPORT_AUTO, which=shutil.which):
    """-> RawSource / SeqSource.  OSError if it cannot be opened."""
    if transport == C.MIDI_TRANSPORT_SEQ:
        return SeqSource(port.name or str(port.card))
    try:
        return RawSource(port.device)
    except OSError as e:
        if (transport == C.MIDI_TRANSPORT_AUTO and e.errno == errno.EBUSY
                and which(C.MIDI_SEQ_DUMP) and (port.name or port.card is not None)):
            log.warning("%s busy (PipeWire / an ALSA seq subscriber has it): "
                        "reading through the ALSA sequencer instead", port.device)
            return SeqSource(port.name or str(port.card))
        raise


# ---- the status file -------------------------------------------------------
def midi_status_path():
    return os.environ.get(C.MIDI_STATUS_ENV) or C.MIDI_STATUS_PATH


class MidiStatus(IngestStatus):
    """ingest_udp's status.json doc plus a "midi" section: port, connected,
    notes received, last note time, errors.  Rewritten every
    INGEST_STATUS_WRITE_S (5 s) and on a change (at most once a second)."""

    def __init__(self, path=None, **kw):
        kw.setdefault("mode", C.INGEST_MODE_MIDI)
        super().__init__(path, **kw)
        self.errors = deque(maxlen=C.MIDI_STATUS_RECENT_ERRORS)
        self.midi = {
            "looking_for": None, "port": None, "transport": None, "connected": False, "since_ms": None,
            "notes_received": 0, "note_ons": 0, "note_offs": 0, "strokes": 0,
            "unmapped": 0, "other_channel": 0, "last_note_ms": None, "last_note": None,
            "connects": 0, "disconnects": 0, "errors": 0, "recent_errors": [],
            "parser_skipped": 0, "sysex_skipped": 0,
        }
        self.doc["midi"] = self.midi

    def _now_ms(self):
        return int(self.wall() * C.MS_PER_S)

    def connected(self, source):
        self.midi.update(port=source.label, transport=source.transport, connected=True,
                         since_ms=self._now_ms(), connects=self.midi["connects"] + 1)
        self._changed = True

    def disconnected(self, why=None):
        was = self.midi["connected"]
        self.midi.update(connected=False, since_ms=None if not was else self._now_ms())
        if was:
            self.midi["disconnects"] += 1
        if why:
            self.error(why)
        self._changed = True

    def searching(self, port_label):
        self.midi["port"] = port_label

    def error(self, why):
        self.midi["errors"] += 1
        self.errors.append({"ms": self._now_ms(), "error": str(why)[:C.INGEST_STATUS_EXCERPT]})
        self._changed = True

    def note(self, msg, at_ms, stroke, why=None):
        m = self.midi
        m["notes_received"] += 1
        m["note_ons" if msg.kind == C.MIDI_ON else "note_offs"] += 1
        if stroke:
            m["strokes"] += 1
        elif why:
            m[why] += 1
        m["last_note_ms"] = at_ms
        m["last_note"] = {"kind": msg.kind, "channel": msg.channel, "note": msg.note,
                          "velocity": msg.velocity}
        self._changed = True

    def parser(self, p):
        if p is not None:
            self.midi.update(parser_skipped=p.skipped, sysex_skipped=p.sysex)

    def snapshot(self, ingest):
        super().snapshot(ingest)
        self.midi["recent_errors"] = list(self.errors)


# ---- notes -> strokes ---------------------------------------------------------
class StrokeMaker:
    """NoteMessage -> sand.event/v1 stroke text (or None), own boot_id/seq."""

    def __init__(self, channel=C.MIDI_CHANNEL, note_to_ch=None, wall=time.time,
                 tick=time.monotonic, boot_id=None):
        self.channel = int(channel)
        self.note_to_ch = dict(C.MIDI_NOTE_TO_CH if note_to_ch is None else note_to_ch)
        self.wall, self.tick = wall, tick
        self.boot_id = boot_id or os.urandom(4).hex()   # one per run, as a Pico boot
        self.seq = 0

    def why_not(self, msg):
        """None if msg is a stroke, else the MidiStatus counter it goes to."""
        if msg.kind != C.MIDI_ON:
            return "note_offs"
        if self.channel != C.MIDI_CHANNEL_ANY and msg.channel != self.channel:
            return "other_channel"
        if msg.note not in self.note_to_ch:
            return "unmapped"
        return None

    def event(self, msg, utc_ms, tick_ms):
        self.seq += 1
        return json.dumps({
            C.F_SCHEMA: C.SCHEMA_EVENT_V1, C.F_TYPE: C.TYPE_STROKE, C.F_SRC: C.MIDI_SRC,
            C.F_ID: C.MIDI_DEVICE_ID, C.F_BOOT_ID: self.boot_id, C.F_SEQ: self.seq,
            C.F_TICK_MS: tick_ms, C.F_UTC_MS: utc_ms,
            C.F_BODY: {C.BODY_CH: self.note_to_ch[msg.note], C.MIDI_BODY_NOTE: msg.note,
                       C.MIDI_BODY_VEL: msg.velocity, C.MIDI_BODY_VIA: C.MIDI_SRC},
        }, separators=(",", ":"))


def handle_notes(msgs, ingest, maker, status, utc_ms, tick_ms, peer=None):
    """Store the strokes among msgs (all read at utc_ms).  -> strokes stored."""
    n = 0
    for msg in msgs:
        why = maker.why_not(msg)
        status.note(msg, utc_ms, why is None, why if why != "note_offs" else None)
        if why is None:
            ingest.handle_frame(maker.event(msg, utc_ms, tick_ms), peer=peer)
            n += 1
        elif why == "unmapped":
            k = status.midi["unmapped"]
            if k == 1 or k % C.MIDI_UNMAPPED_LOG_EVERY == 0:
                log.warning("note %d on channel %d is not in MIDI_NOTE_TO_CH (%d so far)",
                            msg.note, msg.channel, k)
    return n


def serve(source, ingest, stop, maker, status, find=None, idle_s=C.MIDI_IDLE_S,
          check_s=C.MIDI_RECONNECT_S, wall=time.time, tick=time.monotonic,
          clock=time.monotonic):
    """Read source until stop or Disconnected (re-raised).  Quiet second ->
    ingest.idle().  Every check_s: find() must still see the port."""
    checked = clock()
    parser = getattr(source, "parser", None)
    while not stop.is_set():
        r, _, _ = select.select([source], [], [], idle_s)
        if r:
            utc_ms, tick_ms = int(wall() * C.MS_PER_S), int(tick() * C.MS_PER_S)
            msgs = source.read()                      # Disconnected goes up
            handle_notes(msgs, ingest, maker, status, utc_ms, tick_ms, peer=source.label)
            status.parser(parser)
            ingest.maybe_summary()
        else:
            ingest.idle()
        if find is not None and clock() - checked >= check_s:
            checked = clock()
            if find() is None:
                raise Disconnected("card gone from %s" % C.MIDI_PROC_CARDS)
        status.maybe_write(ingest)


def run(ingest, stop, status, find=find_port, opener=open_source,
        transport=C.MIDI_TRANSPORT_AUTO, maker=None, reconnect_s=C.MIDI_RECONNECT_S,
        idle_s=C.MIDI_IDLE_S, once=False):
    """Find the Pico, read it, and again after an unplug, until stop.  once:
    return after the first disconnect (tests, a manual check).  Flushes on
    the way out."""
    maker = maker or StrokeMaker()
    waiting_logged = False
    try:
        while not stop.is_set():
            port = find()
            if port is None:
                if not waiting_logged:
                    log.info("no MIDI port yet (looking every %.0f s)", reconnect_s)
                    waiting_logged = True
                status.maybe_write(ingest)
                ingest.idle()
                stop.wait(reconnect_s)
                continue
            try:
                source = opener(port, transport)
            except OSError as e:
                log.warning("cannot open %s: %s (again in %.0f s)", port.device, e, reconnect_s)
                status.searching(C.MIDI_URL_FORMAT % port.device)
                status.error("open %s: %s" % (port.device, e))
                status.maybe_write(ingest)
                ingest.idle()
                if once:
                    return
                stop.wait(reconnect_s)
                continue
            waiting_logged = False
            log.info("MIDI connected: %s (%s)", source.label, source.transport)
            ingest.new_connection()
            status.connected(source)
            ingest.note("connected", via=C.MIDI_SRC, port=source.label)
            status.maybe_write(ingest, force=True)
            try:
                serve(source, ingest, stop, maker, status, find=find, idle_s=idle_s,
                      check_s=reconnect_s)
            except Disconnected as e:
                log.warning("MIDI disconnected: %s", e)
                status.disconnected(e)
                ingest.note("disconnected", via=C.MIDI_SRC, port=source.label, why=str(e))
            finally:
                source.close()
                ingest.flush()
                status.maybe_write(ingest, force=True)
            if once:
                return
            if not stop.is_set():
                stop.wait(reconnect_s)
    finally:
        if status.midi["connected"]:
            status.disconnected()
        ingest.flush()
