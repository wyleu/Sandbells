"""Chimes Play: MIDI reading and timing, note maps (chime-build's), the 8-bell
check, the player's process handling (fake fluidsynth, mocked kills), the
player views, the MIDI / note-map fields and bundle loading."""

import io
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command, CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from bells import chime_driver, chime_midi, chime_notemap, chime_player
from bells import chimes as chime_files
from bells.admin import ChimeTuneForm
from bells.management.commands.chime_load import SAMPLE_FILE
from bells.models import ChimeTune
from bells.tests_chimes import ChimesRootMixin, HAVE_POPPLER, NEEDS_POPPLER, png_bytes

SAMPLES = SAMPLE_FILE.parent
SAMPLE_MIDI = SAMPLES / "boars-head-carol.midi"
SAMPLE_NOTEMAP = SAMPLES / "boars-head-carol.notemap.json"
SMALL = 200
PPQ = chime_midi.DEFAULT_PPQ
BPM_60 = 60
BPM_120 = 120
F4, C5, F5, G5, C3 = 65, 72, 77, 79, 48
LOCAL = "127.0.0.1"
PUBLIC = "8.8.8.8"
needs_poppler = unittest.skipUnless(HAVE_POPPLER, NEEDS_POPPLER)


def quarter(n):
    return n * PPQ


def small_midi(pitches=(C5, F5, F4), bpm=BPM_60):
    """One quarter note each, in a row."""
    return chime_midi.write_midi(
        [(quarter(i), quarter(i + 1), p) for i, p in enumerate(pitches)], bpm=bpm)


TSV_HEAD = "\t".join(chime_notemap.TSV_COLUMNS + (chime_notemap.TSV_TIED,))


def tsv_row(page, x, y, moment, bar, bar_pos, midi, pitch="3:0:1", staff="bells",
            length="1/4", paper=(100.0, 50.0)):
    """A row without its tied column (the caller adds it, or the reader takes 0)."""
    half = 0.5
    return "\t".join(str(v) for v in (
        page, paper[0], paper[1], x - half, x + half, -y - half, -y + half,
        moment, bar, bar_pos, midi, pitch, staff, length))


