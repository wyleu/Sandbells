"""mapping.py -- channel -> bell at a given time (pure).

Rows are (src, ch, bell, valid_from_ms); the latest row at or before the
stroke time wins.  bell None = unmapped.  Many channels may share a bell.
"""

from bisect import bisect_right

from . import constants as C


class ChannelMapper:
    def __init__(self, rows=()):
        self._by_key = {}            # (src, ch) -> ([from_ms...], [bell...])
        for src, ch, bell, from_ms in sorted(rows, key=lambda r: r[3]):
            froms, bells = self._by_key.setdefault((src, ch), ([], []))
            froms.append(from_ms)
            bells.append(bell)

    @classmethod
    def from_db(cls):
        from .models import ChannelMap
        return cls((m.src, m.ch, m.bell, m.valid_from_ms)
                   for m in ChannelMap.objects.all())

    def bell_for(self, src, ch, at_ms):
        """Bell number or None.  at_ms None: the latest mapping."""
        entry = self._by_key.get((src, ch))
        if entry is None or ch is None:
            return None
        froms, bells = entry
        i = len(froms) if at_ms is None else bisect_right(froms, at_ms)
        return bells[i - 1] if i else None


def ch_label(ch):
    return C.CH_LABEL % ch
