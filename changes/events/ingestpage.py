"""ingestpage.py -- what the Ingest page (/events/ingest/) shows, read-only.

    units()              systemctl is-enabled / is-active of each ingest unit
    udp_bound(port)      is the port bound on this Pi (/proc/net/udp)
    this_ips()           this Pi's IPv4 addresses (the Pico's udp_host is one)
    verdict(doc, age)    OK / QUIET / STALE / DOWN from the status file
    page_context()       everything above + the last stored stroke

Every probe has a short timeout and turns "no systemd", "no /proc" or any
error into a plain word, so the page always renders (and the tests run on
a machine without systemd).  Nothing here talks to the ingest process: it
only reads the file that ingest_udp writes (ingeststatus.py).
"""

import subprocess
import time

from . import constants as C
from . import localtime as LT
from .ingeststatus import ingest_status_path, read_ingest_status
from .midiingest import midi_status_path
from . import serialingest

V_OK, V_QUIET, V_STALE, V_DOWN = "OK", "QUIET", "STALE", "DOWN"
NO_SYSTEMD = "no systemd"
NOT_FOUND = "not-found"
HEX = 16
PROC_LOCAL_ADDR_COL = 1         # /proc/net/udp: "sl local_address rem_address ..."


def _now_ms():
    return int(time.time() * C.MS_PER_S)


def systemctl(*args, run=None, timeout=C.SYSTEMCTL_TIMEOUT_S):
    """systemctl's one-word answer ('enabled', 'inactive', ...), or
    'no systemd' / 'timeout' / 'error'.  Never raises."""
    run = run or subprocess.run
    try:
        r = run([C.SYSTEMCTL] + list(args), capture_output=True, text=True,
                timeout=timeout)
    except FileNotFoundError:
        return NO_SYSTEMD
    except subprocess.TimeoutExpired:
        return "timeout"
    except Exception:
        return "error"
    out = (r.stdout or "").strip().splitlines()
    if out:
        return out[0].strip()
    err = (r.stderr or "").lower()
    if "no such file" in err or "not found" in err or "not loaded" in err:
        return NOT_FOUND
    if "system has not been booted with systemd" in err or "failed to connect to bus" in err:
        return NO_SYSTEMD
    return "unknown"


def units(run=None):
    out = []
    for unit in C.INGEST_UNITS:
        enabled = systemctl("is-enabled", unit, run=run)
        active = systemctl("is-active", unit, run=run)
        out.append({"unit": unit, "mode": C.INGEST_UNIT_MODES.get(unit, ""),
                    "installed": (None if NO_SYSTEMD in (enabled, active)
                                  else enabled != NOT_FOUND),
                    "enabled": enabled, "active": active,
                    "ok_enabled": enabled == "enabled", "ok_active": active == "active"})
    return out


def udp_bound(port, path=C.PROC_NET_UDP):
    """True / False: a socket is bound to this UDP port; None: cannot tell."""
    try:
        with open(path) as f:
            lines = f.read().splitlines()[1:]
    except OSError:
        return None
    for line in lines:
        cols = line.split()
        if len(cols) > PROC_LOCAL_ADDR_COL and ":" in cols[PROC_LOCAL_ADDR_COL]:
            try:
                if int(cols[PROC_LOCAL_ADDR_COL].rsplit(":", 1)[1], HEX) == port:
                    return True
            except ValueError:
                continue
    return False


def this_ips(run=None, timeout=C.SYSTEMCTL_TIMEOUT_S):
    run = run or subprocess.run
    try:
        r = run(["hostname", "-I"], capture_output=True, text=True, timeout=timeout)
        return [ip for ip in (r.stdout or "").split() if "." in ip]
    except Exception:
        return []


def _ago_s(now, ms):
    return None if ms is None else max(0, now - ms) // C.MS_PER_S


