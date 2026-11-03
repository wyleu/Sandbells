"""views.py -- server-rendered pages (no JS libraries).  UK local time.

  /events/days/[?date=YYYY-MM-DD]          days with strokes, rings of one day
  /events/ring/<src>/<boot_id>/<seq>/      strokes of one ring (the Strokes page's list)
  /events/strokes/                         the live stroke list, full width
  /events/ingest/                          the ingest: units, counters, last datagram
"""

import time

from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import render

from . import constants as C
from . import ingestpage
from . import localtime as LT
from .api import _event_json
from .mapping import ChannelMapper
from .models import Event, receiving_host
from .queries import (ring_from, ring_json, rings_starting_between, stroke_days,
                      stroke_intervals)


def _now_ms():
    return int(time.time() * C.MS_PER_S)


def strokes_page(request):
    """The live stroke list on a page of its own, the whole screen wide, so the
    beat column (early / lead left, late / lag right) has room.  Everything on
    it comes from Sandbells: /events/api/since/ (the stored stroke events) and
    /events/api/link/ (the ingest's tmpfs file).  Nothing here asks a device
    for its /status, and there is no socket to a Pico."""
    return render(request, "events/strokes.html")


def ingest_page(request):
    """Is the event ingest there, running and set up right?  Read-only:
    systemctl is-enabled / is-active (short timeout), ingest_udp's status
    file (tmpfs, never the ingest process itself), the newest stored stroke.
    Reloads itself every INGEST_PAGE_REFRESH_S; no JS."""
    ctx = ingestpage.page_context()
    ctx["host"] = receiving_host()
    return render(request, "events/ingest.html", ctx)


def days_page(request):
    src = request.GET.get("src") or None
    today = LT.local_date(_now_ms())
    first = today - (C.DAYS_MAX - 1) * LT.ONE_DAY
    counts = stroke_days(src, LT.day_bounds_ms(first)[0], LT.day_bounds_ms(today)[1])
    days = [{"date": d, "iso": d.strftime(C.DATE_FORMAT), "label": LT.day_label(d),
             "strokes": n} for d, n in sorted(counts.items(), reverse=True)]
    if request.GET.get("date"):
        try:
            chosen = LT.parse_day(request.GET["date"])
        except ValueError:
            return HttpResponseBadRequest("date must be YYYY-MM-DD")
    else:
        chosen = days[0]["date"] if days else today
    start_ms, end_ms = LT.day_bounds_ms(chosen)
    mapper = ChannelMapper.from_db()
    rings = [ring_json(r, mapper)
             for r in rings_starting_between(src, start_ms, end_ms)]
    rings.sort(key=lambda r: r["start_ms"] or 0)
    for r in rings:
        r["bell_rows"] = _bell_rows(r)
    return render(request, "events/days.html", {
        "host": receiving_host(), "days": days,
        "chosen_iso": chosen.strftime(C.DATE_FORMAT),
        "chosen_label": LT.day_label(chosen), "rings": rings,
        "ring_gap_min": C.RING_GAP_MS // C.MS_PER_MINUTE,
    })


def _bell_rows(ring):
    """Display lines for the Bells cell: 'Bell 8' (+ two-heads counts),
    then each channel's strokes while it had no bell as 'ch N'."""
    rows = []
    for b in ring["bells"]:
        heads = ["ch %d: %d" % (ch, n) for ch, n in b["per_ch"].items()]
        rows.append({"name": "Bell %d" % b["bell"], "strokes": b["strokes"],
                     "heads": heads if len(heads) > 1 else []})
    for c in ring["channels"]:
        if c["unmapped"]:                # its strokes while it had no bell
            rows.append({"name": c["label"], "strokes": c["unmapped"], "heads": []})
    return rows


def ring_page(request, src, boot_id, first_seq):
    """One stored ring, drawn by the Strokes page's own panel and list
    (live_panel.html, live_list.js) from the same event JSON as
    /events/api/since/, full width; no polling, no link widget or clock."""
    ring = ring_from(src, boot_id, first_seq)
    if ring is None:
        raise Http404("no ring starts at %s/%s/%d" % (src, boot_id, first_seq))
    mapper = ChannelMapper.from_db()
    rows = list(Event.objects.defer("raw")
                .filter(src=src, boot_id=boot_id, type=C.TYPE_STROKE, ch__isnull=False,
                        seq__gte=ring.first.seq, seq__lte=ring.last.seq)
                .order_by("-seq")[:C.RING_TABLE_MAX_ROWS])[::-1]   # the last ones, oldest first
    intervals = stroke_intervals(rows)
    summary = ring_json(ring, mapper)
    day = LT.local_date(ring.first.at_ms)
    return render(request, "events/strokes.html", {"ring": {
        "summary": summary,
        "data": {"ring": summary, "events": [_event_json(e, mapper, intervals) for e in rows]},
        "truncated": len(ring.strokes) > len(rows), "max_rows": C.RING_TABLE_MAX_ROWS,
        "day_iso": day.strftime(C.DATE_FORMAT), "day_label": LT.day_label(day),
    }})
