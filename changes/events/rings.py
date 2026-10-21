"""rings.py -- group strokes into displayed "rings" (pure).

A ring is consecutive strokes of one src + boot_id (in seq order) with no
pause longer than RING_GAP_MS between them, measured on tick_ms (always
present, monotonic within a boot).  The firmware's own session counter
is kept as a raw field; rings are what the pages show.
"""

from collections import namedtuple

from . import constants as C

# at_ms: utc_ms, or received time when the stroke was unsynced
Stroke = namedtuple("Stroke", "src boot_id seq ch tick_ms at_ms")


class Ring:
    def __init__(self, first):
        self.src, self.boot_id = first.src, first.boot_id
        self.strokes = [first]

    @property
    def first(self):
        return self.strokes[0]

    @property
    def last(self):
        return self.strokes[-1]

    @property
    def key(self):
        return "%s/%s/%d" % (self.src, self.boot_id, self.first.seq)

    def continues(self, s, gap_ms):
        return (s.src == self.src and s.boot_id == self.boot_id
                and s.tick_ms - self.last.tick_ms <= gap_ms)


def group_rings(strokes, gap_ms=C.RING_GAP_MS):
    """strokes: any order.  -> [Ring], ordered by (src, boot_id, seq)."""
    rings = []
    for s in sorted(strokes, key=lambda s: (s.src, s.boot_id, s.seq)):
        if rings and rings[-1].continues(s, gap_ms):
            rings[-1].strokes.append(s)
        else:
            rings.append(Ring(s))
    return rings


def summarise(ring, mapper, ch_label, events_in_span):
    """Dict for the JSON API.  events_in_span: rows of any type stored with
    seq in [first.seq, last.seq] for this boot (for coverage)."""
    per_ch, per_bell = {}, {}
    for s in ring.strokes:
        bell = mapper.bell_for(ring.src, s.ch, s.at_ms)
        c = per_ch.setdefault(s.ch, {"ch": s.ch, "bell": bell,
                                     "label": ch_label(s.ch), "strokes": 0})
        c["strokes"] += 1
        if bell is not None:
            b = per_bell.setdefault(bell, {"bell": bell, "chs": set(),
                                           "strokes": 0})
            b["chs"].add(s.ch)
            b["strokes"] += 1
    bells = [dict(b, chs=sorted(b["chs"])) for _, b in sorted(per_bell.items())]
    span = ring.last.seq - ring.first.seq + 1
    times = [s.at_ms for s in ring.strokes if s.at_ms is not None]
    return {
        "key": ring.key, "src": ring.src, "boot_id": ring.boot_id,
        "start_ms": min(times) if times else None,
        "end_ms": max(times) if times else None,
        "duration_s": (ring.last.tick_ms - ring.first.tick_ms) / C.MS_PER_S,
        "strokes": len(ring.strokes),
        "bells": bells,
        "channels": [per_ch[k] for k in sorted(per_ch)],
        "unmapped_chs": sorted(c for c, v in per_ch.items() if v["bell"] is None),
        "seq_first": ring.first.seq, "seq_last": ring.last.seq,
        "seq_missing": max(span - events_in_span, 0),
    }
