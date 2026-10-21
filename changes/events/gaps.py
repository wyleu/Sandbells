"""gaps.py -- spot lost, repeated and late events from their seq numbers.

Pure Python, no DB.  Each src has a current boot_id; seq counts up from
SEQ_FIRST within a boot.  A new boot_id is a reset, not a gap.

    tracker = GapTracker()
    obs = tracker.observe(p.src, p.boot_id, p.seq)
    if obs.missing: log(obs)          # (first_missing, last_missing)
"""

from dataclasses import dataclass

from . import constants as C


@dataclass(frozen=True)
class Observation:
    kind: str                 # constants.GAP_*
    src: str
    boot_id: str
    seq: int
    missing: tuple = None     # (first, last) inclusive, or None

    @property
    def missing_count(self):
        return 0 if self.missing is None else self.missing[1] - self.missing[0] + 1


def _from_start(seq):
    """Missing range before the first seq seen of a boot, or None."""
    return (C.SEQ_FIRST, seq - 1) if seq > C.SEQ_FIRST else None


class GapTracker:
    def __init__(self):
        self._boot = {}           # src -> current boot_id
        self._last = {}           # (src, boot_id) -> highest seq seen
        self.counts = {}          # kind -> number of observations
        self.missing_total = 0

    def observe(self, src, boot_id, seq):
        obs = self._classify(src, boot_id, seq)
        self.counts[obs.kind] = self.counts.get(obs.kind, 0) + 1
        self.missing_total += obs.missing_count
        return obs

    def _classify(self, src, boot_id, seq):
        key = (src, boot_id)
        last = self._last.get(key)
        if last is None:
            kind = C.GAP_FIRST if src not in self._boot else C.GAP_RESET
            self._boot[src] = boot_id
            self._last[key] = seq
            return Observation(kind, src, boot_id, seq, _from_start(seq))
        if seq == last + 1:
            self._last[key] = seq
            return Observation(C.GAP_OK, src, boot_id, seq)
        if seq > last + 1:
            self._last[key] = seq
            return Observation(C.GAP_GAP, src, boot_id, seq, (last + 1, seq - 1))
        if seq == last:
            return Observation(C.GAP_DUPLICATE, src, boot_id, seq)
        return Observation(C.GAP_OUT_OF_ORDER, src, boot_id, seq)
