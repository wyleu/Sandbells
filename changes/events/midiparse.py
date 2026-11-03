"""midiparse.py -- MIDI 1.0 bytes (or aseqdump lines) -> note messages.

Pure: standard library only, no Django, no I/O.

    p = MidiParser()
    for m in p.feed(data):       # bytes from the rawmidi device, any split
        m.kind, m.channel, m.note, m.velocity   # kind MIDI_ON / MIDI_OFF

Only notes come out.  Handled on the way:
  - running status: data bytes after a channel message reuse its status
  - NoteOn with velocity 0 is a NoteOff (it says MIDI_OFF)
  - system exclusive (0xF0 ... 0xF7) is skipped whole
  - real-time bytes (0xF8-0xFF) are dropped wherever they are, even inside
    a message or a sysex, and do not touch running status
  - system common (0xF1-0xF6) clears running status; its data is skipped
  - a status byte in the middle of a message abandons the partial one;
    stray data bytes with no status are dropped (counted in .skipped)

parse_seq_line() reads one line of `aseqdump` output (the ALSA sequencer
path, see midiingest.SeqSource) into the same NoteMessage.
"""

import re
from collections import namedtuple

from . import constants as C

# channel is 1-based (1..16), as people and the sandswing docs say it
NoteMessage = namedtuple("NoteMessage", "kind channel note velocity")


class MidiParser:
    def __init__(self):
        self.running = None          # status byte of the current channel message
        self.data = []               # its data bytes so far
        self.in_sysex = False
        self.common_left = 0         # data bytes of a system common message to skip
        self.skipped = 0             # bytes dropped (stray data, abandoned messages)
        self.sysex = 0               # sysex messages skipped

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
            self.in_sysex, self.running, self.common_left = True, None, 0
            return None
        if b == C.MIDI_SYSEX_END:
            if self.in_sysex:
                self.sysex += 1
            self.in_sysex = False
            return None
        self.in_sysex = False                            # any other status ends a sysex
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


def parse_seq_line(line):
    """One aseqdump line -> NoteMessage, or None (header, other events)."""
    if isinstance(line, (bytes, bytearray)):
        line = bytes(line).decode(C.TEXT_ENCODING, "replace")
    m = _SEQ_NOTE.match(line)
    if not m:
        return None
    word, ch, note, vel = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
    vel = int(vel) if vel is not None else 0
    on = word == C.MIDI_ON and vel > 0
    return NoteMessage(C.MIDI_ON if on else C.MIDI_OFF, ch + 1, note, vel)
