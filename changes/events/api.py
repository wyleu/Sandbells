"""api.py -- JSON endpoints for the pages.  All times shown are UK local.

  GET /events/api/since/?after=<id>&src=&type=&limit=
                                                    live event list
  GET /events/api/days/?from=YYYY-MM-DD&to=YYYY-MM-DD&src=
                                                    rings per local day
  GET /events/api/link/                             concentrator link state
                                                    (ingest's LinkState file)
"""

import time

from django.http import JsonResponse

from . import constants as C
from . import localtime as LT
from .mapping import ChannelMapper, ch_label
from .ingeststatus import read_ingest_status
from .linkstate import read_link_state
from .midiingest import midi_status_path
from . import serialingest
from .models import receiving_host
from .queries import (current_ring, events_after, ring_json,
                      rings_starting_between, stroke_intervals)

HTTP_BAD_REQUEST = 400


def _bad(msg):
    return JsonResponse({"error": msg}, status=HTTP_BAD_REQUEST)


def _int_arg(request, name, default):
    v = request.GET.get(name)
    if v in (None, ""):
        return default
    return int(v)                     # ValueError -> 400 by the caller


def _now_ms():
    return int(time.time() * C.MS_PER_S)


def time_ok(acc, sync):
    return acc == C.TIME_OK_ACC and sync in C.TIME_OK_SYNC


def _event_json(e, mapper, intervals):
    at_ms = e.utc_ms if e.utc_ms is not None else LT.dt_to_ms(e.received_at)
    bell = mapper.bell_for(e.src, e.ch, at_ms) if e.ch is not None else None
    return {
        "at_ms": at_ms, "at_hms_ms": LT.local_hms_ms(at_ms),
        "bell_label": C.BELL_LABEL % bell if bell is not None else None,
        "interval_ms": intervals.get(e.id), "time_ok": time_ok(e.acc, e.sync),
        "id": e.id, "type": e.type, "src": e.src, "boot_id": e.boot_id,
        "seq": e.seq, "ch": e.ch, "bell": bell,
        "label": ch_label(e.ch) if e.ch is not None else None,
        "tick_ms": e.tick_ms, "utc_ms": e.utc_ms, "at_local": LT.local_iso(at_ms),
        "err_ms": e.err_ms, "sync": e.sync, "acc": e.acc, "mode": e.mode,
        "session": e.session, "body": e.body,
    }


def since(request):
    try:
        after = _int_arg(request, "after", None)
        limit = _int_arg(request, "limit", C.LIVE_LIMIT_DEFAULT)
    except ValueError:
        return _bad("after and limit must be integers")
    limit = max(1, min(limit, C.LIVE_LIMIT_MAX))
    src = request.GET.get("src") or None
    type_ = request.GET.get("type") or None
    rows = events_after(src, after, limit, type_)
    mapper = ChannelMapper.from_db()
    latest = rows[-1].id if rows else after
    intervals = stroke_intervals(rows)
    out = {"host": receiving_host(), "server_ms": _now_ms(), "latest_id": latest,
           "events": [_event_json(e, mapper, intervals) for e in rows]}
    strokes = [e for e in rows if e.type == C.TYPE_STROKE and e.ch is not None]
    if strokes:                       # only when something new arrived
        last = strokes[-1]
        ring = current_ring(last.src, last.boot_id, last.seq)
        if ring is not None:
            out["ring"] = ring_json(ring, mapper)
    return JsonResponse(out)


def days(request):
    try:
        today = LT.local_date(_now_ms())
        last = LT.parse_day(request.GET["to"]) if request.GET.get("to") else today
        first = (LT.parse_day(request.GET["from"]) if request.GET.get("from")
                 else last - (C.DAYS_DEFAULT - 1) * LT.ONE_DAY)
    except ValueError:
        return _bad("from/to must be YYYY-MM-DD")
    if first > last or (last - first).days + 1 > C.DAYS_MAX:
        return _bad("from..to must be 1..%d days" % C.DAYS_MAX)
    src = request.GET.get("src") or None
    start_ms = LT.day_bounds_ms(first)[0]
    end_ms = LT.day_bounds_ms(last)[1]
    mapper = ChannelMapper.from_db()
    by_day = {}
    for ring in rings_starting_between(src, start_ms, end_ms):
        day = LT.local_date(ring.first.at_ms)
        by_day.setdefault(day, []).append(ring_json(ring, mapper))
    out = []
    for day in sorted(by_day):
        rings = sorted(by_day[day], key=lambda r: r["start_ms"] or 0)
        out.append({"date": day.strftime(C.DATE_FORMAT),
                    "weekday": day.strftime("%a"), "rings": rings})
    return JsonResponse({"host": receiving_host(),
                         "from": first.strftime(C.DATE_FORMAT),
                         "to": last.strftime(C.DATE_FORMAT), "days": out})


