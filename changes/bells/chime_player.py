"""Chimes player: one tune at a time on this Pi, with a dot on the sheet.

Play starts bells/chime_driver.py detached (it plays the tune and writes a
small state file); Stop kills its process group, then sends all-notes-off.
Every gunicorn worker reads the same state file, so the page, a reload or
the full-screen view all see the same player.  A file lock keeps two Plays
from racing.

Two outputs, switched on the Chimes screen (bells.models.ChimeOutputs, one
row; the settings below are only its first values):
  MIDI out    aplaymidi -p PORT (a tempo-scaled copy of the tune).  Never the
              Pico's usb_midi port: ingest_midi reads it.  Ports whose client
              or port name contains one of EXCLUDED_PORT_NAMES are left out of
              every list and refused.  QmidiNet (QMIDINET_CLIENT_NAME) is kept
              when that service is running.
  HDMI audio  bell samples, fluidsynth -n on the HDMI ALSA device.
Both off: Play still runs the dot, silently.

Settings, all optional, read with defaults (no settings file is edited):
  /etc/sandbells/settings.json  {"chimes": {
      "midi_out": true, "midi_port": "", "midi_exclude": [],
      "hdmi_audio": false, "hdmi_device": "hdmi:CARD=vc4hdmi,DEV=0",
      "soundfont": ..., "gain": 0.6, "program_changes": false}}
  or Django settings SANDBELLS_CHIMES_MIDI_PORT, SANDBELLS_CHIMES_HDMI_DEVICE,
  SANDBELLS_CHIMES_SOUNDFONT, SANDBELLS_CHIMES_GAIN, SANDBELLS_CHIMES_PLAYER_STATE.
The default soundfont is the Sandbach 8-bell font when it is installed,
else FluidR3_GM.
"""

from __future__ import annotations

import fcntl
import re
import os
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings

from bells import chimes as chime_files
from bells import chime_driver, chime_midi, chime_notemap

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SOUNDFONT_DIR = Path("/usr/local/share/sounds/sf2")
SOUNDFONT_SANDBACH_8 = SOUNDFONT_DIR / "sandbach_bells_8.sf2"         # default
SOUNDFONT_SANDBACH_12 = SOUNDFONT_DIR / "Sandbach Bells_n_12.sf2"     # optional, by setting
SOUNDFONT_GM = Path("/usr/share/sounds/sf2/FluidR3_GM.sf2")           # fluid-soundfont-gm
DEFAULT_SOUNDFONTS = (SOUNDFONT_SANDBACH_8, SOUNDFONT_GM)
DEFAULT_AUDIO_DRIVER = "alsa"
# Pi 3, KMS driver: the HDMI card is "vc4hdmi"; its "hdmi" PCM does the IEC958
# packing that a plain hw: device refuses.  (Old firmware driver: "bcm2835 HDMI 1",
# set "hdmi_device": "plughw:CARD=b1" or what `aplay -L` lists.)
DEFAULT_HDMI_DEVICE = "hdmi:CARD=vc4hdmi,DEV=0"
DEFAULT_GAIN = 0.6
DEFAULT_MIDI_OUT = True
DEFAULT_HDMI_AUDIO = False            # needs fluidsynth and a soundfont installed
DEFAULT_MIDI_PORT = ""                # "": the first allowed port (see pick_port)
FLUIDSYNTH = "fluidsynth"
APLAYMIDI = "aplaymidi"
APLAYMIDI_LIST_TIMEOUT_S = 5
PANIC_TIMEOUT_S = 5
PANIC_FILE_NAME = "player-all-off.mid"

# The Pico 2 W's usb_midi port belongs to ingest_midi: never a destination.
# (events.constants.MIDI_CARD_MATCH is what ingest_midi looks for.)
EXCLUDED_PORT_NAMES = ("Pico", "CircuitPython", "Pico 2 W")
# ALSA client created by qmidinet (install-steps/sandbells-qmidinet.sh).
# Listed like any other port; not excluded.  midi_port may be "QmidiNet".
QMIDINET_CLIENT_NAME = "QmidiNet"
MIDI_THROUGH_NAME = "Midi Through"     # last choice when picking a port by itself
PORT_ID_RE = re.compile(r"^\d+:\d+$")
# aplaymidi -l:  " 14:0    Midi Through                     Midi Through Port-0"
PORT_ROW_RE = re.compile(r"^\s*(\d+:\d+)\s+(.*?)\s{2,}(.*?)\s*$")

