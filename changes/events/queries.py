"""queries.py -- DB reads for the pages (rings per local day, live list).

Light for the Pi 3: values_list rows only, the utc_ms index for day
windows, the UNIQUE(src, boot_id, seq) index for ring tails and coverage.
"""

import threading

from . import constants as C
from . import localtime as LT
from .mapping import ch_label
from .models import Event
from .rings import Ring, Stroke, group_rings, summarise

STROKE_FIELDS = ("src", "boot_id", "seq", "ch", "tick_ms")
TAIL_CHUNK = 500


def _strokes(src):
    qs = Event.objects.filter(type=C.TYPE_STROKE, ch__isnull=False)
    return qs.filter(src=src) if src else qs


def strokes_between(src, start_ms, end_ms):
    """Strokes with wall time in [start_ms, end_ms).  Unsynced strokes
    (utc_ms null) are placed by their received time."""
    synced = _strokes(src).filter(utc_ms__gte=start_ms, utc_ms__lt=end_ms)
    for row in synced.values_list(*STROKE_FIELDS, "utc_ms"):
        yield Stroke(*row)
    unsynced = _strokes(src).filter(
        utc_ms__isnull=True,
        received_at__gte=LT.UNIX_EPOCH + start_ms * LT.ONE_MS,
        received_at__lt=LT.UNIX_EPOCH + end_ms * LT.ONE_MS)
    for row in unsynced.values_list(*STROKE_FIELDS, "received_at"):
        yield Stroke(*row[:-1], LT.dt_to_ms(row[-1]))


def _extend_tail(ring, gap_ms):
    """A ring near the window end may go on past it: follow the boot's
    later strokes by seq until the next pause longer than gap_ms."""
    later = (_strokes(ring.src).filter(boot_id=ring.boot_id, seq__gt=ring.last.seq)
             .order_by("seq").values_list(*STROKE_FIELDS, "utc_ms", "received_at"))
    for row in later.iterator(chunk_size=TAIL_CHUNK):
        utc, received = row[-2], row[-1]
        s = Stroke(*row[:-2], utc if utc is not None else LT.dt_to_ms(received))
        if not ring.continues(s, gap_ms):
            return
        ring.strokes.append(s)


def events_in_span(ring):
    """Stored events of any type in the ring's seq span (for coverage)."""
    return Event.objects.filter(src=ring.src, boot_id=ring.boot_id,
                                seq__gte=ring.first.seq,
                                seq__lte=ring.last.seq).count()


def rings_starting_between(src, start_ms, end_ms, gap_ms=C.RING_GAP_MS):
    """Rings whose FIRST stroke is in [start_ms, end_ms), complete even if
    they run past end_ms.  A ring already going at start_ms belongs to the
    earlier window, so strokes from gap_ms before are read to see it."""
    rings = group_rings(strokes_between(src, start_ms - gap_ms, end_ms), gap_ms)
    out = [r for r in rings if start_ms <= r.first.at_ms < end_ms]
    for r in out:
        if r.last.at_ms >= end_ms - gap_ms:
            _extend_tail(r, gap_ms)
    return out


def events_after(src, after_id, limit, type_=None):
    """Newest-last list of Event rows: id > after_id, or the latest limit.
    Walks the primary key (id) only; raw JSON is not loaded."""
    qs = Event.objects.defer("raw")
    if src:
        qs = qs.filter(src=src)
    if type_:
        qs = qs.filter(type=type_)
    if after_id is None:
        return list(reversed(qs.order_by("-id")[:limit]))
    return list(qs.filter(id__gt=after_id).order_by("id")[:limit])


def ring_json(ring, mapper):
    """summarise() plus local-time labels and coverage from the DB."""
    d = summarise(ring, mapper, ch_label, events_in_span(ring))
    d.update(start_local=LT.local_iso(d["start_ms"]),
             end_local=LT.local_iso(d["end_ms"]),
             start_hms=LT.local_hms(d["start_ms"]),
             end_hms=LT.local_hms(d["end_ms"]),
             duration=LT.format_duration(d["duration_s"]),
             first_seq=ring.first.seq)
    return d