def verdict(doc, age_ms, now_ms):
    """-> (verdict, why)."""
    if doc is None:
        return V_DOWN, ("no status file at %s: ingest_udp is not running "
                        "(or is an older build)" % ingest_status_path())
    if doc.get("state") == C.INGEST_STATE_STOPPED:
        return V_DOWN, "ingest_udp stopped (pid %s)" % doc.get("pid")
    if age_ms is None or age_ms > C.INGEST_STATUS_STALE_MS:
        return V_STALE, ("status file not rewritten for %d s: ingest_udp hung or "
                         "killed" % ((age_ms or 0) // C.MS_PER_S))
    last = (doc.get("last") or {}).get("ms")
    if last is None:
        return V_QUIET, "running, but not one datagram since it started"
    if now_ms - last > C.INGEST_QUIET_MS:
        return V_QUIET, "running, no datagram for %d s" % _ago_s(now_ms, last)
    return V_OK, "running, datagrams arriving"


def _when(now, ms):
    if ms is None:
        return {"ms": None, "hms": None, "ago_s": None}
    return {"ms": ms, "hms": LT.local_hms(ms), "ago_s": _ago_s(now, ms)}


def last_stroke():
    """The newest stored stroke: its time, src, seq.  None if there is none."""
    from .models import Event
    e = (Event.objects.filter(type=C.TYPE_STROKE).order_by("-id")
         .only("utc_ms", "received_at", "src", "boot_id", "seq", "ch").first())
    if e is None:
        return None
    return {"src": e.src, "boot_id": e.boot_id, "seq": e.seq, "ch": e.ch,
            "utc_ms": e.utc_ms, "received_ms": LT.dt_to_ms(e.received_at)}


def page_context(now_ms=None, run=None, proc_udp=C.PROC_NET_UDP):
    now = _now_ms() if now_ms is None else now_ms
    doc, age = read_ingest_status()
    v, why = verdict(doc, age, now)
    d = doc or {}
    port = d.get("port") or C.UDP_INGEST_PORT
    last = dict(d.get("last") or {})
    last.update(_when(now, last.get("ms")))
    rejects = [dict(r, **{"hms": LT.local_hms(r.get("ms"))})
               for r in reversed(d.get("recent_rejects") or [])]
    try:
        stroke, stroke_error = last_stroke(), None
    except Exception as e:                    # DB locked / missing: still show the rest
        stroke, stroke_error = None, str(e)
    if stroke:
        stroke["stored"] = _when(now, stroke["received_ms"])
        stroke["stamped"] = _when(now, stroke["utc_ms"])
    mdoc, mage = read_ingest_status(midi_status_path())
    midi = dict((mdoc or {}).get("midi") or {})
    if midi:
        midi["stamp"] = midi.get("stamp") or {}
        midi["last_note_when"] = _when(now, midi.get("last_note_ms"))
        midi["last_stamp_when"] = _when(now, midi["stamp"].get("last_stamp_ms"))
    sdoc, sage = read_ingest_status(serialingest.serial_status_path())
    serial = dict((sdoc or {}).get("serial") or {})
    hb = serialingest.latest(now) if serial else None
    if serial:
        serial["last_good_when"] = _when(now, serial.get("last_good_ms"))
    return {
        "serial": serial, "serial_path": serialingest.serial_status_path(),
        "serial_age_s": None if sage is None else sage // C.MS_PER_S,
        "serial_file_stale": sage is None or sage > C.INGEST_STATUS_STALE_MS,
        "serial_hb_stale": hb is None or hb["stale"],
        "midi": midi, "midi_path": midi_status_path(),
        "midi_age_s": None if mage is None else mage // C.MS_PER_S,
        "midi_stale": mage is None or mage > C.INGEST_STATUS_STALE_MS,
        "verdict": v, "why": why, "file_path": ingest_status_path(),
        "file_age_s": None if age is None else age // C.MS_PER_S,
        "stale_s": C.INGEST_STATUS_STALE_MS // C.MS_PER_S,
        "doc": doc, "counters": d.get("counters") or {},
        "started": _when(now, d.get("started_ms")),
        "last": last, "rejects": rejects, "recent_max": C.INGEST_STATUS_RECENT,
        "units": units(run=run),
        "configured": {"mode": C.INGEST_MODE_UDP, "host": C.UDP_INGEST_HOST,
                       "port": C.UDP_INGEST_PORT},
        "running": {"mode": d.get("mode"), "host": d.get("host"), "port": d.get("port"),
                    "pid": d.get("pid")} if doc else None,
        "port_bound": udp_bound(port, proc_udp), "port": port,
        "ips": this_ips(run=run), "stroke": stroke, "stroke_error": stroke_error,
        "refresh_s": C.INGEST_PAGE_REFRESH_S,
    }
