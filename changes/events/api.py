"""api.py -- JSON endpoints for the pages.  All times shown are UK local.

  GET /events/api/since/?after=<id>&src=&type=&limit=
                                                    live event list
  GET /events/api/days/?from=YYYY-MM-DD&to=YYYY-MM-DD&src=
                                                    rings per local day
"""

import time

from django.http import JsonResponse

from . import constants as C
from . import localtime as LT
from .mapping import ChannelMapper, ch_label
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
