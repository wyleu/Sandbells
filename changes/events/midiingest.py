"""midiingest.py -- the Pico's USB MIDI on this Pi -> strokes in the Event
table, with no Wi-Fi.  Run by manage.py ingest_midi.  No Django import here.

sandswing sends one USB MIDI NoteOn per bell stroke (ring.py, and a trigger
plug press since sandswing 0cfd112): channel MIDI_CHANNEL, note per channel
MIDI_NOTE_TO_CH.  Each NoteOn (velocity > 0) on that channel becomes one
sand.event/v1 "stroke" {src MIDI_SRC, body {"ch", "note", "vel", "via", ...}}
and goes through the same Ingest (parse, gap tracker, EventStore batches)
as ingest_udp.  NoteOffs, other channels and unmapped notes are counted only.

Timing (StampPairer, StampClock): newer sandswing sends right after each
stroke NoteOn a SysEx with the stroke's own keypad stamp (Pico ms;
midiparse.StampMessage, sandswing midi_stamp.py), and a clock SysEx every
10 s when quiet.  A NoteOn is held until its stamp (same bell channel)
arrives, at most MIDI_STAMP_WAIT_MS.  Stamped: tick_ms = pico_ms + offset,
offset = min over the window of (arrival monotonic ms - pico ms), utc_ms =
tick_ms + (wall - monotonic), body + {pico_ms, seq, stamped: true,
offset_ms (utc_ms - pico_ms)}.  No stamp in time (older firmware, a lost
SysEx): this Pi's clock at the read, as before, body + {stamped: false}.

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
from .midiparse import MidiParser, parse_seq_line, StampMessage

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
            "stamp": None,           # StampClock / StampPairer counters (StampPairer.counters)
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

    def stamps(self, pairer):
        if pairer is not None:
            self.midi["stamp"] = pairer.counters()

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

    def ch_of(self, msg):
        return self.note_to_ch[msg.note]

    def event(self, msg, utc_ms, tick_ms, extra=None):
        """extra: more body fields (the stamp's)."""
        self.seq += 1
        body = {C.BODY_CH: self.note_to_ch[msg.note], C.MIDI_BODY_NOTE: msg.note,
                C.MIDI_BODY_VEL: msg.velocity, C.MIDI_BODY_VIA: C.MIDI_SRC}
        body.update(extra or {})
        return json.dumps({
            C.F_SCHEMA: C.SCHEMA_EVENT_V1, C.F_TYPE: C.TYPE_STROKE, C.F_SRC: C.MIDI_SRC,
            C.F_ID: C.MIDI_DEVICE_ID, C.F_BOOT_ID: self.boot_id, C.F_SEQ: self.seq,
            C.F_TICK_MS: tick_ms, C.F_UTC_MS: utc_ms,
            C.F_BODY: body,
        }, separators=(",", ":"))


# ---- the Pico's stamps -> stroke times -------------------------------------------
class StampClock:
    """Host monotonic ms <-> Pico ms.  offset = min over the window (last
    MIDI_STAMP_WINDOW_N samples, none older than MIDI_STAMP_WINDOW_MS) of
    (arrival - pico_ms): the least-delayed message bounds the true offset
    from above, and USB / ALSA / this loop only ever add delay.

    A Pico restart (stamp more than MIDI_STAMP_REBOOT_BACK_MS before the last
    one, or seq starting again) empties the window: its tick scale is a new
    one.  reset() (a reconnect) empties it too but keeps the last stamp and
    seq, so a restart behind the reconnect is still counted."""

    def __init__(self, n=C.MIDI_STAMP_WINDOW_N, max_age_ms=C.MIDI_STAMP_WINDOW_MS,
                 reboot_back_ms=C.MIDI_STAMP_REBOOT_BACK_MS):
        self.n, self.max_age_ms, self.reboot_back_ms = n, max_age_ms, reboot_back_ms
        self.samples = deque()       # (arrival ms, arrival - pico_ms)
        self.offset = None           # host monotonic ms - pico ms
        self.spread = None           # max - min of the window's (arrival - pico_ms)
        self.last_pico = None
        self.last_seq = None         # last stroke seq seen (a clock's says it too)
        self.reboots = 0
        self.resets = 0              # window emptied by a reconnect
        self.seq_gaps = 0            # times stroke stamps were missing ...
        self.seq_missing = 0         # ... and how many
        self.seq_odd = 0             # a repeated or older seq (not counted as missing)

    def reset(self):
        if self.samples:
            self.resets += 1
        self.samples.clear()
        self.offset = self.spread = None

    def _rebooted(self, stamp):
        """A Pico restart: its seq started again (a clock with seq 0, or a
        stroke stamp 1, after strokes), or its ms went back by more than
        reboot_back_ms where they cannot (a clock is "now": never before an
        earlier stamp; a stroke stamp can be, if its edge waited in the
        Pico's queue past a clock, but then its seq still follows on)."""
        last, seq = self.last_seq, stamp.seq
        clock = stamp.ch == C.MIDI_STAMP_CH_CLOCK
        if last not in (None, 0):
            if clock and seq == 0:
                return True
            if not clock and seq == 1 and last != C.MIDI_STAMP_SEQ_MAX:
                return True
        if self.last_pico is None or stamp.pico_ms >= self.last_pico - self.reboot_back_ms:
            return False
        follows = last is not None and seq == last % C.MIDI_STAMP_SEQ_MAX + 1
        return clock or not follows

    def _seq(self, stamp):
        """Seq bookkeeping; a stroke stamp should be last + 1, a clock's = last."""
        last, seq = self.last_seq, stamp.seq
        clock = stamp.ch == C.MIDI_STAMP_CH_CLOCK
        if last is None:                             # first sight: strokes before it unknown
            self.last_seq = seq
            return
        if clock:
            missing = (seq - last) % C.MIDI_STAMP_SEQ_MAX
        else:
            missing = (seq - (last % C.MIDI_STAMP_SEQ_MAX + 1)) % C.MIDI_STAMP_SEQ_MAX
        if missing == 0:
            self.last_seq = seq
        elif missing < C.MIDI_STAMP_SEQ_MAX // 2:
            self.seq_gaps += 1
            self.seq_missing += missing
            self.last_seq = seq
        else:
            self.seq_odd += 1                        # repeated / older: keep last

    def add(self, stamp, arrival_ms):
        """One stamp read at arrival_ms (host monotonic).  -> True if it
        showed a Pico restart (the window was emptied first)."""
        rebooted = self._rebooted(stamp)
        if rebooted:
            self.reboots += 1
            self.samples.clear()
            self.last_seq = None
            log.warning("Pico restarted (stamp %d ms after %s, seq %d): stamp offset starts again",
                        stamp.pico_ms, self.last_pico, stamp.seq)
        self._seq(stamp)
        self.last_pico = stamp.pico_ms
        self.samples.append((arrival_ms, arrival_ms - stamp.pico_ms))
        while len(self.samples) > self.n or (
                arrival_ms - self.samples[0][0] > self.max_age_ms):
            self.samples.popleft()
        ds = [d for _, d in self.samples]
        self.offset, self.spread = min(ds), max(ds) - min(ds)
        return rebooted

    def host_ms(self, pico_ms):
        """pico_ms on the host monotonic ms scale (None: no offset yet)."""
        return None if self.offset is None else pico_ms + self.offset


class StampPairer:
    """NoteOn strokes held until their stamp SysEx (same bell channel) or
    MIDI_STAMP_WAIT_MS, then handed to Ingest.  One pending stroke per
    channel: a second NoteOn on it sends the first on unstamped."""

    def __init__(self, ingest, maker, status, wait_ms=C.MIDI_STAMP_WAIT_MS, clock=None,
                 peer=None):
        self.ingest, self.maker, self.status = ingest, maker, status
        self.wait_ms = wait_ms
        self.clock = clock or StampClock()
        self.peer = peer
        self.pending = {}            # bell ch -> (NoteMessage, utc_ms, tick_ms) at arrival
        self.stamped = 0
        self.unstamped = 0
        self.clocks = 0              # clock messages
        self.orphans = 0             # stroke stamps with no NoteOn waiting
        self.last_pico_ms = None
        self.wall_minus_tick = None  # utc ms - monotonic ms at the last read

    # ---- in -------------------------------------------------------------
    def handle(self, msgs, utc_ms, tick_ms):
        """msgs (NoteMessage / StampMessage), all read at utc_ms / tick_ms
        (this Pi's wall and monotonic ms).  -> strokes handed to Ingest."""
        self.wall_minus_tick = utc_ms - tick_ms
        n = 0
        for msg in msgs:
            if isinstance(msg, StampMessage):
                n += self._stamp(msg, tick_ms)
                continue
            why = self.maker.why_not(msg)
            self.status.note(msg, utc_ms, why is None, why if why != "note_offs" else None)
            if why is None:
                ch = self.maker.ch_of(msg)
                if ch in self.pending:                 # its stamp never came
                    n += self._store(ch)
                self.pending[ch] = (msg, utc_ms, tick_ms)
            elif why == "unmapped":
                k = self.status.midi["unmapped"]
                if k == 1 or k % C.MIDI_UNMAPPED_LOG_EVERY == 0:
                    log.warning("note %d on channel %d is not in MIDI_NOTE_TO_CH (%d so far)",
                                msg.note, msg.channel, k)
        # after the messages: a stamp read late with its note still pairs
        return n + self.expire(tick_ms)

    def _stamp(self, stamp, tick_ms):
        self.last_pico_ms = stamp.pico_ms
        self.clock.add(stamp, tick_ms)
        if stamp.ch == C.MIDI_STAMP_CH_CLOCK:
            self.clocks += 1
            return 0
        if stamp.ch not in self.pending:
            self.orphans += 1                          # late (after the wait), or its NoteOn lost
            return 0
        return self._store(stamp.ch, stamp)

    # ---- out ------------------------------------------------------------
    def _store(self, ch, stamp=None):
        msg, utc_ms, tick_ms = self.pending.pop(ch)
        extra = {C.MIDI_BODY_STAMPED: False}
        host = None if stamp is None else self.clock.host_ms(stamp.pico_ms)
        if host is not None:
            tick_ms = host
            utc_ms = host + self.wall_minus_tick
            extra = {C.MIDI_BODY_PICO_MS: stamp.pico_ms, C.MIDI_BODY_STAMP_SEQ: stamp.seq,
                     C.MIDI_BODY_STAMPED: True, C.MIDI_BODY_OFFSET_MS: utc_ms - stamp.pico_ms}
            self.stamped += 1
        else:
            self.unstamped += 1
        self.ingest.handle_frame(self.maker.event(msg, utc_ms, tick_ms, extra), peer=self.peer)
        return 1

    def expire(self, tick_ms):
        """Strokes held longer than wait_ms go on unstamped.  -> how many."""
        n = 0
        for ch in sorted(self.pending, key=lambda c: self.pending[c][2]):
            if tick_ms - self.pending[ch][2] >= self.wait_ms:
                n += self._store(ch)
        return n

    def flush(self):
        """All held strokes on, unstamped (unplug, stop)."""
        n = 0
        for ch in sorted(self.pending, key=lambda c: self.pending[c][2]):
            n += self._store(ch)
        return n

    def wait_s(self, tick_ms, idle_s):
        """select timeout: idle_s, or less when a held stroke falls due."""
        if not self.pending:
            return idle_s
        due = min(t for _, _, t in self.pending.values()) + self.wait_ms
        return max(0.0, min(idle_s, (due - tick_ms) / C.MS_PER_S))

    def counters(self):
        """The status file's midi.stamp section."""
        c = self.clock
        wall_off = (None if c.offset is None or self.wall_minus_tick is None
                    else c.offset + self.wall_minus_tick)
        return {"stamped": self.stamped, "unstamped": self.unstamped,
                "clocks": self.clocks, "orphans": self.orphans,
                "offset_ms": wall_off, "offset_tick_ms": c.offset,
                "offset_spread": c.spread, "offset_samples": len(c.samples),
                "reboots": c.reboots, "window_resets": c.resets,
                "seq_gaps": c.seq_gaps, "seq_missing": c.seq_missing, "seq_odd": c.seq_odd,
                "last_seq": c.last_seq, "last_pico_ms": self.last_pico_ms,
                "wait_ms": self.wait_ms, "held": len(self.pending)}


def handle_notes(msgs, ingest, maker, status, utc_ms, tick_ms, peer=None, pairer=None):
    """Store the strokes among msgs (all read at utc_ms).  -> strokes stored.
    Without a pairer every NoteOn goes at once, unstamped (stamps ignored)."""
    if pairer is None:
        pairer = StampPairer(ingest, maker, status, peer=peer)
        n = pairer.handle(msgs, utc_ms, tick_ms)
        return n + pairer.flush()
    return pairer.handle(msgs, utc_ms, tick_ms)


def serve(source, ingest, stop, maker, status, find=None, idle_s=C.MIDI_IDLE_S,
          check_s=C.MIDI_RECONNECT_S, wall=time.time, tick=time.monotonic,
          clock=time.monotonic, pairer=None):
    """Read source until stop or Disconnected (re-raised).  Quiet second ->
    ingest.idle().  Every check_s: find() must still see the port.  Held
    strokes (pairer) go on when their stamp comes or their wait ends; the
    caller flushes the rest."""
    checked = clock()
    parser = getattr(source, "parser", None)
    if pairer is None:
        pairer = StampPairer(ingest, maker, status)
    pairer.peer = source.label
    while not stop.is_set():
        r, _, _ = select.select([source], [], [],
                                pairer.wait_s(int(tick() * C.MS_PER_S), idle_s))
        utc_ms, tick_ms = int(wall() * C.MS_PER_S), int(tick() * C.MS_PER_S)
        if r:
            msgs = source.read()                      # Disconnected goes up
            pairer.handle(msgs, utc_ms, tick_ms)
            status.parser(parser)
            status.stamps(pairer)
            ingest.maybe_summary()
        elif pairer.pending:
            pairer.expire(tick_ms)
            status.stamps(pairer)
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
    pairer = StampPairer(ingest, maker, status)
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
            pairer.clock.reset()          # the Pico may have restarted behind the unplug
            status.connected(source)
            ingest.note("connected", via=C.MIDI_SRC, port=source.label)
            status.maybe_write(ingest, force=True)
            try:
                serve(source, ingest, stop, maker, status, find=find, idle_s=idle_s,
                      check_s=reconnect_s, pairer=pairer)
            except Disconnected as e:
                log.warning("MIDI disconnected: %s", e)
                status.disconnected(e)
                ingest.note("disconnected", via=C.MIDI_SRC, port=source.label, why=str(e))
            finally:
                source.close()
                pairer.flush()            # held strokes: unstamped, never lost
                status.stamps(pairer)
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
