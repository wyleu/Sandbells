"""midiparse.py -- MIDI 1.0 bytes (or aseqdump lines) -> note messages.

Pure: standard library only, no Django, no I/O.

    p = MidiParser()
    for m in p.feed(data):       # bytes from the rawmidi device, any split
        m.kind, m.channel, m.note, m.velocity   # kind MIDI_ON / MIDI_OFF

Notes come out, and the Pico's stroke stamps (StampMessage, kind
MIDI_STAMP: the 7D 'S' SysEx of sandswing midi_stamp.py), in the order
they arrived.  Handled on the way:
  - running status: data bytes after a channel message reuse its status
  - NoteOn with velocity 0 is a NoteOff (it says MIDI_OFF)
  - system exclusive (0xF0 ... 0xF7) is skipped whole (counted in .sysex),
    unless it is a stroke stamp of a known version (counted in .stamps)
  - real-time bytes (0xF8-0xFF) are dropped wherever they are, even inside
    a message or a sysex, and do not touch running status
  - system common (0xF1-0xF6) clears running status; its data is skipped
  - a status byte in the middle of a message abandons the partial one;
    stray data bytes with no status are dropped (counted in .skipped)

parse_seq_line() reads one line of `aseqdump` output (the ALSA sequencer
path, see midiingest.SeqSource) into the same NoteMessage, or a
"System exclusive" line into a StampMessage.
"""

import re
from collections import namedtuple

from . import constants as C

# channel is 1-based (1..16), as people and the sandswing docs say it
NoteMessage = namedtuple("NoteMessage", "kind channel note velocity")
# the Pico's stamp: seq (14 bits), ch = bell channel 1-8 (0: a clock
# message), pico_ms = its tick ms (the stroke's keypad stamp, or now)
StampMessage = namedtuple("StampMessage", "kind seq ch pico_ms")


def parse_stamp(msg):
    """Whole SysEx bytes (F0 .. F7) -> StampMessage, or None (not ours, or
    not a version this knows)."""
    msg = bytes(msg)
    if (len(msg) != C.MIDI_STAMP_LEN or msg[0] != C.MIDI_SYSEX_START
            or msg[-1] != C.MIDI_SYSEX_END or msg[1] != C.MIDI_STAMP_MFR_ID
            or msg[2] != C.MIDI_STAMP_TAG or msg[3] != C.MIDI_STAMP_VERSION
            or any(b >= C.MIDI_STATUS_BIT for b in msg[1:-1])):
        return None
    i = 4
    seq = 0
    for b in msg[i:i + C.MIDI_STAMP_SEQ_BYTES]:
        seq = (seq << C.MIDI_SEVEN_BITS) | b
    i += C.MIDI_STAMP_SEQ_BYTES
    ch = msg[i]
    t = 0
    for b in msg[i + 1:i + 1 + C.MIDI_STAMP_T_BYTES]:
        t = (t << C.MIDI_SEVEN_BITS) | b
    return StampMessage(C.MIDI_STAMP, seq, ch, t)


class MidiParser:
    def __init__(self):
        self.running = None          # status byte of the current channel message
        self.data = []               # its data bytes so far
        self.in_sysex = False
        self.common_left = 0         # data bytes of a system common message to skip
        self.skipped = 0             # bytes dropped (stray data, abandoned messages)
        self.sysex = 0               # sysex messages skipped (not a stamp)
        self.stamps = 0              # stroke / clock stamps parsed
        self.sysex_buf = bytearray() # the sysex so far (None: too long to be ours)

    def feed(self, data):
        """-> list of NoteMessage completed by these bytes."""
        out = []
        for b in bytes(data):
            m = self._byte(b)
            if m is not None:
                out.append(m)
        return out

    def _byte(self, b):
        if b >= C.MIDI_REALTIME_MIN:
            return None                                  # clock, active sensing, ...
        if b >= C.MIDI_STATUS_BIT:
            return self._status(b)
        if self.in_sysex:
            if self.sysex_buf is not None:
                self.sysex_buf.append(b)
                if len(self.sysex_buf) > C.MIDI_SYSEX_KEEP_B:
                    self.sysex_buf = None                # too long to be ours: skip it
            return None
        if self.common_left:
            self.common_left -= 1
            return None
        if self.running is None:
            self.skipped += 1
            return None
        self.data.append(b)
        if len(self.data) < C.MIDI_DATA_LEN[self.running & C.MIDI_TYPE_MASK]:
            return None
        status, data = self.running, self.data
        self.data = []                                   # running status: keep self.running
        return _note(status, data)

    def _status(self, b):
        if self.data:
            self.skipped += len(self.data)               # cut short by a new status
            self.data = []
        if b == C.MIDI_SYSEX_START:
            if self.in_sysex:
                self.sysex += 1                          # one cut short by a new one
            self.in_sysex, self.running, self.common_left = True, None, 0
            self.sysex_buf = bytearray([b])
            return None
        if b == C.MIDI_SYSEX_END:
            stamp = None
            if self.in_sysex:
                if self.sysex_buf is not None:
                    self.sysex_buf.append(b)
                    stamp = parse_stamp(self.sysex_buf)
                if stamp is not None:
                    self.stamps += 1
                else:
                    self.sysex += 1
            self.in_sysex, self.sysex_buf = False, None
            return stamp
        if self.in_sysex:                                # any other status ends a sysex
            self.sysex += 1                              # (cut short: never a stamp)
        self.in_sysex, self.sysex_buf = False, None
        if b in C.MIDI_COMMON_DATA_LEN:
            self.running, self.common_left = None, C.MIDI_COMMON_DATA_LEN[b]
            return None
        self.running, self.common_left = b, 0
        return None


def _note(status, data):
    kind = status & C.MIDI_TYPE_MASK
    if kind not in (C.MIDI_NOTE_ON, C.MIDI_NOTE_OFF):
        return None
    note, vel = data[0], data[1]
    on = kind == C.MIDI_NOTE_ON and vel > 0
    return NoteMessage(C.MIDI_ON if on else C.MIDI_OFF,
                       (status & C.MIDI_CHANNEL_MASK) + 1, note, vel)


# aseqdump (alsa-utils):  " 28:0   Note on                 0, note 65, velocity 100"
# (its channel is 0-based; "Note off" may have no velocity)
_SEQ_NOTE = re.compile(r"^\s*\d+:\d+\s+Note (on|off)\s+(\d+),\s*note (\d+)(?:,\s*velocity (\d+))?")


# aseqdump:  " 28:0   System exclusive          F0 7D 53 01 00 01 03 01 7F 7C 2B 20 F7"
_SEQ_SYSEX = re.compile(r"^\s*\d+:\d+\s+%s\s+((?:[0-9A-Fa-f]{2}\s*)+)$" % C.MIDI_SEQ_SYSEX_WORDS)


def parse_seq_line(line):
    """One aseqdump line -> NoteMessage / StampMessage, or None (header,
    other events, a SysEx that is not a stamp)."""
    if isinstance(line, (bytes, bytearray)):
        line = bytes(line).decode(C.TEXT_ENCODING, "replace")
    m = _SEQ_SYSEX.match(line.rstrip())
    if m:
        return parse_stamp(bytes(int(h, 16) for h in m.group(1).split()))
    m = _SEQ_NOTE.match(line)
    if not m:
        return None
    word, ch, note, vel = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
    vel = int(vel) if vel is not None else 0
    on = word == C.MIDI_ON and vel > 0
    return NoteMessage(C.MIDI_ON if on else C.MIDI_OFF, ch + 1, note, vel)
