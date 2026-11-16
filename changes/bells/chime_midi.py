"""Standard MIDI files for Chimes: read, time, write.  Stdlib only, no Django,
so tools/chimes/chime-build (on the desk Pi) and the player driver use it too.

Times: every note gets its tick, its beat (quarter notes from the start) and
its second at the file's own tempo map.  Tempo changes for playback are not
written into the file: the player divides the seconds by the tempo factor.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from fractions import Fraction

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HEADER_CHUNK = b"MThd"
TRACK_CHUNK = b"MTrk"
HEADER_LENGTH = 6
CHUNK_HEAD_BYTES = 8

MICROSECONDS_PER_SECOND = 1_000_000
SECONDS_PER_MINUTE = 60
DEFAULT_TEMPO_US = 500_000                 # MIDI default: 120 quarter notes a minute
DEFAULT_PPQ = 384                          # ticks per quarter (LilyPond writes 384)
QUARTERS_PER_WHOLE = 4                     # LilyPond moments are whole notes

STATUS_MASK = 0xF0
CHANNEL_MASK = 0x0F
NOTE_OFF = 0x80
NOTE_ON = 0x90
POLY_PRESSURE = 0xA0
CONTROL_CHANGE = 0xB0
PROGRAM_CHANGE = 0xC0
CHANNEL_PRESSURE = 0xD0
PITCH_BEND = 0xE0
SYSEX = 0xF0
SYSEX_ESCAPE = 0xF7
META = 0xFF
META_TEMPO = 0x51
META_TIME_SIGNATURE = 0x58
META_END_OF_TRACK = 0x2F
META_TRACK_NAME = 0x03
DATA_BYTES = {NOTE_OFF: 2, NOTE_ON: 2, POLY_PRESSURE: 2, CONTROL_CHANGE: 2,
              PROGRAM_CHANGE: 1, CHANNEL_PRESSURE: 1, PITCH_BEND: 2}
VLQ_MASK = 0x7F
VLQ_MORE = 0x80
VLQ_SHIFT = 7
DEFAULT_VELOCITY = 100
MIDI_FORMAT_SINGLE = 0
CC_SUSTAIN = 64
CC_ALL_SOUND_OFF = 120
CC_ALL_NOTES_OFF = 123
MIDI_CHANNEL_COUNT = 16
PLAYBACK_TEMPO_US = 1_000_000              # played-back copies: 60 quarters a minute ...
PLAYBACK_PPQ = 1000                        # ... at 1000 ticks a quarter, so a tick is 1 ms
PLAYBACK_KIND_STATUS = {"on": NOTE_ON, "off": NOTE_OFF, "cc": CONTROL_CHANGE,
                        "prog": PROGRAM_CHANGE}

NOTE_NAMES_SHARP = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
NOTE_NAMES_FLAT = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")
SEMITONES_PER_OCTAVE = 12
MIDI_OCTAVE_OFFSET = 1                     # MIDI 60 is C4


class MidiError(ValueError):
    """Not a MIDI file this code can read."""


@dataclass
class MidiEvent:
    tick: int
    status: int                            # high nibble for channel events, META, SYSEX
    channel: int = 0
    data: tuple = ()
    meta_type: int | None = None
    meta: bytes = b""


@dataclass
class Note:
    tick: int
    channel: int
    pitch: int
    velocity: int
    end_tick: int
    sec: float = 0.0
    end_sec: float = 0.0


@dataclass
class MidiFile:
    ppq: int
    format: int
    tracks: list = field(default_factory=list)      # list of [MidiEvent]

    def events(self):
        """Every event of every track, in tick order (stable by track)."""
        merged = [e for t in self.tracks for e in t]
        merged.sort(key=lambda e: e.tick)
        return merged


def pitch_name(midi: int, flats: bool = True) -> str:
    names = NOTE_NAMES_FLAT if flats else NOTE_NAMES_SHARP
    octave = midi // SEMITONES_PER_OCTAVE - MIDI_OCTAVE_OFFSET
    return "%s%d" % (names[midi % SEMITONES_PER_OCTAVE], octave)


def _vlq(data: bytes, pos: int):
    value = 0
    while True:
        if pos >= len(data):
            raise MidiError("truncated variable-length number")
        b = data[pos]
        pos += 1
        value = (value << VLQ_SHIFT) | (b & VLQ_MASK)
        if not b & VLQ_MORE:
            return value, pos


def _encode_vlq(value: int) -> bytes:
    out = [value & VLQ_MASK]
    value >>= VLQ_SHIFT
    while value:
        out.append((value & VLQ_MASK) | VLQ_MORE)
        value >>= VLQ_SHIFT
    return bytes(reversed(out))


def _read_track(data: bytes) -> list:
    events, pos, tick, running = [], 0, 0, None
    while pos < len(data):
        delta, pos = _vlq(data, pos)
        tick += delta
        if pos >= len(data):
            raise MidiError("truncated track")
        status = data[pos]
        if status == META:
            meta_type = data[pos + 1]
            length, pos = _vlq(data, pos + 2)
            events.append(MidiEvent(tick, META, meta_type=meta_type,
                                    meta=data[pos:pos + length]))
            pos += length
            if meta_type == META_END_OF_TRACK:
                break
            continue
        if status in (SYSEX, SYSEX_ESCAPE):
            length, pos = _vlq(data, pos + 1)
            pos += length
            continue
        if status & VLQ_MORE:
            running = status
            pos += 1
        elif running is None:
            raise MidiError("data byte without a status")
        kind, channel = running & STATUS_MASK, running & CHANNEL_MASK
        n = DATA_BYTES.get(kind)
        if n is None:
            raise MidiError("unknown status 0x%02x" % running)
        args = tuple(data[pos:pos + n])
        if len(args) != n:
            raise MidiError("truncated event")
        pos += n
        events.append(MidiEvent(tick, kind, channel, args))
    return events


def read_midi(data: bytes) -> MidiFile:
    if data[:4] != HEADER_CHUNK:
        raise MidiError("not a MIDI file (no MThd)")
    length = struct.unpack(">I", data[4:8])[0]
    if length < HEADER_LENGTH:
        raise MidiError("short MIDI header")
    fmt, ntracks, division = struct.unpack(">HHH", data[8:8 + HEADER_LENGTH])
    if division & 0x8000:
        raise MidiError("SMPTE time division is not supported")
    mf = MidiFile(ppq=division, format=fmt)
    pos = CHUNK_HEAD_BYTES + length
    while pos + CHUNK_HEAD_BYTES <= len(data) and len(mf.tracks) < ntracks:
        kind = data[pos:pos + 4]
        size = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        body = data[pos + CHUNK_HEAD_BYTES:pos + CHUNK_HEAD_BYTES + size]
        if kind == TRACK_CHUNK:
            mf.tracks.append(_read_track(body))
        pos += CHUNK_HEAD_BYTES + size
    if not mf.tracks:
        raise MidiError("MIDI file has no tracks")
    return mf


class TempoMap:
    """Ticks to seconds through every tempo change."""

    def __init__(self, mf: MidiFile):
        self.ppq = mf.ppq
        changes = [(e.tick, int.from_bytes(e.meta, "big")) for e in mf.events()
                   if e.status == META and e.meta_type == META_TEMPO and e.meta]
        self.points = []                       # (tick, sec at tick, us per quarter)
        tick, sec, tempo = 0, 0.0, DEFAULT_TEMPO_US
        for t, us in changes:
            sec += (t - tick) * tempo / (self.ppq * MICROSECONDS_PER_SECOND)
            tick, tempo = t, us
            self.points.append((tick, sec, tempo))
        if not self.points or self.points[0][0] != 0:
            self.points.insert(0, (0, 0.0, changes[0][1] if changes and changes[0][0] == 0
                                   else DEFAULT_TEMPO_US))

    def seconds(self, tick: int) -> float:
        base = self.points[0]
        for p in self.points:
            if p[0] <= tick:
                base = p
            else:
                break
        t0, s0, us = base
        return s0 + (tick - t0) * us / (self.ppq * MICROSECONDS_PER_SECOND)

    def first_bpm(self) -> float:
        return SECONDS_PER_MINUTE * MICROSECONDS_PER_SECOND / self.points[0][2]


def notes(mf: MidiFile) -> list:
    """Every sounded note (note on with velocity > 0, to its note off)."""
    tm = TempoMap(mf)
    open_notes, out = {}, []
    for e in mf.events():
        if e.status not in (NOTE_ON, NOTE_OFF):
            continue
        pitch, vel = e.data
        key = (e.channel, pitch)
        if e.status == NOTE_ON and vel > 0:
            if key in open_notes:                     # retrigger: close the old one
                n = open_notes.pop(key)
                n.end_tick = e.tick
            n = Note(e.tick, e.channel, pitch, vel, e.tick)
            open_notes[key] = n
            out.append(n)
        elif key in open_notes:
            open_notes.pop(key).end_tick = e.tick
    for n in out:
        n.sec, n.end_sec = tm.seconds(n.tick), tm.seconds(n.end_tick)
    out.sort(key=lambda n: (n.tick, n.pitch))
    return out


def chords(note_list: list) -> list:
    """Notes grouped by start tick: [(tick, sec, (pitches...))]."""
    out = []
    for n in note_list:
        if out and out[-1][0] == n.tick:
            out[-1][2].append(n.pitch)
        else:
            out.append((n.tick, n.sec, [n.pitch]))
    return [(t, s, tuple(sorted(set(p)))) for t, s, p in out]


def playback_messages(mf: MidiFile, program_changes: bool = False) -> list:
    """What the player sends, in order: (sec, kind, channel, a, b).  kind is
    'on', 'off', 'cc' or 'prog' (program changes only when asked for: a bell
    soundfont usually has one preset and a General MIDI program would silence it)."""
    tm = TempoMap(mf)
    out = []
    for e in mf.events():
        if e.status == NOTE_ON and e.data[1] > 0:
            out.append((tm.seconds(e.tick), "on", e.channel, e.data[0], e.data[1]))
        elif e.status in (NOTE_ON, NOTE_OFF):
            out.append((tm.seconds(e.tick), "off", e.channel, e.data[0], 0))
        elif e.status == CONTROL_CHANGE:
            out.append((tm.seconds(e.tick), "cc", e.channel, e.data[0], e.data[1]))
        elif e.status == PROGRAM_CHANGE and program_changes:
            out.append((tm.seconds(e.tick), "prog", e.channel, e.data[0], 0))
    return out


def scale_times(messages: list, factor: float, from_sec: float = 0.0) -> list:
    """Playback at factor x the written tempo (2.0 = twice as fast), starting
    at from_sec of the written time.  Returns (sec from now, ...) in order.
    Notes already sounding at from_sec are not restarted."""
    if factor <= 0:
        raise ValueError("tempo factor must be positive")
    return [((sec - from_sec) / factor,) + tuple(m[1:])
            for m in messages for sec in (m[0],) if sec >= from_sec]


def write_midi(note_list, ppq: int = DEFAULT_PPQ, bpm: float = None,
               track_name: str = "") -> bytes:
    """A format 0 file from (start_tick, end_tick, pitch[, velocity, channel])."""
    events = []
    if track_name:
        events.append((0, 0, bytes([META, META_TRACK_NAME])
                       + _encode_vlq(len(track_name.encode())) + track_name.encode()))
    if bpm:
        us = round(SECONDS_PER_MINUTE * MICROSECONDS_PER_SECOND / bpm)
        events.append((0, 0, bytes([META, META_TEMPO, 3]) + us.to_bytes(3, "big")))
    for n in note_list:
        start, end, pitch = n[0], n[1], n[2]
        vel = n[3] if len(n) > 3 else DEFAULT_VELOCITY
        ch = n[4] if len(n) > 4 else 0
        events.append((end, 1, bytes([NOTE_OFF | ch, pitch, 0])))
        events.append((start, 2, bytes([NOTE_ON | ch, pitch, vel])))
    events.sort(key=lambda e: (e[0], e[1]))
    body, last = b"", 0
    for tick, _, raw in events:
        body += _encode_vlq(tick - last) + raw
        last = tick
    body += _encode_vlq(0) + bytes([META, META_END_OF_TRACK, 0])
    header = HEADER_CHUNK + struct.pack(">IHHH", HEADER_LENGTH, MIDI_FORMAT_SINGLE, 1, ppq)
    return header + TRACK_CHUNK + struct.pack(">I", len(body)) + body


def _format0(events: list, ppq: int, tempo_us: int) -> bytes:
    """A format 0 file from (tick, raw bytes) in order, with one tempo."""
    body = _encode_vlq(0) + bytes([META, META_TEMPO, 3]) + tempo_us.to_bytes(3, "big")
    last = 0
    for tick, raw in events:
        body += _encode_vlq(max(0, tick - last)) + raw
        last = max(last, tick)
    body += _encode_vlq(0) + bytes([META, META_END_OF_TRACK, 0])
    header = HEADER_CHUNK + struct.pack(">IHHH", HEADER_LENGTH, MIDI_FORMAT_SINGLE, 1, ppq)
    return header + TRACK_CHUNK + struct.pack(">I", len(body)) + body


def write_messages(messages: list, ppq: int = PLAYBACK_PPQ,
                   tempo_us: int = PLAYBACK_TEMPO_US) -> bytes:
    """A format 0 file that plays (sec, kind, channel, a, b) messages (as from
    scale_times) at exactly those seconds: the player's MIDI-out copy, with the
    tempo factor and the start point already in the times."""
    ticks_per_sec = ppq * MICROSECONDS_PER_SECOND / tempo_us
    events = []
    for sec, kind, ch, a, b in sorted(messages, key=lambda m: m[0]):
        status = PLAYBACK_KIND_STATUS[kind] | (ch & CHANNEL_MASK)
        raw = bytes([status, a]) if kind == "prog" else bytes([status, a, b])
        events.append((int(round(max(0.0, sec) * ticks_per_sec)), raw))
    return _format0(events, ppq, tempo_us)


def all_off_midi() -> bytes:
    """Sustain off, all sound off and all notes off on all 16 channels (Stop)."""
    events = [(0, bytes([CONTROL_CHANGE | ch, cc, 0]))
              for ch in range(MIDI_CHANNEL_COUNT)
              for cc in (CC_SUSTAIN, CC_ALL_SOUND_OFF, CC_ALL_NOTES_OFF)]
    return _format0(events, PLAYBACK_PPQ, PLAYBACK_TEMPO_US)


def moment_to_ticks(moment: Fraction, ppq: int = DEFAULT_PPQ) -> int:
    """A LilyPond moment (whole notes) as ticks."""
    return int(round(moment * QUARTERS_PER_WHOLE * ppq))
