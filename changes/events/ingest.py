"""ingest.py -- one text frame -> parse -> GapTracker -> EventStore.

No network here: wsclient.py feeds frames in and calls idle() when the
socket is quiet.  Logging is a periodic summary, plus a WARNING for each
gap and at most one WARNING per reject reason per REJECT_LOG_INTERVAL_S.

The first frame of each (src, boot_id) seeds the GapTracker from the DB
(max stored seq, one query on the UNIQUE(src, boot_id, seq) index), so a
restart does not report already-stored seqs as missed.  Events still in
the store's buffer are known to the in-process tracker already.
"""

import logging
import time

from . import constants as C
from .gaps import GapTracker
from .parse import ParseError, parse


def stored_max_seq(src, boot_id):
    """Highest seq in the DB for this boot, or None."""
    from django.db.models import Max
    from .models import Event
    return (Event.objects.filter(src=src, boot_id=boot_id)
            .aggregate(m=Max("seq"))["m"])

log = logging.getLogger(C.LOGGER_NAME)


class Ingest:
    def __init__(self, store, tracker=None, clock=time.monotonic,
                 summary_interval_s=C.SUMMARY_INTERVAL_S,
                 reject_log_interval_s=C.REJECT_LOG_INTERVAL_S,
                 last_stored=stored_max_seq):
        self.store = store
        self.last_stored = last_stored
        self.tracker = tracker or GapTracker()
        self.clock = clock
        self.summary_interval_s = float(summary_interval_s)
        self.reject_log_interval_s = float(reject_log_interval_s)
        self.frames = 0
        self.ignored = 0              # frames of IGNORED_SCHEMAS (not stored)
        self.rejects = {}             # reason -> count
        self._reject_logged_at = {}   # reason -> clock() of last WARNING
        self._summary_at = clock()

    # ---- frames ---------------------------------------------------------
    def handle_frame(self, text):
        self.frames += 1
        try:
            p = parse(text)
        except ParseError as e:
            if e.reason == C.R_IGNORED:          # e.g. sand.panel/v1 mimic frames
                self.ignored += 1
                return None
            self._reject(e)
            return None
        self._seed_from_db(p.src, p.boot_id)
        obs = self.tracker.observe(p.src, p.boot_id, p.seq)
        if obs.kind == C.GAP_GAP:
            log.warning("gap %s/%s: missing seq %d-%d (%d)", p.src, p.boot_id,
                        obs.missing[0], obs.missing[1], obs.missing_count)
        elif obs.kind in (C.GAP_FIRST, C.GAP_RESET):
            log.info("%s %s/%s at seq %d%s", obs.kind, p.src, p.boot_id, p.seq,
                     " (missed %d-%d)" % obs.missing if obs.missing else "")
        self._write(self.store.add, p)
        return obs

    def idle(self):
        """Socket quiet: flush if due, emit the summary if due."""
        self._write(self.store.poll)
        self.maybe_summary()

    def flush(self):
        """Write everything buffered (disconnect, shutdown)."""
        return self._write(self.store.flush)

    # ---- logging --------------------------------------------------------
    def maybe_summary(self):
        now = self.clock()
        if now - self._summary_at < self.summary_interval_s:
            return False
        self._summary_at = now
        log.info(self.summary())
        return True

    def summary(self):
        c, s = self.tracker.counts, self.store.stats
        return ("frames %d, ignored %d, accepted %d, submitted %d, buffered %d, "
                "rejected %d %s, "
                "gaps %d (missing %d), dup %d, late %d, resets %d, dropped %d"
                % (self.frames, self.ignored, s["added"], s["written"], len(self.store),
                   sum(self.rejects.values()), self.rejects or "",
                   c.get(C.GAP_GAP, 0), self.tracker.missing_total,
                   c.get(C.GAP_DUPLICATE, 0), c.get(C.GAP_OUT_OF_ORDER, 0),
                   c.get(C.GAP_RESET, 0), s["dropped"]))

    def _seed_from_db(self, src, boot_id):
        if self.tracker.knows(src, boot_id):
            return
        try:
            last = self.last_stored(src, boot_id)
        except Exception as e:
            log.warning("resume lookup %s/%s failed: %s", src, boot_id, e)
            return
        if last is not None and self.tracker.seed(src, boot_id, last):
            log.info("resume %s/%s after seq %d (stored)", src, boot_id, last)

    def _reject(self, err):
        self.rejects[err.reason] = self.rejects.get(err.reason, 0) + 1
        now = self.clock()
        last = self._reject_logged_at.get(err.reason)
        if last is None or now - last >= self.reject_log_interval_s:
            self._reject_logged_at[err.reason] = now
            log.warning("reject %s (total %d for this reason)", err,
                        self.rejects[err.reason])

    def _write(self, fn, *args):
        """Run a store call; a DB error is logged, the buffer is kept."""
        try:
            n = fn(*args)
        except Exception as e:
            log.error("store write failed (%d buffered, will retry): %s",
                      len(self.store), e)
            return 0
        if n:
            log.debug("submitted %d events (duplicates ignored by the DB)", n)
        return n