TEMPO_PERCENT_MIN = 50
TEMPO_PERCENT_MAX = 150
TEMPO_PERCENT_STEP = 5
TEMPO_PERCENT_DEFAULT = 100
PERCENT = 100

STATE_FILE_NAME = "player-state.json"
LOCK_FILE_NAME = "player.lock"
SPAWN_WAIT_S = 5               # the --daemon parent exits at once
STOP_WAIT_S = 2.0
STOP_POLL_S = 0.05
PROC_CMDLINE = "/proc/%d/cmdline"

SETTING_SOUNDFONT = "SANDBELLS_CHIMES_SOUNDFONT"
SETTING_HDMI_DEVICE = "SANDBELLS_CHIMES_HDMI_DEVICE"
SETTING_MIDI_PORT = "SANDBELLS_CHIMES_MIDI_PORT"
SETTING_GAIN = "SANDBELLS_CHIMES_GAIN"
SETTING_STATE = "SANDBELLS_CHIMES_PLAYER_STATE"
SETTINGS_JSON_BLOCK = "chimes"


class PlayerError(Exception):
    """Play cannot start; the message says why."""


def _json_settings() -> dict:
    from bells.app_settings import _load
    raw, _ = _load()
    block = raw.get(SETTINGS_JSON_BLOCK) if isinstance(raw, dict) else None
    return block if isinstance(block, dict) else {}


def player_config() -> dict:
    js = _json_settings()

    def pick(setting, key, default):
        value = getattr(settings, setting, None) if setting else None
        if value in (None, ""):
            value = js.get(key)
        return default if value in (None, "") else value

    soundfont = pick(SETTING_SOUNDFONT, "soundfont", None)
    if soundfont is None:
        soundfont = next((str(p) for p in DEFAULT_SOUNDFONTS if p.is_file()),
                         str(DEFAULT_SOUNDFONTS[0]))
    extra = js.get("midi_exclude")
    extra = [str(x) for x in extra if str(x).strip()] if isinstance(extra, list) else []
    return {
        "midi_out": bool(pick(None, "midi_out", DEFAULT_MIDI_OUT)),
        "midi_port": str(pick(SETTING_MIDI_PORT, "midi_port", DEFAULT_MIDI_PORT)).strip(),
        "midi_exclude": tuple(EXCLUDED_PORT_NAMES) + tuple(extra),
        "aplaymidi": str(js.get("aplaymidi") or APLAYMIDI),
        "hdmi_audio": bool(pick(None, "hdmi_audio", DEFAULT_HDMI_AUDIO)),
        "soundfont": str(soundfont),
        "audio_driver": str(js.get("audio_driver") or DEFAULT_AUDIO_DRIVER),
        "audio_device": str(pick(SETTING_HDMI_DEVICE, "hdmi_device", DEFAULT_HDMI_DEVICE)),
        "gain": float(pick(SETTING_GAIN, "gain", DEFAULT_GAIN)),
        "fluidsynth": str(js.get("fluidsynth") or FLUIDSYNTH),
        "program_changes": bool(js.get("program_changes", False)),
    }


# ---------------------------------------------------------------------------
# MIDI ports (aplaymidi -l), the Pico left out
# ---------------------------------------------------------------------------

def is_excluded_name(text, exclude=None) -> bool:
    exclude = player_config()["midi_exclude"] if exclude is None else exclude
    low = str(text).lower()
    return any(x.lower() in low for x in exclude)


def parse_ports(text, exclude=EXCLUDED_PORT_NAMES):
    """aplaymidi -l output -> (allowed ports, ids of the ports left out)."""
    ports, left_out = [], []
    for line in text.splitlines():
        m = PORT_ROW_RE.match(line)
        if not m:
            continue                                  # the heading
        port = {"id": m.group(1), "client": m.group(2), "name": m.group(3)}
        if is_excluded_name(port["client"], exclude) or is_excluded_name(port["name"], exclude):
            left_out.append(port["id"])
            continue
        ports.append(port)
    return ports, left_out