def link(request):
    """The ingest's live view of the concentrator link, for the page 3
    widget.  The verdict (ok / stale / lost) is made here so the page
    shows exactly what the constants say."""
    now = _now_ms()
    doc, file_age = read_link_state()
    out = {"host": receiving_host(), "server_ms": now,
           "file_age_ms": file_age, "stale_ms": C.LINK_STALE_MS,
           "lost_ms": C.LINK_LOST_MS}
    out.update(link_verdict(doc, file_age, now))
    out["ingest"] = (doc or {}).get("ingest")
    out["pico"] = (doc or {}).get("pico")
    out["via"] = C.LINK_VIA_UDP
    wifi = out["verdict"]
    serial = serial_link(now, out)
    if serial:                        # Wi-Fi heartbeat not fresh: the USB serial one instead
        out.update(serial)
    mdoc, mage = read_ingest_status(midi_status_path())
    out["midi"] = (mdoc or {}).get("midi")
    midi = midi_verdict(mdoc, mage, now)
    if midi:                          # USB MIDI is live: say so, not the Wi-Fi verdict
        why = "%s (Wi-Fi: %s)" % (midi["why"], wifi)
        if serial:
            why += "; status via %s, heartbeat %d s ago" % (
                C.LINK_VIA_SERIAL, serial["hb_age_ms"] // C.MS_PER_S)
        out.update(midi, why=why)
        out["verdict"] = C.LINK_MIDI
    return JsonResponse(out)


def serial_link(now, udp):
    """The USB serial heartbeat (ingest_serial, serialingest.latest) in
    place of the Wi-Fi one, when the Wi-Fi heartbeat is not fresh (verdict
    not ok, or ok on packets with no heartbeat) and the serial one is
    (younger than its stale_ms).  -> the fields to change, or None (UDP
    stays as it was)."""
    if udp.get("verdict") == "ok" and udp.get("hb_age_ms") is not None:
        return None
    try:
        s = serialingest.latest(now)
    except Exception:
        return None
    if s is None or s["stale"] or s["age_ms"] is None:
        return None
    return {"verdict": "ok", "via": C.LINK_VIA_SERIAL, "pico": s["heartbeat"],
            "hb_age_ms": s["age_ms"], "wifi_verdict": udp.get("verdict"),
            "wifi_why": udp.get("why"),
            "serial": {"port": s["port"], "age_ms": s["age_ms"], "period_s": s["period_s"],
                       "stale_ms": s["stale_ms"]},
            "why": "via %s %s, heartbeat %d s ago (Wi-Fi: %s)" % (
                C.LINK_VIA_SERIAL, s["port"] or "", s["age_ms"] // C.MS_PER_S,
                udp.get("verdict"))}


def _age(now, ms):
    return None if ms is None else max(0, now - ms)


def midi_verdict(doc, file_age, now):
    """ingest_midi's status doc -> {"why", "midi_age_ms"} when USB MIDI is
    live (constants: MIDI_LIVE_MS), else None."""
    if doc is None or file_age is None or file_age > C.INGEST_STATUS_STALE_MS:
        return None
    m = doc.get("midi") or {}
    if not m.get("connected"):
        return None
    heard = [t for t in ((m.get("stamp") or {}).get("last_stamp_ms"), m.get("last_note_ms"))
             if t is not None]
    age = _age(now, max(heard)) if heard else None
    if age is None or age > C.MIDI_LIVE_MS:
        return None
    return {"why": "USB MIDI %s, heard %d s ago" % (m.get("port"), age // C.MS_PER_S),
            "midi_age_ms": age}


def link_verdict(doc, file_age, now):
    """-> {"verdict": "ok"|"stale"|"lost"|"no_ingest", "why": str,
    "hb_age_ms", "rx_age_ms"}."""
    if doc is None or file_age is None or file_age > C.INGEST_FILE_STALE_MS:
        return {"verdict": "no_ingest", "hb_age_ms": None, "rx_age_ms": None,
                "why": "ingest not running" if doc is None
                else "ingest not updating (%d s)" % (file_age // C.MS_PER_S)}
    i = doc.get("ingest") or {}
    hb_age = _age(now, i.get("last_heartbeat_ms"))
    rx_age = _age(now, i.get("last_frame_ms"))
    base = {"hb_age_ms": hb_age, "rx_age_ms": rx_age}
    if i.get("state") != C.LINK_CONNECTED:
        why = i.get("last_drop_reason") or i.get("last_error") or i.get("state")
        return dict(base, verdict="lost", why="ingest %s: %s" % (i.get("state"), why))
    if hb_age is None:
        # No heartbeat this run.  Judge by the last packet of any kind, so a
        # silent or unplugged Pico (or one whose heartbeats never arrive,
        # e.g. too big for one UDP datagram) goes STALE/LOST, never a
        # CONNECTED that nothing backs up.
        if rx_age is None:
            return dict(base, verdict="lost", why="nothing heard from the concentrator")
        if rx_age > C.LINK_LOST_MS:
            return dict(base, verdict="lost", why="no packet for %d s (no heartbeats)"
                        % (rx_age // C.MS_PER_S))
        if rx_age > C.LINK_STALE_MS:
            return dict(base, verdict="stale", why="no packet for %d s (no heartbeats)"
                        % (rx_age // C.MS_PER_S))
        return dict(base, verdict="ok", why="connected (packets, but no heartbeat "
                    "from the concentrator)")
    if hb_age > C.LINK_LOST_MS:
        return dict(base, verdict="lost", why="no heartbeat for %d s" % (hb_age // C.MS_PER_S))
    if hb_age > C.LINK_STALE_MS:
        return dict(base, verdict="stale", why="no heartbeat for %d s" % (hb_age // C.MS_PER_S))
    return dict(base, verdict="ok", why="connected")
