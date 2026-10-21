"""queries.py -- DB reads for the pages (rings per local day, live list).

Light for the Pi 3: values_list rows only, the utc_ms index for day
windows, the UNIQUE(src, boot_id, seq) index for ring tails and coverage.
"""

from . import constants as C
from . import localtime as LT
from .models import Event
from .rings import Stroke, group_rings

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


def events_after(src, after_id, limit):
    """Newest-last list of Event rows: id > after_id, or the latest limit."""
    qs = Event.objects.all()
    if src:
        qs = qs.filter(src=src)
    if after_id is None:
        return list(reversed(qs.order_by("-id")[:limit]))
    return list(qs.filter(id__gt=after_id).order_by("id")[:limit])
