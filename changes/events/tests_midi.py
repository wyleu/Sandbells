"""manage.py ingest_midi: the MIDI byte parser, finding the Pico's ALSA
card, notes -> strokes, and bytes in -> Event rows out (no hardware).
The snd-virmidi test runs only where that kernel module is loaded."""

import errno
import glob
import json
import logging
import os
import re
import select
import shutil
import subprocess
import tempfile
import threading
import time
from unittest import mock, skipUnless

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from . import constants as C
from . import midiingest
from .ingest import Ingest
from .mapping import ChannelMapper
from .midiparse import MidiParser, NoteMessage, parse_seq_line
from .models import Event
from .store import EventStore

ON, OFF = C.MIDI_ON, C.MIDI_OFF
NOTE_ON_CH1, NOTE_OFF_CH1 = 0x90, 0x80     # sandswing: channel 1
TREBLE, TENOR = 65, 53                      # sandswing ring.NOTES[0], [7]
SYSEX = bytes([0xF0, 0x7E, 0x7F, 0x06, 0x01, 0xF7])
CLOCK, ACTIVE_SENSING = 0xF8, 0xFE

# /proc/asound/cards as on the desk Pi with the Pico plugged in
CARDS = """ 0 [vc4hdmi0       ]: vc4-hdmi - vc4-hdmi-0
                      vc4-hdmi-0
 3 [W              ]: USB-Audio - Pico 2 W
                      Raspberry Pi Pico 2 W at usb-xhci-hcd.1-1, full speed
"""

_quiet = {}


def setUpModule():
    for name in (C.LOGGER_NAME, C.LOGGER_NAME + ".midi"):
        log = logging.getLogger(name)
        _quiet[name] = (log.handlers[:], log.propagate)
        log.handlers, log.propagate = [logging.NullHandler()], False


def tearDownModule():
    for name, (h, p) in _quiet.items():
        log = logging.getLogger(name)
        log.handlers, log.propagate = h, p


def on(note, vel=100, ch=1):
    return NoteMessage(ON, ch, note, vel)


def off(note, vel=0, ch=1):
    return NoteMessage(OFF, ch, note, vel)