class ChimeMidiTests(TestCase):
    def test_round_trip_and_times_at_the_written_tempo(self):
        mf = chime_midi.read_midi(small_midi(bpm=BPM_120))
        notes = chime_midi.notes(mf)
        self.assertEqual([n.pitch for n in notes], [C5, F5, F4])
        self.assertEqual([n.sec for n in notes], [0.0, 0.5, 1.0])
        self.assertEqual(chime_midi.TempoMap(mf).first_bpm(), BPM_120)

    def test_tempo_change_mid_file(self):
        body = small_midi(bpm=BPM_60)
        mf = chime_midi.read_midi(body)
        mf.tracks[0].append(chime_midi.MidiEvent(
            quarter(1), chime_midi.META, meta_type=chime_midi.META_TEMPO,
            meta=(chime_midi.DEFAULT_TEMPO_US // 2).to_bytes(3, "big")))
        tm = chime_midi.TempoMap(mf)
        self.assertAlmostEqual(tm.seconds(quarter(1)), 1.0)
        self.assertAlmostEqual(tm.seconds(quarter(3)), 1.5)   # 240 bpm after beat 1

    def test_chords_group_by_tick(self):
        mf = chime_midi.read_midi(chime_midi.write_midi(
            [(0, quarter(1), F5), (0, quarter(1), F4), (quarter(1), quarter(2), C5)]))
        self.assertEqual([c[2] for c in chime_midi.chords(chime_midi.notes(mf))],
                         [(F4, F5), (C5,)])

    def test_scale_times_divides_by_the_factor_and_starts_where_asked(self):
        msgs = chime_midi.playback_messages(chime_midi.read_midi(small_midi()))
        fast = chime_midi.scale_times(msgs, 2.0)
        ons = [m for m in fast if m[1] == "on"]
        self.assertEqual([m[0] for m in ons], [0.0, 0.5, 1.0])
        later = [m for m in chime_midi.scale_times(msgs, 1.0, from_sec=1.0) if m[1] == "on"]
        self.assertEqual([(m[0], m[3]) for m in later], [(0.0, F5), (1.0, F4)])
        with self.assertRaises(ValueError):
            chime_midi.scale_times(msgs, 0)

    def test_program_changes_only_when_asked(self):
        mf = chime_midi.read_midi(small_midi())
        mf.tracks[0].insert(0, chime_midi.MidiEvent(0, chime_midi.PROGRAM_CHANGE, 0, (52,)))
        self.assertFalse([m for m in chime_midi.playback_messages(mf) if m[1] == "prog"])
        self.assertTrue([m for m in chime_midi.playback_messages(mf, program_changes=True)
                         if m[1] == "prog"])

    def test_garbage_is_refused(self):
        with self.assertRaises(chime_midi.MidiError):
            chime_midi.read_midi(b"not midi at all")

    def test_pitch_names(self):
        self.assertEqual(chime_midi.pitch_name(70), "Bb4")
        self.assertEqual(chime_midi.pitch_name(F5), "F5")

    def test_the_sample_midi_from_lilypond(self):
        mf = chime_midi.read_midi(SAMPLE_MIDI.read_bytes())
        self.assertEqual(mf.ppq, PPQ)
        self.assertTrue(all(n.pitch in chime_notemap.BELLS_8 for n in chime_midi.notes(mf)))


class ChimeNotemapTests(TestCase):
    def heads(self):
        rows = [TSV_HEAD,
                tsv_row(1, 10, 5, "0/1", 1, "0/1", C5, "0:0:1"),
                tsv_row(1, 20, 5, "1/4", 1, "1/4", F5, "3:0:1"),
                tsv_row(1, 30, 10, "1/2", 1, "1/2", F4, "3:0:0"),
                tsv_row(2, 10, 5, "3/4", 1, "3/4", G5, "4:0:1")]
        return chime_notemap.parse_heads("\n".join(rows) + "\n")

    def test_parse_heads_gives_page_fractions_from_the_top_left(self):
        h = self.heads()
        self.assertEqual(len(h), 4)
        self.assertAlmostEqual(h[0].fx, 0.1)
        self.assertAlmostEqual(h[0].fy, 0.1)
        self.assertEqual(h[1].moment, Fraction(1, 4))
        self.assertEqual(h[3].name, "G5")

    def test_missing_columns_are_refused(self):
        with self.assertRaises(chime_notemap.NotemapError):
            chime_notemap.parse_heads("page\tx1\n1\t2\n")

    def test_align_follows_a_repeat_back(self):
        printed = [chime_notemap.PrintedChord(Fraction(i), (p,), []) for i, p in
                   enumerate((C5, F5, F4, G5))]
        played = [(i, float(i), (p,)) for i, p in enumerate((C5, F5, F4, C5, F5, F4, G5))]
        self.assertEqual(chime_notemap.align(played, printed), [0, 1, 2, 0, 1, 2, 3])

    def test_tied_to_heads_are_not_matched(self):
        rows = [TSV_HEAD,
                tsv_row(1, 10, 5, "0/1", 1, "0/1", C5) + "\t0",
                tsv_row(1, 20, 5, "1/2", 1, "1/2", C5) + "\t1",      # c2~ c2
                tsv_row(1, 30, 5, "1/1", 2, "0/1", F5) + "\t0"]
        heads = chime_notemap.parse_heads("\n".join(rows) + "\n")
        self.assertTrue(heads[1].tied)
        printed = chime_notemap.printed_chords(heads)
        self.assertEqual([p.moment for p in printed], [Fraction(0), Fraction(1)])
        played = [(0, 0.0, (C5,)), (2, 2.0, (F5,))]
        self.assertEqual(chime_notemap.align(played, printed), [0, 1])

    def test_unknown_chord_is_unplaced(self):
        printed = [chime_notemap.PrintedChord(Fraction(0), (C5,), [])]
        self.assertEqual(chime_notemap.align([(0, 0.0, (G5,))], printed), [None])

    def test_bell_check_is_strict_and_says_where(self):
        problems = chime_notemap.bell_check(self.heads())
        self.assertEqual(len(problems), 1)
        self.assertEqual((problems[0]["bar"], problems[0]["beat"], problems[0]["pitch"]),
                         (1, 4.0, "G5"))
        self.assertIn("bar 1 beat 4: G5 (MIDI 79)", chime_notemap.describe_problem(problems[0]))

    def test_bell_check_also_reads_the_played_notes(self):
        played = chime_midi.notes(chime_midi.read_midi(small_midi((C3,))))
        problems = chime_notemap.bell_check([], played)
        self.assertEqual(problems[0]["pitch"], "C3")
        self.assertIsNone(problems[0]["bar"])

    def test_the_eight_bells_are_f_major_f5_down_to_f4(self):
        self.assertEqual([chime_midi.pitch_name(p) for p in chime_notemap.BELLS_8],
                         ["F5", "E5", "D5", "C5", "Bb4", "A4", "G4", "F4"])
        self.assertEqual(chime_notemap.BELL_NUMBER[F5], 1)
        self.assertEqual(chime_notemap.BELL_NUMBER[F4], 8)

    def test_build_places_each_played_chord(self):
        heads = self.heads()
        mf = chime_midi.read_midi(small_midi((C5, F5, F4, G5)))
        data = chime_notemap.build(heads, mf, title="T")
        self.assertEqual([(e["page"], round(e["fx"], 2)) for e in data["events"]],
                         [(1, 0.1), (1, 0.2), (1, 0.3), (2, 0.1)])
        self.assertEqual(data["unplaced"], 0)
        self.assertEqual(len(data["out_of_set"]), 1)
        chime_notemap.load(json.dumps(data))                 # its own output loads

    def test_load_refuses_bad_maps(self):
        for text in ("nope", "{}", json.dumps({"format": chime_notemap.NOTEMAP_FORMAT}),
                     json.dumps({"format": chime_notemap.NOTEMAP_FORMAT,
                                 "events": [{"sec": 1}, {"sec": 0}]}),
                     json.dumps({"format": chime_notemap.NOTEMAP_FORMAT,
                                 "events": [{"sec": 0, "page": 1, "fx": 2, "fy": 0}]})):
            with self.assertRaises(chime_notemap.NotemapError):
                chime_notemap.load(text)

    def test_the_sample_note_map(self):
        data = chime_notemap.load(SAMPLE_NOTEMAP.read_text())
        self.assertEqual(data["out_of_set"], [])
        self.assertEqual(data["unplaced"], 0)
        self.assertTrue(all(e["page"] == 1 for e in data["events"]))

    def test_event_at(self):
        events = [{"sec": 0.0}, {"sec": 1.0}, {"sec": 2.0}]
        self.assertEqual(chime_notemap.event_at(events, -0.5), -1)
        self.assertEqual(chime_notemap.event_at(events, 1.0), 1)
        self.assertEqual(chime_notemap.event_at(events, 9), 2)


FAKE_FLUIDSYNTH = """#!%s
import os, sys
log = open(os.environ["FAKE_FS_LOG"], "a")
log.write("ARGS " + repr(sys.argv[1:]) + "\\n"); log.flush()
for line in sys.stdin:
    log.write(line); log.flush()
    if line.strip() == "fonts":
        sys.stdout.write("ID  Name\\n 1  font.sf2\\n"); sys.stdout.flush()
    if line.strip() == "quit":
        break
"""
DEAD_FLUIDSYNTH = "#!/bin/sh\nexit 1\n"
APLAYMIDI_LIST = """ Port    Client name                      Port name
 14:0    Midi Through                     Midi Through Port-0
 20:0    Roland SC-8820                   Roland SC-8820 MIDI 1
 24:0    Pico 2 W                         Pico 2 W MIDI 1
"""
# aplaymidi -l when sandbells-qmidinet is running (typical client/port names).
PORT_QMIDINET = "128:0"
APLAYMIDI_LIST_QMIDINET = """ Port    Client name                      Port name
 14:0    Midi Through                     Midi Through Port-0
 24:0    Pico 2 W                         Pico 2 W MIDI 1
 128:0   QmidiNet                         Network 1
"""
FAKE_APLAYMIDI = """#!%s
import os, shutil, sys, time
log = open(os.environ["FAKE_AP_LOG"], "a")
log.write("ARGS " + repr(sys.argv[1:]) + "\\n"); log.flush()
if sys.argv[1:] == ["-l"]:
    sys.stdout.write(os.environ.get("FAKE_AP_LIST", "")); sys.exit(0)
if sys.argv[1] == "-p":
    n = len([f for f in os.listdir(os.environ["FAKE_AP_DIR"]) if f.startswith("sent")])
    shutil.copy(sys.argv[3], os.path.join(os.environ["FAKE_AP_DIR"], "sent%%d.mid" %% n))
    sys.exit(int(os.environ.get("FAKE_AP_EXIT", "0")))
"""
PORT_ROLAND, PORT_THROUGH, PORT_PICO = "20:0", "14:0", "24:0"


class FakeFluidsynthMixin:
    """A fake fluidsynth (logs its stdin shell) and a fake aplaymidi (lists
    APLAYMIDI_LIST, keeps each file it is asked to play)."""

    def setUp(self):
        super().setUp()
        self.tmp = Path(tempfile.mkdtemp(prefix="chime-play-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.fs = self.tmp / "fluidsynth"
        self.fs.write_text(FAKE_FLUIDSYNTH % sys.executable)
        self.fs.chmod(self.fs.stat().st_mode | stat.S_IEXEC)
        self.ap = self.tmp / "aplaymidi"
        self.ap.write_text(FAKE_APLAYMIDI % sys.executable)
        self.ap.chmod(self.ap.stat().st_mode | stat.S_IEXEC)
        self.sent = self.tmp / "sent"
        self.sent.mkdir()
        self.log = self.tmp / "fs.log"
        self.ap_log = self.tmp / "ap.log"
        patcher = mock.patch.dict(os.environ, {
            "FAKE_FS_LOG": str(self.log), "FAKE_AP_LOG": str(self.ap_log),
            "FAKE_AP_DIR": str(self.sent), "FAKE_AP_LIST": APLAYMIDI_LIST})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.font = self.tmp / "Sandbach Bells_n_12.sf2"     # a space in the name
        self.font.write_bytes(b"sf2")
        self.midi = self.tmp / "t.midi"
        self.midi.write_bytes(small_midi(bpm=BPM_120))
        self.state = self.tmp / "state.json"

    def args(self, **kw):
        a = dict(midi=str(self.midi), state=str(self.state), soundfont=str(self.font),
                 fluidsynth=str(self.fs), aplaymidi=str(self.ap), midi_port="", hdmi=True,
                 audio_driver="alsa", audio_device=chime_player.DEFAULT_HDMI_DEVICE,
                 gain=0.5, factor=2.0, from_sec=0.0, slug="t", title="T",
                 program_changes=False, daemon=False)
        a.update(kw)
        return SimpleNamespace(**a)

    def sent_files(self):
        return sorted(self.sent.iterdir(), key=lambda p: int(p.stem[len("sent"):]))

    def ap_calls(self):
        if not self.ap_log.exists():
            return []
        return [eval(l[len("ARGS "):]) for l in self.ap_log.read_text().splitlines()]


def sounded(midi_bytes):
    """(sec, pitch) of every note on in a MIDI file."""
    return [(round(n.sec, 3), n.pitch) for n in chime_midi.notes(chime_midi.read_midi(midi_bytes))]


class ChimeMidiOutFileTests(TestCase):
    def test_write_messages_plays_at_the_given_seconds(self):
        msgs = [(0.0, "prog", 0, 14, 0), (0.0, "on", 0, C5, 90), (0.25, "off", 0, C5, 0),
                (1.5, "on", 3, F4, 80), (2.0, "off", 3, F4, 0)]
        mf = chime_midi.read_midi(chime_midi.write_messages(msgs))
        self.assertEqual(sounded(chime_midi.write_messages(msgs)), [(0.0, C5), (1.5, F4)])
        progs = [e for e in mf.events() if e.status == chime_midi.PROGRAM_CHANGE]
        self.assertEqual([(p.channel, p.data) for p in progs], [(0, (14,))])

    def test_all_off_covers_every_channel(self):
        mf = chime_midi.read_midi(chime_midi.all_off_midi())
        ccs = {(e.channel, e.data[0]) for e in mf.events()
               if e.status == chime_midi.CONTROL_CHANGE}
        for ch in range(chime_midi.MIDI_CHANNEL_COUNT):
            self.assertIn((ch, chime_midi.CC_ALL_NOTES_OFF), ccs)
            self.assertIn((ch, chime_midi.CC_ALL_SOUND_OFF), ccs)


class ChimeDriverTests(FakeFluidsynthMixin, TestCase):
    def test_fluidsynth_has_no_midi_input_and_the_soundfont_is_one_argument(self):
        cmd = chime_driver.fluidsynth_command(self.args())
        self.assertIn("-n", cmd)                      # never opens a MIDI port (Pico)
        self.assertIn("audio.alsa.device=" + chime_player.DEFAULT_HDMI_DEVICE, cmd)
        self.assertEqual(cmd[-1], str(self.font))
        self.assertNotIn("-i", cmd)

    def test_hdmi_plays_every_note_through_the_shell_then_quits(self):
        chime_driver.play(self.args(), sleep=lambda s: None)
        lines = self.log.read_text().splitlines()
        self.assertEqual(lines[1], "fonts")
        self.assertEqual([l for l in lines if l.startswith("noteon")],
                         ["noteon 0 %d %d" % (p, chime_midi.DEFAULT_VELOCITY)
                          for p in (C5, F5, F4)])
        self.assertEqual(lines[-1], "quit")
        self.assertEqual(self.ap_calls(), [])          # MIDI out off
        state = json.loads(self.state.read_text())
        self.assertFalse(state["playing"])
        self.assertEqual(state["phase"], "finished")
        self.assertEqual(state["tempo_factor"], 2.0)
        self.assertEqual(state["outputs"], {"midi_out": False, "midi_port": "",
                                            "hdmi_audio": True})
        self.assertIsNotNone(state["started_at"])

    def test_midi_out_plays_a_tempo_scaled_copy_to_the_port(self):
        chime_driver.play(self.args(hdmi=False, midi_port=PORT_ROLAND, factor=2.0,
                                    from_sec=0.5), sleep=lambda s: None)
        self.assertFalse(self.log.exists())            # no fluidsynth
        (call,) = self.ap_calls()
        self.assertEqual(call[:2], ["-p", PORT_ROLAND])
        # 120 bpm: notes at 0, 0.5, 1.0 s; from 0.5 s at x2 -> 0 and 0.25 s
        self.assertEqual(sounded(self.sent_files()[0].read_bytes()), [(0.0, F5), (0.25, F4)])
        state = json.loads(self.state.read_text())
        self.assertEqual(state["phase"], "finished")
        self.assertEqual(state["outputs"]["midi_port"], PORT_ROLAND)

    def test_both_outputs_together(self):
        chime_driver.play(self.args(midi_port=PORT_ROLAND), sleep=lambda s: None)
        self.assertEqual(len(self.ap_calls()), 1)
        self.assertIn("quit", self.log.read_text())

    def test_neither_output_still_keeps_time_for_the_dot(self):
        sleeps = []
        fixed = [0.0]
        chime_driver.play(self.args(hdmi=False, midi_port="", factor=1.0),
                          sleep=lambda s: (sleeps.append(s), fixed.__setitem__(0, fixed[0] + s)),
                          clock=lambda: fixed[0])
        self.assertFalse(self.log.exists())
        self.assertEqual(self.ap_calls(), [])
        # 120 bpm: last note off at 1.5 s after the start lead
        self.assertAlmostEqual(fixed[0], chime_driver.START_LEAD_S + 1.5, places=3)
        self.assertEqual(json.loads(self.state.read_text())["phase"], "finished")

    def test_aplaymidi_that_fails_is_an_error_in_the_state(self):
        with mock.patch.dict(os.environ, {"FAKE_AP_EXIT": "1"}):
            with self.assertRaises(RuntimeError):
                chime_driver.play(self.args(hdmi=False, midi_port=PORT_ROLAND),
                                  sleep=lambda s: None)
        state = json.loads(self.state.read_text())
        self.assertEqual(state["phase"], "error")
        self.assertIn("aplaymidi -p %s" % PORT_ROLAND, state["error"])

    def test_tempo_factor_sets_the_gaps(self):
        sleeps = []
        fixed = [0.0]                                      # a clock that only sleep moves

        def fake_clock():
            return fixed[0]

        def fake_sleep(s):
            sleeps.append(round(s, 3))
            fixed[0] += s

        chime_driver.play(self.args(factor=2.0), sleep=fake_sleep, clock=fake_clock)
        # 120 bpm quarters are 0.5 s; at factor 2 the notes are 0.25 s apart
        on_gaps = [s for s in sleeps if s and s != chime_driver.RELEASE_TAIL_S]
        self.assertIn(0.25, on_gaps)

    def test_fluidsynth_that_dies_is_an_error_in_the_state(self):
        self.fs.write_text(DEAD_FLUIDSYNTH)
        with self.assertRaises(RuntimeError):
            chime_driver.play(self.args(), sleep=lambda s: None)
        state = json.loads(self.state.read_text())
        self.assertEqual(state["phase"], "error")
        self.assertIn("did not start", state["error"])


class ChimePortTests(TestCase):
    def test_the_pico_is_never_listed(self):
        ports, left_out = chime_player.parse_ports(APLAYMIDI_LIST)
        self.assertEqual([p["id"] for p in ports], [PORT_THROUGH, PORT_ROLAND])
        self.assertEqual(left_out, [PORT_PICO])
        self.assertEqual(ports[1]["client"], "Roland SC-8820")

    def test_qmidinet_is_listed_and_the_pico_is_still_left_out(self):
        ports, left_out = chime_player.parse_ports(APLAYMIDI_LIST_QMIDINET)
        self.assertEqual([p["id"] for p in ports], [PORT_THROUGH, PORT_QMIDINET])
        self.assertEqual(left_out, [PORT_PICO])
        self.assertEqual(ports[1]["client"], chime_player.QMIDINET_CLIENT_NAME)
        self.assertEqual(ports[1]["name"], "Network 1")
        self.assertEqual(chime_player.pick_port("", ports), PORT_QMIDINET)
        self.assertEqual(chime_player.pick_port("QmidiNet", ports), PORT_QMIDINET)
        self.assertEqual(chime_player.pick_port("network 1", ports), PORT_QMIDINET)
        with self.assertRaisesRegex(chime_player.PlayerError, "Pico"):
            chime_player.pick_port("Pico 2 W", ports, left_out=left_out)
        with self.assertRaisesRegex(chime_player.PlayerError, "Pico"):
            chime_player.pick_port(PORT_PICO, ports, left_out=left_out)

    def test_circuitpython_and_extra_names_are_left_out_too(self):
        text = APLAYMIDI_LIST + " 28:0    CircuitPython usb_midi.ports[0]  CircuitPython MIDI 1\n"
        ports, left_out = chime_player.parse_ports(
            text, chime_player.EXCLUDED_PORT_NAMES + ("roland",))
        self.assertEqual([p["id"] for p in ports], [PORT_THROUGH])
        self.assertEqual(sorted(left_out), [PORT_ROLAND, PORT_PICO, "28:0"])

    def test_pick_port(self):
        ports, left_out = chime_player.parse_ports(APLAYMIDI_LIST)
        self.assertEqual(chime_player.pick_port("", ports), PORT_ROLAND)   # not Midi Through
        self.assertEqual(chime_player.pick_port("", ports[:1]), PORT_THROUGH)
        self.assertEqual(chime_player.pick_port("roland", ports), PORT_ROLAND)
        self.assertEqual(chime_player.pick_port(PORT_THROUGH, ports), PORT_THROUGH)
        for pico in ("Pico 2 W", PORT_PICO):
            with self.assertRaisesRegex(chime_player.PlayerError, "Pico"):
                chime_player.pick_port(pico, ports, left_out=left_out)
        with self.assertRaisesRegex(chime_player.PlayerError, "not there"):
            chime_player.pick_port("99:0", ports)
        with self.assertRaisesRegex(chime_player.PlayerError, "no MIDI port"):
            chime_player.pick_port("", [])


@override_settings()
class ChimePlayerTests(ChimesRootMixin, FakeFluidsynthMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.js = {"soundfont": str(self.font), "fluidsynth": str(self.fs),
                   "aplaymidi": str(self.ap)}
        cfg = mock.patch("bells.chime_player._json_settings", side_effect=lambda: self.js)
        cfg.start()
        self.addCleanup(cfg.stop)
        self.tune = ChimeTune.objects.create(
            title="Tune", source=SimpleUploadedFile("t.png", png_bytes(SMALL, SMALL)),
            midi=SimpleUploadedFile("t.midi", small_midi()))
        self.addCleanup(chime_player.stop)

    def test_config_defaults(self):
        with mock.patch("bells.chime_player._json_settings", return_value={}):
            eight = self.tmp / "sandbach_bells_8.sf2"
            gm = self.tmp / "FluidR3_GM.sf2"
            gm.write_bytes(b"")
            with mock.patch.object(chime_player, "DEFAULT_SOUNDFONTS", (eight, gm)):
                self.assertEqual(chime_player.player_config()["soundfont"], str(gm))
                eight.write_bytes(b"")
                cfg = chime_player.player_config()
                self.assertEqual(cfg["soundfont"], str(eight))
            self.assertEqual(cfg["audio_device"], "hdmi:CARD=vc4hdmi,DEV=0")
            self.assertTrue(cfg["midi_out"])
            self.assertFalse(cfg["hdmi_audio"])
            self.assertEqual(cfg["midi_port"], "")
            self.assertIn("Pico", cfg["midi_exclude"])
            self.assertEqual(chime_player.SOUNDFONT_SANDBACH_8.name, "sandbach_bells_8.sf2")

    def test_settings_block_and_django_settings(self):
        self.js.update(midi_out=False, hdmi_audio=True, hdmi_device="plughw:CARD=b1",
                       midi_port="roland", midi_exclude=["SC-8820"])
        cfg = chime_player.player_config()
        self.assertEqual((cfg["midi_out"], cfg["hdmi_audio"]), (False, True))
        self.assertEqual(cfg["audio_device"], "plughw:CARD=b1")
        self.assertEqual(cfg["midi_port"], "roland")
        self.assertIn("SC-8820", cfg["midi_exclude"])
        self.assertIn("Pico", cfg["midi_exclude"])      # can only add, never drop the Pico
        with override_settings(SANDBELLS_CHIMES_SOUNDFONT="/x/y z.sf2",
                               SANDBELLS_CHIMES_HDMI_DEVICE="hw:9"):
            cfg = chime_player.player_config()
            self.assertEqual(cfg["soundfont"], "/x/y z.sf2")
            self.assertEqual(cfg["audio_device"], "hw:9")

    def test_outputs_row_starts_from_the_settings_and_keeps_changes(self):
        from bells.models import ChimeOutputs
        self.js.update(midi_out=False, hdmi_audio=True)
        self.assertEqual(chime_player.outputs().as_dict(),
                         {"midi_out": False, "midi_port": "", "hdmi_audio": True})
        self.js.update(midi_out=True, hdmi_audio=False)            # only first values
        self.assertFalse(chime_player.outputs().midi_out)
        chime_player.set_outputs(midi_out=True)
        self.assertEqual(ChimeOutputs.objects.get().as_dict(),
                         {"midi_out": True, "midi_port": "", "hdmi_audio": True})
        chime_player.set_outputs(midi_port=PORT_ROLAND, hdmi_audio=False)
        self.assertEqual(chime_player.outputs().as_dict(),
                         {"midi_out": True, "midi_port": PORT_ROLAND, "hdmi_audio": False})
        for pico in ("Pico 2 W", PORT_PICO):
            with self.assertRaisesRegex(chime_player.PlayerError, "Pico"):
                chime_player.set_outputs(midi_port=pico)
        self.assertEqual(chime_player.outputs().midi_port, PORT_ROLAND)
        self.assertEqual(ChimeOutputs.objects.count(), 1)

    def test_list_ports_without_aplaymidi_says_why(self):
        self.js["aplaymidi"] = str(self.tmp / "missing")
        listing = chime_player.list_ports()
        self.assertEqual(listing["ports"], [])
        self.assertIn("aplaymidi -l", listing["error"])

    def test_tempo_percent_is_clamped(self):
        self.assertEqual(chime_player.tempo_factor(chime_player.TEMPO_PERCENT_MAX * 2),
                         chime_player.TEMPO_PERCENT_MAX / chime_player.PERCENT)
        self.assertEqual(chime_player.tempo_factor("junk"), 1.0)

    def test_state_lives_with_the_chimes_files(self):
        self.assertEqual(chime_player.state_path().parent, Path(self.root))

    def driver_cmd(self, *a, **kw):
        listing = chime_player.list_ports()        # the fake aplaymidi, before Popen is mocked
        with mock.patch("bells.chime_player.list_ports", return_value=listing), \
                mock.patch("bells.chime_player._stop_unlocked") as stop, \
                mock.patch("bells.chime_player.subprocess.Popen") as popen:
            out = chime_player.play(self.tune, *a, **kw)
        stop.assert_called_once()
        popen.assert_called_once()
        return popen.call_args[0][0], out

    def test_play_stops_the_old_player_first_and_starts_one_driver(self):
        cmd, out = self.driver_cmd(120)
        self.assertIn(chime_driver.__file__, cmd)
        self.assertEqual(cmd[cmd.index("--factor") + 1], "1.2")
        self.assertEqual(cmd[cmd.index("--midi-port") + 1], PORT_ROLAND)   # auto, not the Pico
        self.assertNotIn("--hdmi", cmd)                                      # default off
        self.assertIn("--daemon", cmd)
        self.assertEqual(out["outputs"], {"midi_out": True, "midi_port": PORT_ROLAND,
                                          "hdmi_audio": False})

    def test_play_follows_the_switches(self):
        chime_player.set_outputs(midi_out=False, hdmi_audio=True)
        cmd, _ = self.driver_cmd()
        self.assertEqual(cmd[cmd.index("--midi-port") + 1], "")
        self.assertIn("--hdmi", cmd)
        self.assertEqual(cmd[cmd.index("--soundfont") + 1], str(self.font))
        self.assertEqual(cmd[cmd.index("--audio-device") + 1], chime_player.DEFAULT_HDMI_DEVICE)
        chime_player.set_outputs(midi_out=False, hdmi_audio=False)       # silent: dot only
        cmd, _ = self.driver_cmd()
        self.assertEqual(cmd[cmd.index("--midi-port") + 1], "")
        self.assertNotIn("--hdmi", cmd)
        chime_player.set_outputs(midi_out=True, midi_port=PORT_THROUGH)
        cmd, _ = self.driver_cmd()
        self.assertEqual(cmd[cmd.index("--midi-port") + 1], PORT_THROUGH)

    def test_play_refuses_the_pico_even_from_the_settings(self):
        self.js["midi_port"] = "Pico 2 W"
        with self.assertRaisesRegex(chime_player.PlayerError, "Pico"):
            chime_player.play(self.tune)
        from bells.models import ChimeOutputs
        ChimeOutputs.objects.filter(pk=1).update(midi_port=PORT_PICO)    # e.g. by hand
        with self.assertRaisesRegex(chime_player.PlayerError, "Pico"):
            chime_player.play(self.tune)

    def test_play_without_midi_or_soundfont_or_ports_says_why(self):
        self.tune.midi = ""
        with self.assertRaises(chime_player.PlayerError):
            chime_player.play(self.tune)
        self.tune.refresh_from_db()
        chime_player.set_outputs(hdmi_audio=True)
        self.font.unlink()
        with self.assertRaisesRegex(chime_player.PlayerError, "soundfont"):
            chime_player.play(self.tune)
        chime_player.set_outputs(hdmi_audio=False)
        self.js["aplaymidi"] = str(self.tmp / "missing")
        with self.assertRaisesRegex(chime_player.PlayerError, "MIDI out"):
            chime_player.play(self.tune)

    def test_stop_kills_the_driver_group_never_our_own(self):
        chime_driver.write_state(chime_player.state_path(),
                                 {"playing": True, "pid": 4242, "pgid": 4242})
        alive = iter([True, False, False])
        with mock.patch("bells.chime_player._driver_alive", side_effect=lambda p: next(alive)), \
                mock.patch("bells.chime_player.os.killpg") as killpg:
            state = chime_player.stop()
        killpg.assert_called_once_with(4242, signal.SIGTERM)
        self.assertFalse(state["playing"])
        chime_driver.write_state(chime_player.state_path(),
                                 {"playing": True, "pid": 4243, "pgid": os.getpgrp()})
        alive = iter([True, False, False])
        with mock.patch("bells.chime_player._driver_alive", side_effect=lambda p: next(alive)), \
                mock.patch("bells.chime_player.os.killpg") as killpg, \
                mock.patch("bells.chime_player.os.kill") as kill:
            chime_player.stop()
        killpg.assert_not_called()
        kill.assert_called_once_with(4243, signal.SIGTERM)

    def test_stop_sends_all_notes_off_to_the_port_it_played_to(self):
        chime_driver.write_state(chime_player.state_path(), {
            "playing": True, "pid": 4242, "pgid": 4242,
            "outputs": {"midi_out": True, "midi_port": PORT_ROLAND, "hdmi_audio": False}})
        alive = iter([True, False, False])
        with mock.patch("bells.chime_player._driver_alive", side_effect=lambda p: next(alive)), \
                mock.patch("bells.chime_player.os.killpg"):
            chime_player.stop()
        (call,) = self.ap_calls()
        self.assertEqual(call[:2], ["-p", PORT_ROLAND])
        self.assertEqual(self.sent_files()[0].read_bytes(), chime_midi.all_off_midi())

    def test_all_off_never_goes_to_the_pico(self):
        chime_player.send_all_off("Pico 2 W")
        self.assertEqual(self.ap_calls(), [])

    def test_a_dead_driver_reads_as_stopped(self):
        chime_driver.write_state(chime_player.state_path(),
                                 {"playing": True, "pid": 999999, "phase": "playing"})
        self.assertFalse(chime_player.read_state()["playing"])

    def test_a_reused_pid_is_not_our_driver(self):
        self.assertFalse(chime_player._driver_alive(os.getpid()))   # the test runner

    def test_status_works_out_the_event_and_has_the_switches(self):
        chime_driver.write_state(chime_player.state_path(), {
            "playing": True, "pid": 1, "slug": "tune", "started_at": 100.0,
            "tempo_factor": 2.0, "phase": "playing",
            "outputs": {"midi_out": True, "midi_port": PORT_ROLAND, "hdmi_audio": False}})
        events = [{"sec": 0.0}, {"sec": 1.0}, {"sec": 3.0}]
        chime_player.set_outputs(hdmi_audio=True)
        with mock.patch("bells.chime_player._driver_alive", return_value=True):
            st = chime_player.status(events, now=101.0)
        self.assertEqual(st["event_index"], 1)                 # 1 s at x2 = 2 s written
        self.assertEqual(st["playing_to"]["midi_port"], PORT_ROLAND)
        self.assertTrue(st["outputs"]["hdmi_audio"])          # the switch, for the next Play

    @unittest.skipUnless(sys.platform.startswith("linux"), "uses /proc")
    def test_real_driver_detaches_and_stop_ends_it(self):
        chime_player.set_outputs(midi_out=True, hdmi_audio=True)
        long_midi = chime_midi.write_midi(
            [(quarter(i), quarter(i + 1), C5) for i in range(40)], bpm=BPM_60)
        self.tune.midi.save("long.midi", SimpleUploadedFile("long.midi", long_midi))
        chime_player.play(self.tune)
        deadline = time.monotonic() + 10
        st = {}
        while time.monotonic() < deadline:
            st = chime_player.read_state()
            if st.get("phase") == "playing":
                break
            time.sleep(0.05)
        self.assertEqual(st.get("phase"), "playing", st)
        pid = st["pid"]
        self.assertTrue(chime_player._driver_alive(pid))
        chime_player.stop()
        self.assertFalse(chime_player._driver_alive(pid))
        self.assertFalse(chime_player.read_state()["playing"])
        out = subprocess.run(["pgrep", "-f", str(self.fs)], capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "", "fluidsynth left behind")
        calls = self.ap_calls()
        self.assertEqual(calls[-1][:2], ["-p", PORT_ROLAND])    # all notes off after Stop
        self.assertEqual(self.sent_files()[-1].read_bytes(), chime_midi.all_off_midi())


class ChimeTuneMidiFieldTests(ChimesRootMixin, TestCase):
    def make(self, **kw):
        return ChimeTune.objects.create(
            title="T", source=SimpleUploadedFile("t.png", png_bytes(SMALL, SMALL)), **kw)

    def test_out_of_set_midi_notes_are_recorded(self):
        t = self.make(midi=SimpleUploadedFile("t.mid", small_midi((C5, G5))))
        self.assertIn("G5 (MIDI 79)", t.bell_problems)
        self.assertEqual(len(t.bell_problems.splitlines()), 1)

    def test_a_tune_on_the_bells_has_no_problems(self):
        t = self.make(midi=SimpleUploadedFile("t.mid", SAMPLE_MIDI.read_bytes()),
                      notemap=SimpleUploadedFile("n.json", SAMPLE_NOTEMAP.read_bytes()))
        self.assertEqual(t.bell_problems, "")
        self.assertEqual(len(t.notemap_data()["events"]), 60)

    def test_note_map_problems_name_the_bar(self):
        data = json.loads(SAMPLE_NOTEMAP.read_text())
        data["out_of_set"] = [{"bar": 3, "beat": 2.0, "pitch": "G5", "midi": G5}]
        t = self.make(notemap=SimpleUploadedFile("n.json", json.dumps(data).encode()))
        self.assertIn("bar 3 beat 2: G5", t.bell_problems)

    def test_replacing_or_deleting_removes_the_files(self):
        t = self.make(midi=SimpleUploadedFile("a.mid", small_midi()))
        old = Path(t.midi.path)
        t.midi = SimpleUploadedFile("b.mid", small_midi())
        t.save()
        self.assertFalse(old.exists())
        new = Path(t.midi.path)
        t.delete()
        self.assertFalse(new.exists())

    def test_admin_form_refuses_bad_midi_and_note_maps(self):
        files = {"source": SimpleUploadedFile("t.png", png_bytes(SMALL, SMALL)),
                 "midi": SimpleUploadedFile("t.mid", b"junk"),
                 "notemap": SimpleUploadedFile("n.json", b"{}")}
        form = ChimeTuneForm(data={"title": "T", "order": 1}, files=files)
        self.assertFalse(form.is_valid())
        self.assertIn("midi", form.errors)
        self.assertIn("notemap", form.errors)

    def test_migrations_match_the_models(self):
        out = io.StringIO()
        call_command("makemigrations", "bells", "--check", "--dry-run", stdout=out)


def make_bundle(folder: Path, title="Boars Head Test", slug="boars-head-test"):
    folder.mkdir(parents=True)
    shutil.copy(SAMPLE_FILE, folder / "score.pdf")
    shutil.copy(SAMPLE_MIDI, folder / "tune.midi")
    shutil.copy(SAMPLE_NOTEMAP, folder / "notemap.json")
    (folder / "tune.json").write_text(json.dumps({
        "format": "sandbells-chime-bundle", "version": 1, "title": title, "slug": slug,
        "pdf": "score.pdf", "midi": "tune.midi", "notemap": "notemap.json", "pages": []}))
    return folder


@needs_poppler
class ChimeBundleLoadTests(ChimesRootMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.tmp = Path(tempfile.mkdtemp(prefix="chime-bundle-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_load_a_bundle_folder(self):
        out = io.StringIO()
        call_command("chime_load", str(make_bundle(self.tmp / "b")), stdout=out)
        t = ChimeTune.objects.get()
        self.assertEqual(t.title, "Boars Head Test")
        self.assertTrue(t.midi and t.notemap)
        self.assertEqual(t.page_count, 1)
        self.assertIn("from bundle", out.getvalue())

    def test_load_a_bundle_zip_twice(self):
        folder = make_bundle(self.tmp / "b")
        zpath = self.tmp / "b.chime.zip"
        with zipfile.ZipFile(zpath, "w") as z:
            for f in folder.iterdir():
                z.write(f, "boars-head-test/" + f.name)
        call_command("chime_load", str(zpath), stdout=io.StringIO())
        call_command("chime_load", str(zpath), stdout=io.StringIO())
        self.assertEqual(ChimeTune.objects.count(), 1)
        midi_dir = Path(self.root) / chime_files.MIDI_DIR
        self.assertEqual(len(list(midi_dir.iterdir())), 1)

    def test_a_zip_with_paths_outside_is_refused(self):
        zpath = self.tmp / "evil.zip"
        with zipfile.ZipFile(zpath, "w") as z:
            z.writestr("../evil.txt", "x")
        with self.assertRaisesRegex(CommandError, "unsafe"):
            call_command("chime_load", str(zpath), stdout=io.StringIO())

    def test_not_a_bundle(self):
        (self.tmp / "x").mkdir()
        with self.assertRaises(CommandError):
            call_command("chime_load", str(self.tmp / "x"), stdout=io.StringIO())


@needs_poppler
class ChimePlayerViewTests(ChimesRootMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.tune = ChimeTune.objects.create(
            title="Carol", source=SimpleUploadedFile("c.pdf", SAMPLE_FILE.read_bytes()),
            midi=SimpleUploadedFile("c.midi", SAMPLE_MIDI.read_bytes()),
            notemap=SimpleUploadedFile("c.json", SAMPLE_NOTEMAP.read_bytes()))
        self.plain = ChimeTune.objects.create(
            title="Plain", source=SimpleUploadedFile("p.png", png_bytes(SMALL, SMALL)))
        self.csrf_client = Client(enforce_csrf_checks=True, REMOTE_ADDR=LOCAL)

    def token(self):
        r = self.csrf_client.get(reverse("chime_tune", args=[self.tune.slug]))
        return r.cookies["csrftoken"].value

    def post(self, name, body, addr=LOCAL, token=True):
        headers = {"HTTP_X_CSRFTOKEN": self.token()} if token else {}
        return self.csrf_client.post(reverse(name), json.dumps(body),
                                     content_type="application/json", REMOTE_ADDR=addr,
                                     **headers)

    def test_page_with_midi_has_the_player_and_the_dot(self):
        r = self.client.get(reverse("chime_tune", args=[self.tune.slug]))
        self.assertContains(r, 'id="chime-player"')
        self.assertContains(r, 'id="chime-dot"')
        self.assertContains(r, 'max="%d"' % chime_player.TEMPO_PERCENT_MAX)
        self.assertContains(r, reverse("chime_notemap", args=[self.tune.slug]))
        self.assertNotContains(r, "not on the 8 bells")

    def test_full_screen_has_the_player_too(self):
        r = self.client.get(reverse("chime_full", args=[self.tune.slug, 1]))
        self.assertContains(r, 'data-image-id="chime-full-image"')
        self.assertContains(r, 'data-full="1"')

    def test_page_without_midi_has_no_player(self):
        r = self.client.get(reverse("chime_tune", args=[self.plain.slug]))
        self.assertNotContains(r, 'id="chime-player"')

    def test_out_of_set_tune_shows_a_warning(self):
        ChimeTune.objects.filter(pk=self.tune.pk).update(bell_problems="a\nb")
        r = self.client.get(reverse("chime_tune", args=[self.tune.slug]))
        self.assertContains(r, "2 notes not on the 8 bells")

    def test_notemap_json_is_compact(self):
        r = self.client.get(reverse("chime_notemap", args=[self.tune.slug]))
        data = r.json()
        self.assertEqual(len(data["events"][0]), 4)
        self.assertEqual(data["bpm"], 100.0)
        self.assertEqual(self.client.get(
            reverse("chime_notemap", args=[self.plain.slug])).status_code, 404)

    def test_play_needs_csrf_and_the_lan(self):
        with mock.patch("bells.chime_player.play") as play:
            self.assertEqual(self.post("chime_player_play", {"slug": self.tune.slug},
                                       token=False).status_code, 403)
            self.assertEqual(self.post("chime_player_play", {"slug": self.tune.slug},
                                       addr=PUBLIC).status_code, 403)
            play.assert_not_called()

    def test_play_and_stop(self):
        with mock.patch("bells.chime_player.play", return_value={"playing": True}) as play:
            r = self.post("chime_player_play", {"slug": self.tune.slug, "tempo": 80})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(play.call_args[0][1], 80)
        with mock.patch("bells.chime_player.stop") as stop:
            r = self.post("chime_player_stop", {})
        self.assertTrue(r.json()["ok"])
        stop.assert_called_once()

    def test_play_unknown_tune_or_player_error(self):
        self.assertEqual(self.post("chime_player_play", {"slug": "nope"}).status_code, 404)
        with mock.patch("bells.chime_player.play",
                        side_effect=chime_player.PlayerError("soundfont not found: x")):
            r = self.post("chime_player_play", {"slug": self.tune.slug})
        self.assertEqual(r.status_code, 503)
        self.assertIn("soundfont", r.json()["error"])

    def test_state_reports_the_event_for_the_dot(self):
        chime_driver.write_state(chime_player.state_path(), {
            "playing": True, "pid": 1, "slug": self.tune.slug, "title": "Carol",
            "started_at": time.time() - 2.0, "tempo_factor": 1.0, "phase": "playing"})
        with mock.patch("bells.chime_player._driver_alive", return_value=True):
            data = self.client.get(reverse("chime_player_state")).json()
        self.assertTrue(data["playing"])
        self.assertEqual(data["event_index"], 0)               # first note is at 1.8 s
        self.assertIn("now", data)
        self.assertEqual(self.client.post(reverse("chime_player_state")).status_code, 405)

    def test_screen_has_the_output_switches(self):
        r = self.client.get(reverse("chime_tune", args=[self.tune.slug]))
        self.assertContains(r, 'id="chime-midi"')
        self.assertContains(r, 'id="chime-hdmi"')
        self.assertContains(r, 'id="chime-port"')
        self.assertContains(r, reverse("chime_player_outputs"))
        self.assertContains(r, reverse("chime_player_ports"))
        r = self.client.get(reverse("chime_full", args=[self.tune.slug, 1]))
        self.assertContains(r, 'id="chime-midi"')

    def test_outputs_post_needs_csrf_and_the_lan_and_is_kept(self):
        from bells.models import ChimeOutputs
        self.assertEqual(self.post("chime_player_outputs", {"midi_out": False},
                                   token=False).status_code, 403)
        self.assertEqual(self.post("chime_player_outputs", {"midi_out": False},
                                   addr=PUBLIC).status_code, 403)
        self.assertEqual(self.client.get(reverse("chime_player_outputs")).status_code, 405)
        r = self.post("chime_player_outputs", {"midi_out": False, "hdmi_audio": True})
        self.assertEqual(r.json()["outputs"],
                         {"midi_out": False, "midi_port": "", "hdmi_audio": True})
        self.assertEqual(ChimeOutputs.objects.get().as_dict(), r.json()["outputs"])
        r = self.client.get(reverse("chime_tune", args=[self.tune.slug]))   # a reload
        self.assertContains(r, 'id="chime-hdmi" class="chime-toggle" aria-pressed="true"')
        self.assertContains(r, 'id="chime-midi" class="chime-toggle" aria-pressed="false"')
        data = self.client.get(reverse("chime_player_state")).json()
        self.assertEqual(data["outputs"], r.context["player"]["outputs"])

    def test_outputs_post_refuses_the_pico(self):
        r = self.post("chime_player_outputs", {"midi_port": "Pico 2 W"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Pico", r.json()["error"])

    def test_ports_lists_aplaymidi_without_the_pico(self):
        with mock.patch("bells.chime_player.subprocess.run", return_value=SimpleNamespace(
                returncode=0, stdout=APLAYMIDI_LIST, stderr="")):
            data = self.client.get(reverse("chime_player_ports")).json()
        self.assertEqual([p["id"] for p in data["ports"]], [PORT_THROUGH, PORT_ROLAND])
        self.assertEqual(data["left_out"], 1)
        self.assertNotIn("Pico", json.dumps(data["ports"]))
        self.assertIn("outputs", data)

    def test_admin_outputs_form_refuses_the_pico(self):
        from bells.admin import ChimeOutputsForm
        form = ChimeOutputsForm(data={"midi_out": "on", "midi_port": "Pico 2 W"})
        self.assertFalse(form.is_valid())
        self.assertIn("midi_port", form.errors)
        form = ChimeOutputsForm(data={"midi_out": "on", "midi_port": PORT_ROLAND})
        self.assertTrue(form.is_valid(), form.errors)
