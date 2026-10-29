"""views.py -- server-rendered pages (no JS libraries).  UK local time.

  /events/days/[?date=YYYY-MM-DD]          days with strokes, rings of one day
  /events/ring/<src>/<boot_id>/<seq>/      strokes of one ring (table)
  /events/strokes/                         the live stroke list, full width
"""

import time

from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import render

from . import constants as C
from . import localtime as LT
from .mapping import ChannelMapper
from .models import receiving_host
from .queries import ring_from, ring_json, rings_starting_between, stroke_days


def _now_ms():
    return int(time.time() * C.MS_PER_S)


def strokes_page(request):
    """The live stroke list on a page of its own, the whole screen wide, so the
    beat column (early / lead left, late / lag right) has room.  Everything on
    it comes from Sandbells: /events/api/since/ (the stored stroke events) and
    /events/api/link/ (the ingest's tmpfs file).  Nothing here asks a device
    for its /status, and there is no socket to a Pico."""
    return render(request, "events/strokes.html")


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
    then unmapped channels as 'ch N'."""
    rows = []
    for b in ring["bells"]:
        heads = ["ch %d: %d" % (ch, n) for ch, n in b["per_ch"].items()]
        rows.append({"name": "Bell %d" % b["bell"], "strokes": b["strokes"],
                     "heads": heads if len(heads) > 1 else []})
    for c in ring["channels"]:
        if c["bell"] is None:
            rows.append({"name": c["label"], "strokes": c["strokes"], "heads": []})
    return rows


def ring_page(request, src, boot_id, first_seq):
    ring = ring_from(src, boot_id, first_seq)
    if ring is None:
        raise Http404("no ring starts at %s/%s/%d" % (src, boot_id, first_seq))
    mapper = ChannelMapper.from_db()
    summary = ring_json(ring, mapper)
    summary["bell_rows"] = _bell_rows(summary)
    last_tick = {}                       # ch -> tick_ms of its previous stroke
    rows = []
    for s in ring.strokes[:C.RING_TABLE_MAX_ROWS]:
        prev = last_tick.get(s.ch)
        last_tick[s.ch] = s.tick_ms
        bell = mapper.bell_for(src, s.ch, s.at_ms)
        rows.append({"time": LT.local_hms_ms(s.at_ms), "seq": s.seq,
                     "bell": bell, "ch": s.ch,
                     "interval_ms": None if prev is None else s.tick_ms - prev})
    day = LT.local_date(ring.first.at_ms)
    return render(request, "events/ring.html", {
        "host": receiving_host(), "ring": summary, "rows": rows,
        "truncated": len(ring.strokes) > C.RING_TABLE_MAX_ROWS,
        "max_rows": C.RING_TABLE_MAX_ROWS,
        "day_iso": day.strftime(C.DATE_FORMAT), "day_label": LT.day_label(day),
    })