class TmpDir:
    def tmpdir(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        return d


# ---- the parser -------------------------------------------------------------
class ParserTests(SimpleTestCase):
    def feed(self, *chunks):
        p = MidiParser()
        out = []
        for c in chunks:
            out += p.feed(bytes(c))
        return out, p

    def test_note_on_and_note_off(self):
        out, _ = self.feed([NOTE_ON_CH1, TREBLE, 100, NOTE_OFF_CH1, TREBLE, 0])
        self.assertEqual(out, [on(TREBLE), off(TREBLE)])

    def test_note_on_velocity_zero_is_off(self):
        out, _ = self.feed([NOTE_ON_CH1, TREBLE, 100, NOTE_ON_CH1, TREBLE, 0])
        self.assertEqual(out, [on(TREBLE), NoteMessage(OFF, 1, TREBLE, 0)])

    def test_running_status(self):
        out, _ = self.feed([NOTE_ON_CH1, 65, 100, 64, 100, 65, 0, 62, 90])
        self.assertEqual(out, [on(65), on(64), off(65), on(62, 90)])

    def test_running_status_across_reads_and_split_messages(self):
        out, _ = self.feed([NOTE_ON_CH1], [65], [100, 64], [100])
        self.assertEqual(out, [on(65), on(64)])

    def test_sysex_is_skipped_and_ends_running_status(self):
        out, p = self.feed([NOTE_ON_CH1, 65, 100], SYSEX, [64, 100],
                           [NOTE_ON_CH1, 62, 100])
        self.assertEqual(out, [on(65), on(62)])              # 64,100 after sysex: no status
        self.assertEqual(p.sysex, 1)
        self.assertEqual(p.skipped, 2)

    def test_sysex_split_over_reads_with_note_like_bytes_inside(self):
        out, _ = self.feed([0xF0, 0x7D, NOTE_ON_CH1 & 0x7F, 65], [100, 0xF7],
                           [NOTE_ON_CH1, 57, 100])
        self.assertEqual(out, [on(57)])

    def test_realtime_inside_a_message_keeps_running_status(self):
        out, _ = self.feed([NOTE_ON_CH1, CLOCK, 65, ACTIVE_SENSING, 100, CLOCK, 64, 100])
        self.assertEqual(out, [on(65), on(64)])

    def test_system_common_clears_running_status(self):
        out, _ = self.feed([NOTE_ON_CH1, 65, 100, 0xF2, 0x10, 0x20, 64, 100])
        self.assertEqual(out, [on(65)])

    def test_other_messages_and_channels(self):
        out, _ = self.feed([0xB0, 7, 100, 0xC0, 5, 0x93, 60, 100, 0xE0, 0, 64])
        self.assertEqual(out, [NoteMessage(ON, 4, 60, 100)])   # 0x93: channel 4

    def test_stray_data_and_cut_short_messages_are_dropped(self):
        out, p = self.feed([65, 100, NOTE_ON_CH1, 65, NOTE_ON_CH1, 64, 100])
        self.assertEqual(out, [on(64)])
        self.assertEqual(p.skipped, 3)


class SeqLineTests(SimpleTestCase):
    def test_aseqdump_lines(self):
        self.assertEqual(parse_seq_line(" 28:0   Note on                 0, note 65, velocity 100"),
                         on(65))
        self.assertEqual(parse_seq_line(" 28:0   Note off                0, note 65, velocity 0"),
                         off(65))
        self.assertEqual(parse_seq_line(b" 28:0   Note on                 3, note 60, velocity 0"),
                         NoteMessage(OFF, 4, 60, 0))
        self.assertEqual(parse_seq_line(" 28:0   Note off                0, note 53"), off(53))
        for line in ("Waiting for data. Press Ctrl+C to end.", "Source  Event  Ch  Data",
                     " 28:0   Control change          0, controller 7, value 100", ""):
            self.assertIsNone(parse_seq_line(line))


# ---- finding the Pico ---------------------------------------------------------
class FindPortTests(SimpleTestCase, TmpDir):
    def proc(self, cards=CARDS, midi=((3, 0, "Pico 2 W\n\nInput 0\n"),)):
        d = self.tmpdir()
        with open(os.path.join(d, "cards"), "w") as f:
            f.write(cards)
        for card, dev, text in midi:
            os.makedirs(os.path.join(d, "card%d" % card), exist_ok=True)
            with open(os.path.join(d, "card%d" % card, "midi%d" % dev), "w") as f:
                f.write(text)
        return dict(cards_path=os.path.join(d, "cards"),
                    card_dir=os.path.join(d, "card%d"))

    def test_finds_the_pico_2_w_card(self):
        p = midiingest.find_port(**self.proc())
        self.assertEqual(p, midiingest.Port(3, "Pico 2 W", "/dev/snd/midiC3D0"))

    def test_circuitpython_in_the_midi_file_is_enough(self):
        cards = " 1 [Board ]: USB-Audio - Some Board\n            Adafruit Some Board at usb\n"
        p = midiingest.find_port(**self.proc(cards, ((1, 0, "CircuitPython usb_midi\n"),)))
        self.assertEqual((p.card, p.device), (1, "/dev/snd/midiC1D0"))

    def test_no_card_no_port(self):
        self.assertIsNone(midiingest.find_port(**self.proc(CARDS.split(" 3 [")[0], ())))
        self.assertIsNone(midiingest.find_port(cards_path="/nonexistent/cards"))

    def test_a_matching_card_without_midi_is_not_it(self):
        self.assertIsNone(midiingest.find_port(**self.proc(midi=())))

    def test_card_override(self):
        kw = self.proc()
        self.assertIsNone(midiingest.find_port(match=("Zynthian",), **kw))
        self.assertEqual(midiingest.find_port(match=("usb-xhci",), **kw).card, 3)

    def test_device_override(self):
        d = self.tmpdir()
        dev = os.path.join(d, "midiC3D0")
        self.assertIsNone(midiingest.find_port(device=dev))          # not there (unplugged)
        open(dev, "w").close()
        p = midiingest.find_port(device=dev, **self.proc())
        self.assertEqual(p, midiingest.Port(3, "Pico 2 W", dev))


class OpenSourceTests(SimpleTestCase):
    PORT = midiingest.Port(3, "Pico 2 W", "/dev/snd/midiC3D0")

    def test_busy_raw_device_falls_back_to_the_sequencer(self):
        busy = OSError(errno.EBUSY, "Device or resource busy")
        with mock.patch("events.midiingest.RawSource", side_effect=busy), \
                mock.patch("events.midiingest.SeqSource", return_value="seq") as seq:
            got = midiingest.open_source(self.PORT, which=lambda n: "/usr/bin/" + n)
            self.assertEqual(got, "seq")
            seq.assert_called_once_with("Pico 2 W")
            with self.assertRaises(OSError):                  # raw only: the error
                midiingest.open_source(self.PORT, C.MIDI_TRANSPORT_RAW)
            with self.assertRaises(OSError):                  # no aseqdump: the error
                midiingest.open_source(self.PORT, which=lambda n: None)

    def test_other_open_errors_are_not_hidden(self):
        with mock.patch("events.midiingest.RawSource",
                        side_effect=OSError(errno.EACCES, "Permission denied")):
            with self.assertRaises(OSError):
                midiingest.open_source(self.PORT, which=lambda n: "/usr/bin/" + n)

    def test_seq_source_reads_aseqdump_lines(self):
        out = ("Waiting for data. Press Ctrl+C to end.\\n"
               " 28:0   Note on                 0, note 65, velocity 100\\n"
               " 28:0   Note off                0, note 65, velocity 0\\n")
        seen = {}

        def popen(cmd, **kw):
            seen["cmd"] = cmd
            return subprocess.Popen(["printf", out], **kw)

        s = midiingest.SeqSource("Pico 2 W", popen=popen, which=lambda n: None)
        self.assertEqual(seen["cmd"], ["aseqdump", "-p", "Pico 2 W"])
        got = []
        try:
            with self.assertRaises(midiingest.Disconnected):    # printf ends: "unplugged"
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    select.select([s], [], [], 0.5)
                    got += s.read()
        finally:
            s.close()
        self.assertEqual(got, [on(65), off(65)])


# ---- notes -> strokes ----------------------------------------------------------
class StrokeMakerTests(SimpleTestCase):
    def test_which_notes_are_strokes(self):
        m = midiingest.StrokeMaker()
        self.assertIsNone(m.why_not(on(TREBLE)))
        self.assertEqual(m.why_not(off(TREBLE)), "note_offs")
        self.assertEqual(m.why_not(on(TREBLE, ch=4)), "other_channel")
        self.assertEqual(m.why_not(on(66)), "unmapped")
        self.assertIsNone(midiingest.StrokeMaker(channel=0).why_not(on(TREBLE, ch=4)))

    def test_the_event_is_a_sand_event_stroke(self):
        m = midiingest.StrokeMaker(boot_id="midi0001")
        doc = json.loads(m.event(on(TENOR, 100), 1792578276496, 1234))
        self.assertEqual(doc, {
            "schema": C.SCHEMA_EVENT_V1, "type": C.TYPE_STROKE, "src": C.MIDI_SRC,
            "id": C.MIDI_DEVICE_ID, "boot_id": "midi0001", "seq": 1,
            "tick_ms": 1234, "utc_ms": 1792578276496,
            "body": {"ch": 8, "note": TENOR, "vel": 100, "via": C.MIDI_SRC}})

    def test_mapping_is_sandswings_notes(self):
        self.assertEqual([n for n, ch in sorted(C.MIDI_NOTE_TO_CH.items(), key=lambda i: i[1])],
                         [65, 64, 62, 60, 58, 57, 55, 53])

    def test_midi_strokes_use_the_picos_channel_map(self):
        mapper = ChannelMapper([(C.DEFAULT_SRC, 1, 1, 0), (C.DEFAULT_SRC, 8, 6, 0),
                                (C.MIDI_SRC, 8, 7, 0)])
        self.assertEqual(mapper.bell_for(C.MIDI_SRC, 1, None), 1)     # sandswing's row
        self.assertEqual(mapper.bell_for(C.MIDI_SRC, 8, None), 7)     # its own row wins
        self.assertIsNone(mapper.bell_for(C.MIDI_SRC, 2, None))
        self.assertIsNone(mapper.bell_for("other", 1, None))


# ---- end to end: bytes in, Event rows out ---------------------------------------
class Pipes:
    """Each open() is a fresh pipe whose bytes are given now; its writer is
    closed, so the reader sees EOF after them (an unplug)."""
    def __init__(self, *payloads):
        self.payloads, self.opened = list(payloads), 0

    def __call__(self, port, transport):
        if not self.payloads:
            raise OSError(errno.ENOENT, "No such file or directory")
        r, w = os.pipe()
        os.write(w, bytes(self.payloads.pop(0)))
        os.close(w)
        self.opened += 1
        return midiingest.RawSource(port.device, fd=r)


class EndToEndTests(TestCase, TmpDir):
    PORT = midiingest.Port(3, "Pico 2 W", "/dev/snd/midiC3D0")

    def run_midi(self, *payloads, once=False, finds=None):
        path = os.path.join(self.tmpdir(), "midi_status.json")
        status = midiingest.MidiStatus(path)
        ingest = Ingest(EventStore(), status=status)
        stop = threading.Event()
        opener = Pipes(*payloads)
        finds = list(finds if finds is not None else [self.PORT] * len(payloads))

        def find():
            if finds:
                return finds.pop(0)
            stop.set()
            return None

        wall = iter(range(10 ** 6)).__next__
        maker = midiingest.StrokeMaker(boot_id="midi0001")
        with mock.patch("events.midiingest.time.time", side_effect=lambda: 1792578276.0 + wall()):
            midiingest.run(ingest, stop, status, find=find, opener=opener, maker=maker,
                           reconnect_s=0.01, idle_s=0.01, once=once)
        status.stopped(ingest)
        with open(path) as f:
            return json.load(f), opener

    def test_bytes_to_event_rows(self):
        data = ([NOTE_ON_CH1, 65, 100, CLOCK, 65, 0, 64, 100] + list(SYSEX)
                + [NOTE_ON_CH1, 53, 100, NOTE_OFF_CH1, 53, 0, 0x93, 60, 100,
                   NOTE_ON_CH1, 66, 100])
        doc, _ = self.run_midi(data, once=True)
        rows = list(Event.objects.filter(src=C.MIDI_SRC).order_by("seq"))
        self.assertEqual([(e.seq, e.type, e.ch, e.body["note"]) for e in rows],
                         [(1, "stroke", 1, 65), (2, "stroke", 2, 64), (3, "stroke", 8, 53)])
        self.assertTrue(all(e.boot_id == "midi0001" and e.device_id == C.MIDI_DEVICE_ID
                            and e.body["via"] == "midi" for e in rows))
        self.assertTrue(all(e.utc_ms // C.MS_PER_S >= 1792578276 for e in rows))  # host clock
        ingest_notes = Event.objects.filter(src=C.INGEST_SRC, type=C.TYPE_INGEST)
        self.assertEqual(sorted(e.body["what"] for e in ingest_notes), ["connected", "disconnected"])
        m = doc["midi"]
        self.assertEqual(doc["mode"], C.INGEST_MODE_MIDI)
        self.assertEqual(doc["state"], C.INGEST_STATE_STOPPED)
        self.assertEqual(m["port"], "midi:/dev/snd/midiC3D0")
        self.assertFalse(m["connected"])
        self.assertEqual((m["notes_received"], m["strokes"], m["note_offs"],
                          m["other_channel"], m["unmapped"]), (7, 3, 2, 1, 1))
        self.assertEqual(m["last_note"], {"kind": ON, "channel": 1, "note": 66, "velocity": 100})
        self.assertIsNotNone(m["last_note_ms"])
        self.assertEqual((m["connects"], m["disconnects"], m["sysex_skipped"]), (1, 1, 1))
        # EOF or the periodic card check may see the unplug first (a slower Pi: the card check)
        self.assertRegex(m["recent_errors"][-1]["error"], "end of file|card gone")
        self.assertEqual(doc["counters"]["written"], 5)           # 3 strokes + 2 ingest notes

    def test_unplug_waits_and_reconnects(self):
        doc, opener = self.run_midi([NOTE_ON_CH1, 65, 100], [NOTE_ON_CH1, 64, 100],
                                    finds=[self.PORT, None, self.PORT])
        self.assertEqual(opener.opened, 2)
        self.assertEqual(list(Event.objects.filter(src=C.MIDI_SRC).values_list("seq", "ch")),
                         [(1, 1), (2, 2)])                         # one run, one boot: seq goes on
        self.assertEqual((doc["midi"]["connects"], doc["midi"]["disconnects"]), (2, 2))

    def test_an_open_error_is_counted_and_retried(self):
        doc, _ = self.run_midi(finds=[self.PORT, self.PORT])
        self.assertEqual(doc["midi"]["errors"], 2)
        self.assertIn("No such file", doc["midi"]["recent_errors"][0]["error"])
        self.assertFalse(Event.objects.filter(src=C.MIDI_SRC).exists())


    def test_the_strokes_api_shows_them_with_the_picos_bells(self):
        from datetime import datetime, timezone as tz
        from django.urls import reverse
        from .models import ChannelMap
        ChannelMap.objects.create(src=C.DEFAULT_SRC, ch=1, bell=3,
                                  valid_from=datetime(2026, 1, 1, tzinfo=tz.utc))
        self.run_midi([NOTE_ON_CH1, 65, 100, 64, 100], once=True)
        r = self.client.get(reverse("events:api_since"), {"type": C.TYPE_STROKE})
        ev = r.json()["events"]
        self.assertEqual([(e["src"], e["ch"], e["bell"]) for e in ev],
                         [(C.MIDI_SRC, 1, 3), (C.MIDI_SRC, 2, None)])


class IngestMidiCommandTests(TestCase, TmpDir):
    def test_device_override_once_reads_the_file_and_stores_strokes(self):
        d = self.tmpdir()
        dev, status_path = os.path.join(d, "midiC9D0"), os.path.join(d, "midi_status.json")
        with open(dev, "wb") as f:
            f.write(bytes([NOTE_ON_CH1, 62, 100, 62, 0, 60, 100]))
        with mock.patch.dict(os.environ, {C.MIDI_STATUS_ENV: status_path}), \
                mock.patch("events.management.commands.ingest_midi.setup_logging",
                           return_value=logging.getLogger(C.LOGGER_NAME)):
            call_command("ingest_midi", device=dev, transport=C.MIDI_TRANSPORT_RAW, once=True)
        self.assertEqual(list(Event.objects.filter(src=C.MIDI_SRC).order_by("seq")
                              .values_list("ch", flat=True)), [3, 4])
        with open(status_path) as f:
            doc = json.load(f)
        self.assertEqual(doc["state"], C.INGEST_STATE_STOPPED)
        self.assertEqual(doc["midi"]["strokes"], 2)
        self.assertEqual(doc["midi"]["port"], "midi:" + dev)


# ---- the real kernel path: snd-virmidi --------------------------------------------
def _virmidi():
    """(write device, read device, seq clients) of a loaded snd-virmidi, or None."""
    for num, text, _ in midiingest.read_cards():
        if "VirMIDI" in text or "Virtual" in text:
            devs = sorted(glob.glob("/dev/snd/midiC%dD*" % num))
            if len(devs) >= 2 and shutil.which("aconnect"):
                return num, devs
    return None


VIRMIDI = _virmidi()


@skipUnless(VIRMIDI, "snd-virmidi not loaded (sudo modprobe snd-virmidi) or no aconnect")
class VirmidiTests(TestCase):
    """Bytes written to virmidi device 0 go out on its seq port; aconnect
    routes that to device 1's seq port, whose rawmidi input we read."""

    def test_kernel_rawmidi_round_trip(self):
        num, devs = VIRMIDI
        listing = subprocess.run(["aconnect", "-l"], capture_output=True, text=True).stdout
        clients = re.findall(r"client (\d+): 'Virtual Raw MIDI %d-(\d+)'" % num, listing)
        clients = {int(dev): int(cl) for cl, dev in clients}
        a, b = "%d:0" % clients[0], "%d:0" % clients[1]
        subprocess.run(["aconnect", a, b], check=True)
        self.addCleanup(subprocess.run, ["aconnect", "-d", a, b])
        src = midiingest.RawSource(devs[1])
        self.addCleanup(src.close)
        with open(devs[0], "wb", buffering=0) as w:
            w.write(bytes([NOTE_ON_CH1, 65, 100, 64, 100]))
        got, deadline = [], time.monotonic() + 3
        while len(got) < 2 and time.monotonic() < deadline:
            if select.select([src], [], [], 0.2)[0]:
                got += src.read()
        self.assertEqual(got, [on(65), on(64)])
