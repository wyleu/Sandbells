#!/usr/bin/env python3
"""Chimes player driver: plays one tune at a tempo factor to the outputs that
are switched on, and records what it is doing in a small JSON state file.

Started by bells/chime_player.py (never by hand on the kiosk).  Stdlib only.

Outputs (either, both or neither; with neither the dot still runs silently):
  * MIDI out (--midi-port): a copy of the tune with the tempo factor and the
    start point already in its times is written next to the state file and
    played with `aplaymidi -p PORT`.  chime_player never passes the Pico's
    usb_midi port (ingest_midi reads it).
  * HDMI audio (--hdmi): bell samples through fluidsynth -n (no MIDI input,
    so it never opens an ALSA MIDI port) on the HDMI ALSA device.  Notes are
    sent on its stdin shell, timed here.
The state's start time is the moment the first note is due, so the page's
dot follows from its own clock.  With --daemon it detaches (double fork, own
session): Stop kills its whole process group, aplaymidi and fluidsynth too.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import select
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

try:                                   # inside Django: bells.chime_midi
    from . import chime_midi
except ImportError:                    # run as a script by chime_player
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import chime_midi

DRIVER_TAG = "chime_driver"            # chime_player checks /proc/<pid>/cmdline for this
READY_TIMEOUT_S = 30                   # loading a soundfont on a Pi 3
MIDI_COPY_SUFFIX = ".play.mid"         # the MIDI-out copy, next to the state file
MIDI_FINISH_SLACK_S = 2.0              # aplaymidi may take this long past the last note
READY_POLL_S = 0.2
START_LEAD_S = 0.25                    # time between "ready" and the first note
RELEASE_TAIL_S = 3.0                   # let the last bells ring before quitting
QUIT_WAIT_S = 3.0
STATE_TMP_SUFFIX = ".tmp"
FONT_ROW_RE = re.compile(r"^\s*\d+\s+\S")    # a row of fluidsynth's "fonts" table


def write_state(path: Path, state: dict):
    tmp = path.with_name(path.name + STATE_TMP_SUFFIX + str(os.getpid()))
    tmp.write_text(json.dumps(state))
    os.replace(tmp, path)


def read_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def fluidsynth_command(args) -> list:
    cmd = [args.fluidsynth, "-n", "-a", args.audio_driver]
    if args.audio_device and args.audio_driver == "alsa":
        cmd += ["-o", "audio.alsa.device=%s" % args.audio_device]
    cmd += ["-g", str(args.gain), args.soundfont]   # one argv item: spaces are fine
    return cmd


def shell_line(kind, channel, a, b) -> str:
    if kind == "on":
        return "noteon %d %d %d\n" % (channel, a, b)
    if kind == "off":
        return "noteoff %d %d\n" % (channel, a)
    if kind == "cc":
        return "cc %d %d %d\n" % (channel, a, b)
    if kind == "prog":
        return "prog %d %d\n" % (channel, a)
    raise ValueError(kind)


def wait_ready(proc, timeout=READY_TIMEOUT_S) -> bool:
    """Ask for the font list; ready once a font row comes back."""
    proc.stdin.write("fonts\n")
    proc.stdin.flush()
    end = time.monotonic() + timeout
    buf = ""
    while time.monotonic() < end:
        if proc.poll() is not None:
            return False
        r, _, _ = select.select([proc.stdout], [], [], READY_POLL_S)
        if not r:
            continue
        chunk = os.read(proc.stdout.fileno(), 4096).decode(errors="replace")
        if not chunk:
            return False
        buf += chunk
        if any(FONT_ROW_RE.match(line) for line in buf.splitlines()):
            return True
    return False


def drain(stream):
    try:
        while os.read(stream.fileno(), 4096):
            pass
    except OSError:
        pass


def daemonize():
    if os.fork():
        os._exit(0)
    os.setsid()
    if os.fork():
        os._exit(0)
    devnull = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2):
        os.dup2(devnull, fd)


def midi_copy_path(state_path: Path) -> Path:
    return state_path.with_name(state_path.stem + MIDI_COPY_SUFFIX)


def aplaymidi_command(args, path) -> list:
    return [args.aplaymidi, "-p", args.midi_port, str(path)]


def play(args, sleep=time.sleep, clock=time.monotonic, wall=time.time, popen=subprocess.Popen):
    state_path = Path(args.state)
    outputs = {"midi_out": bool(args.midi_port), "midi_port": args.midi_port,
               "hdmi_audio": bool(args.hdmi)}
    base = {"pid": os.getpid(), "pgid": os.getpgrp(), "slug": args.slug,
            "title": args.title, "tempo_factor": args.factor, "from_sec": args.from_sec,
            "soundfont": args.soundfont if args.hdmi else "", "outputs": outputs}
    write_state(state_path, dict(base, playing=True, phase="loading", started_at=None))
    synth = aplay = None
    copy = midi_copy_path(state_path)

    def mine():
        return read_state(state_path).get("pid") == os.getpid()

    try:
        mf = chime_midi.read_midi(Path(args.midi).read_bytes())
        synth_msgs = chime_midi.scale_times(
            chime_midi.playback_messages(mf, program_changes=args.program_changes),
            args.factor, args.from_sec)
        if args.midi_port:
            # MIDI out sends the file's programs too: the far end may need them
            copy.write_bytes(chime_midi.write_messages(chime_midi.scale_times(
                chime_midi.playback_messages(mf, program_changes=True),
                args.factor, args.from_sec)))
        if args.hdmi:
            synth = popen(fluidsynth_command(args), stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, bufsize=1)
            if not wait_ready(synth):
                raise RuntimeError("fluidsynth did not start (soundfont %s, device %s)"
                                   % (args.soundfont, args.audio_device))
            threading.Thread(target=drain, args=(synth.stdout,), daemon=True).start()
        t0 = clock() + START_LEAD_S
        started_at = wall() + START_LEAD_S - args.from_sec / args.factor
        end_s = synth_msgs[-1][0] if synth_msgs else 0.0
        delay = t0 - clock()
        if delay > 0:
            sleep(delay)
        if args.midi_port:
            aplay = popen(aplaymidi_command(args, copy), stdin=subprocess.DEVNULL,
                          stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        write_state(state_path, dict(base, playing=True, phase="playing",
                                     started_at=started_at))
        for t, kind, ch, a, b in synth_msgs:
            delay = t0 + t - clock()
            if delay > 0:
                sleep(delay)
            if synth:
                synth.stdin.write(shell_line(kind, ch, a, b))
                synth.stdin.flush()
        delay = t0 + end_s - clock()             # silent: keep time to the last note
        if delay > 0:
            sleep(delay)
        if aplay:
            try:
                err = aplay.communicate(timeout=MIDI_FINISH_SLACK_S)[1]
            except subprocess.TimeoutExpired:
                aplay.kill()
                err = aplay.communicate()[1]
            if aplay.returncode:
                raise RuntimeError("aplaymidi -p %s failed: %s"
                                   % (args.midi_port, (err or "").strip()[-200:]))
        if synth:
            sleep(RELEASE_TAIL_S)
            synth.stdin.write("quit\n")
            synth.stdin.flush()
            synth.wait(QUIT_WAIT_S)
        if mine():
            write_state(state_path, dict(base, playing=False, phase="finished",
                                         started_at=started_at))
    except Exception as e:                       # noqa: BLE001  (recorded for the page)
        if mine():
            write_state(state_path, dict(base, playing=False, phase="error",
                                         started_at=None, error=str(e)))
        raise
    finally:
        for proc in (aplay, synth):
            if proc and proc.poll() is None:
                proc.kill()
                proc.wait()


def parser():
    ap = argparse.ArgumentParser(description="Sandbells chimes player driver (%s)" % DRIVER_TAG)
    ap.add_argument("--midi", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--midi-port", default="", help="ALSA sequencer port; empty: no MIDI out")
    ap.add_argument("--aplaymidi", default="aplaymidi")
    ap.add_argument("--hdmi", action="store_true", help="bell samples on the HDMI audio device")
    ap.add_argument("--soundfont", default="")
    ap.add_argument("--fluidsynth", default="fluidsynth")
    ap.add_argument("--audio-driver", default="alsa")
    ap.add_argument("--audio-device", default="")
    ap.add_argument("--gain", type=float, required=True)
    ap.add_argument("--factor", type=float, required=True)
    ap.add_argument("--from-sec", type=float, default=0.0)
    ap.add_argument("--slug", default="")
    ap.add_argument("--title", default="")
    ap.add_argument("--program-changes", action="store_true")
    ap.add_argument("--daemon", action="store_true")
    return ap


def main(argv=None):
    args = parser().parse_args(argv)
    if args.daemon:
        daemonize()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        play(args)
    except Exception:                            # noqa: BLE001  (state has the reason)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