def stroke_days(src, start_ms, end_ms):
    """{local date: stroke events} for strokes in [start_ms, end_ms)."""
    out = {}
    for s in strokes_between(src, start_ms, end_ms):
        day = LT.local_date(s.at_ms)
        out[day] = out.get(day, 0) + 1
    return out


def ring_from(src, boot_id, first_seq, gap_ms=C.RING_GAP_MS):
    """The ring that starts at this stroke, or None if there is no stroke
    with that seq.  Followed by seq until a pause longer than gap_ms."""
    rows = (_strokes(src).filter(boot_id=boot_id, seq__gte=first_seq)
            .order_by("seq").values_list(*STROKE_FIELDS, "utc_ms", "received_at"))
    ring = None
    for row in rows.iterator(chunk_size=TAIL_CHUNK):
        utc, received = row[-2], row[-1]
        s = Stroke(*row[:-2], utc if utc is not None else LT.dt_to_ms(received))
        if ring is None:
            if s.seq != first_seq:
                return None
            ring = Ring(s)
        elif ring.continues(s, gap_ms):
            ring.strokes.append(s)
        else:
            break
    return ring


def _stroke_from(row):
    utc, received = row[-2], row[-1]
    return Stroke(*row[:-2], utc if utc is not None else LT.dt_to_ms(received))


def _prev_tick(e):
    """tick_ms of the previous stroke on the same src/boot/ch (bounded scan
    of the UNIQUE(src, boot_id, seq) index), or None."""
    return (_strokes(e.src)
            .filter(boot_id=e.boot_id, ch=e.ch, seq__lt=e.seq,
                    seq__gte=e.seq - C.LIVE_PREV_SEQ_SPAN)
            .order_by("-seq").values_list("tick_ms", flat=True).first())


def stroke_intervals(rows, gap_ms=C.RING_GAP_MS):
    """{event id: ms since the previous stroke on the same src/boot/ch}.
    None when there is none, or it is more than a ring gap back.
    rows: Event objects, oldest first."""
    prev, out = {}, {}
    for e in rows:
        if e.type != C.TYPE_STROKE or e.ch is None:
            continue
        k = (e.src, e.boot_id, e.ch)
        if k not in prev:
            prev[k] = _prev_tick(e)
        d = None if prev[k] is None else e.tick_ms - prev[k]
        out[e.id] = d if d is not None and 0 <= d <= gap_ms else None
        prev[k] = e.tick_ms
    return out


def _walk_back(src, boot_id, seq, gap_ms):
    """The ring that ends at (or runs through) this stroke, read backwards."""
    rows = (_strokes(src).filter(boot_id=boot_id, seq__lte=seq).order_by("-seq")
            .values_list(*STROKE_FIELDS, "utc_ms", "received_at"))
    back = []
    for row in rows.iterator(chunk_size=TAIL_CHUNK):
        s = _stroke_from(row)
        if back and back[-1].tick_ms - s.tick_ms > gap_ms:
            break
        back.append(s)
    if not back:
        return None
    ring = Ring(back[-1])
    ring.strokes = back[::-1]
    return ring


_ring_lock = threading.Lock()
_ring_cache = {}            # {"ring": Ring} -- the latest one only


def reset_ring_cache():
    with _ring_lock:
        _ring_cache.clear()


def current_ring(src, boot_id, seq, gap_ms=C.RING_GAP_MS):
    """Ring holding stroke (src, boot_id, seq).  The last one is cached and
    only its new tail is read, so a long peal is not re-read every poll."""
    with _ring_lock:
        ring = _ring_cache.get("ring")
        if (ring is not None and (ring.src, ring.boot_id) == (src, boot_id)
                and ring.last.seq <= seq):
            _extend_tail(ring, gap_ms)
            if ring.last.seq < seq:      # a pause: seq starts a newer ring
                ring = None
        else:
            ring = None
        if ring is None:
            ring = _walk_back(src, boot_id, seq, gap_ms)
        if ring is None:
            return None
        _ring_cache["ring"] = ring
        snapshot = Ring(ring.first)          # callers read it outside the lock
        snapshot.strokes = list(ring.strokes)
        return snapshot