def list_ports(cfg=None) -> dict:
    cfg = cfg or player_config()
    try:
        out = subprocess.run([cfg["aplaymidi"], "-l"], capture_output=True, text=True,
                             timeout=APLAYMIDI_LIST_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ports": [], "left_out": [], "error": "aplaymidi -l: %s" % e}
    if out.returncode:
        return {"ports": [], "left_out": [],
                "error": "aplaymidi -l: %s" % (out.stderr.strip() or out.returncode)}
    ports, left_out = parse_ports(out.stdout, cfg["midi_exclude"])
    return {"ports": ports, "left_out": left_out, "error": ""}


def pick_port(wanted, ports, exclude=EXCLUDED_PORT_NAMES, left_out=()):
    """The port id to play to, or raise PlayerError.  wanted: an id ("14:0"),
    a client name (or part of one), or "" for the first allowed port that is
    not Midi Through (Midi Through if it is the only one)."""
    wanted = (wanted or "").strip()
    if wanted and (is_excluded_name(wanted, exclude) or wanted in left_out):
        raise PlayerError("MIDI port %s is the Pico's (ingest_midi reads it)" % wanted)
    if wanted:
        for p in ports:
            if p["id"] == wanted:
                return p["id"]
        low = wanted.lower()
        for p in ports:
            if low in p["client"].lower() or low in p["name"].lower():
                return p["id"]
        raise PlayerError("MIDI port %s is not there (aplaymidi -l)" % wanted)
    real = [p for p in ports if not p["client"].startswith(MIDI_THROUGH_NAME)]
    if real or ports:
        return (real or ports)[0]["id"]
    raise PlayerError("no MIDI port to play to (aplaymidi -l lists none but the Pico)")


def outputs():
    from bells.models import ChimeOutputs
    return ChimeOutputs.current()


def set_outputs(midi_out=None, hdmi_audio=None, midi_port=None) -> dict:
    """Change the switches (None: leave as it is).  Raises PlayerError for the Pico."""
    row = outputs()
    if midi_port is not None:
        midi_port = str(midi_port).strip()
        if midi_port and (is_excluded_name(midi_port) or (
                PORT_ID_RE.match(midi_port) and midi_port in list_ports()["left_out"])):
            raise PlayerError("MIDI port %s is the Pico's (ingest_midi reads it)" % midi_port)
        row.midi_port = midi_port
    if midi_out is not None:
        row.midi_out = bool(midi_out)
    if hdmi_audio is not None:
        row.hdmi_audio = bool(hdmi_audio)
    row.save()
    return row.as_dict()


def state_path() -> Path:
    configured = getattr(settings, SETTING_STATE, None)
    return Path(configured) if configured else chime_files.chimes_root() / STATE_FILE_NAME


@contextmanager
def _locked():
    path = state_path().with_name(LOCK_FILE_NAME)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _driver_alive(pid) -> bool:
    """True only if pid is running and is our driver (not a reused pid)."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        with open(PROC_CMDLINE % pid, "rb") as f:
            return chime_driver.DRIVER_TAG.encode() in f.read()
    except OSError:
        return False


def tempo_factor(percent) -> float:
    try:
        p = float(percent)
    except (TypeError, ValueError):
        p = TEMPO_PERCENT_DEFAULT
    return max(TEMPO_PERCENT_MIN, min(TEMPO_PERCENT_MAX, p)) / PERCENT


def read_state() -> dict:
    state = chime_driver.read_state(state_path())
    if state.get("playing") and not _driver_alive(state.get("pid")):
        state.update(playing=False, phase=state.get("phase") if state.get("phase")
                     in ("finished", "error") else "stopped")
    return state


def stop() -> dict:
    with _locked():
        return _stop_unlocked()


def _stop_unlocked() -> dict:
    path = state_path()
    state = chime_driver.read_state(path)
    pid, pgid = state.get("pid"), state.get("pgid")
    if _driver_alive(pid):
        # its own process group (never ours: that would be the web worker's)
        target = (pgid if isinstance(pgid, int) and pgid > 0 and pgid != os.getpgrp()
                  else None)
        try:
            if target:
                os.killpg(target, signal.SIGTERM)
            else:
                os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        end = time.monotonic() + STOP_WAIT_S
        while _driver_alive(pid) and time.monotonic() < end:
            time.sleep(STOP_POLL_S)
        if _driver_alive(pid):
            try:
                if target:
                    os.killpg(target, signal.SIGKILL)
                else:
                    os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
    port = (state.get("outputs") or {}).get("midi_port")
    if port:
        send_all_off(port)
    if state:
        state.update(playing=False, phase="stopped")
        path.parent.mkdir(parents=True, exist_ok=True)
        chime_driver.write_state(path, state)
    return state


def send_all_off(port, cfg=None):
    """Sustain off, all sound off, all notes off on all 16 channels to port."""
    cfg = cfg or player_config()
    if is_excluded_name(port, cfg["midi_exclude"]):
        return
    path = state_path().with_name(PANIC_FILE_NAME)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(chime_midi.all_off_midi())
        subprocess.run([cfg["aplaymidi"], "-p", port, str(path)], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=PANIC_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired):
        pass


def driver_command(tune, factor, from_sec, cfg, midi_port="", hdmi=False) -> list:
    cmd = [sys.executable, chime_driver.__file__,
           "--midi", tune.midi.path, "--state", str(state_path()),
           "--midi-port", midi_port, "--aplaymidi", cfg["aplaymidi"],
           "--soundfont", cfg["soundfont"], "--fluidsynth", cfg["fluidsynth"],
           "--audio-driver", cfg["audio_driver"], "--audio-device", cfg["audio_device"],
           "--gain", str(cfg["gain"]), "--factor", str(factor),
           "--from-sec", str(max(0.0, float(from_sec or 0))),
           "--slug", tune.slug, "--title", tune.title, "--daemon"]
    if hdmi:
        cmd.append("--hdmi")
    if cfg["program_changes"]:
        cmd.append("--program-changes")
    return cmd


def play(tune, percent=TEMPO_PERCENT_DEFAULT, from_sec=0.0) -> dict:
    """Stop whatever is playing, then play tune.  Raises PlayerError."""
    if not tune.midi:
        raise PlayerError("%s has no MIDI file" % tune.title)
    cfg = player_config()
    outs = outputs()
    if outs.hdmi_audio and not Path(cfg["soundfont"]).is_file():
        raise PlayerError("HDMI audio: soundfont not found: %s" % cfg["soundfont"])
    port = ""
    if outs.midi_out:
        listing = list_ports(cfg)
        if listing["error"]:
            raise PlayerError("MIDI out: %s" % listing["error"])
        port = pick_port(outs.midi_port or cfg["midi_port"], listing["ports"],
                         cfg["midi_exclude"], listing["left_out"])
    factor = tempo_factor(percent)
    with _locked():
        _stop_unlocked()
        state_path().parent.mkdir(parents=True, exist_ok=True)
        try:
            spawn = subprocess.Popen(driver_command(tune, factor, from_sec, cfg,
                                                    port, outs.hdmi_audio),
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, close_fds=True)
            spawn.wait(SPAWN_WAIT_S)          # the daemon's first parent exits at once
        except (OSError, subprocess.TimeoutExpired) as e:
            raise PlayerError("could not start the player: %s" % e)
    return {"playing": True, "phase": "loading", "slug": tune.slug, "title": tune.title,
            "tempo_factor": factor, "from_sec": from_sec, "started_at": None,
            "outputs": {"midi_out": bool(port), "midi_port": port,
                        "hdmi_audio": outs.hdmi_audio}}


def status(events=None, now=None) -> dict:
    """The state for the page, with the server clock and the current event."""
    now = time.time() if now is None else now
    state = read_state()
    out = {"playing": bool(state.get("playing")), "phase": state.get("phase", "stopped"),
           "slug": state.get("slug", ""), "title": state.get("title", ""),
           "started_at": state.get("started_at"),
           "tempo_factor": state.get("tempo_factor", 1.0),
           "error": state.get("error", ""), "now": now, "event_index": -1,
           "playing_to": state.get("outputs") or {}, "outputs": outputs().as_dict()}
    if out["playing"] and out["started_at"] and events:
        written = (now - out["started_at"]) * out["tempo_factor"]
        out["event_index"] = chime_notemap.event_at(events, written)
        out["written_sec"] = written
    return out
