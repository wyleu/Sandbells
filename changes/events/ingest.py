"""ingest.py -- one text frame -> parse -> GapTracker -> EventStore.

No network here: wsclient.py feeds frames in and calls idle() when the
socket is quiet.  Logging is a periodic summary, plus a WARNING for each
gap and at most one WARNING per reject reason per REJECT_LOG_INTERVAL_S.

A frame that cannot be decoded (not UTF-8 / not JSON, e.g. a heartbeat cut
off mid-string) is a "bad frame": skipped, counted, one rate-limited
WARNING with its length and first/last bytes.  framestate.FrameGuard (a
transition table) decides when enough in a row mean the link is bad; the
reason is then left in drop_reason for wsclient, which closes the socket.

The first frame of each (src, boot_id) seeds the GapTracker from the DB
(max stored seq, one query on the UNIQUE(src, boot_id, seq) index), so a
restart does not report already-stored seqs as missed.  Events still in
the store's buffer are known to the in-process tracker already.

Link health: sand.panel/v1 heartbeats from the Pico are not stored; they
update the LinkState (page 3 widget).  note() stores this side's own
"ingest" events (connected, disconnected, connect_failed, started,
stopped) in the same table, src INGEST_SRC, with their own boot_id/seq,
so a link drop leaves a record on both ends.
"""

import json
import logging
import os
import socket
import time

from . import constants as C
from .gaps import GapTracker
from .framestate import FrameGuard
from .linkstate import LinkState
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
                 last_stored=stored_max_seq, link=None, wall=time.time):
        self.store = store
        self.link = link if link is not None else LinkState(None)
        self.wall = wall
        self.pico_heartbeats = 0      # sand.panel/v1 heartbeats seen (wsclient)
        self._note_boot = os.urandom(4).hex()
        self._note_seq = 0
        self.last_stored = last_stored
        self.tracker = tracker or GapTracker()
        self.clock = clock
        self.summary_interval_s = float(summary_interval_s)
        self.reject_log_interval_s = float(reject_log_interval_s)
        self.frames = 0
        self.ignored = 0              # frames of IGNORED_SCHEMAS (not stored)
        self.bad = 0                  # frames that could not be decoded (skipped)
        self.guard = FrameGuard()
        self.drop_reason = None       # set when the guard says: drop the link
        self._bad_logged_at = None
        self._bad_unlogged = 0        # bad frames since the last WARNING
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
                self._good_frame()
                self._panel_frame(text)
                return None
            self._reject(e, quiet=e.reason in C.DECODE_REASONS)
            if e.reason in C.DECODE_REASONS:
                self._bad_frame(text, e.reason)
            else:
                self._good_frame()
            self.link.frame(False)
            return None
        self._good_frame()
        self.link.frame(True)
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

    def bad_frame(self, data, why=C.BAD_FRAME_WHY_TRANSPORT):
        """A frame the WebSocket layer could not decode (wsclient): the
        bytes stand in for the text.  True if the link should be dropped."""
        self.frames += 1
        self._bad_frame(data, why)
        self.link.frame(False)
        return self.drop_reason is not None

    def new_connection(self):
        """A fresh socket: consecutive bad frames start again from 0."""
        self.guard.reset()
        self.drop_reason = None

    def idle(self):
        """Socket quiet: flush if due, emit the summary if due."""
        self._write(self.store.poll)
        self.maybe_summary()
        self.link.maybe_write()

    def _panel_frame(self, text):
        """sand.panel/v1: a heartbeat (LED mimic, link, sync) -> LinkState."""
        try:
            doc = json.loads(text)
        except ValueError:
            return
        if isinstance(doc, dict) and doc.get(C.F_TYPE) == C.TYPE_HEARTBEAT:
            self.pico_heartbeats += 1
            self.link.heartbeat(doc)
        else:
            self.link.frame(False)

    # ---- this side's own events -----------------------------------------
    def note(self, what, **body):
        """Store an "ingest" event (sand.event/v1, src INGEST_SRC) and log it."""
        self._note_seq += 1
        body = dict(body, what=what)
        doc = {C.F_SCHEMA: C.SCHEMA_EVENT_V1, C.F_TYPE: C.TYPE_INGEST,
               C.F_SRC: C.INGEST_SRC,
               C.F_ID: socket.gethostname().split(".")[0][:C.DEVICE_ID_MAX_LEN],
               C.F_BOOT_ID: self._note_boot, C.F_SEQ: self._note_seq,
               C.F_TICK_MS: int(time.monotonic() * C.MS_PER_S),
               C.F_UTC_MS: int(self.wall() * C.MS_PER_S),   # the Pi's chrony clock
               C.F_BODY: body}
        log.info("ingest %s %s", what, body)
        try:
            p = parse(json.dumps(doc))
        except ParseError as e:                   # cannot happen; never raise
            log.error("ingest note not stored: %s", e)
            return None
        self._write(self.store.add, p)
        return p

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
        return ("frames %d, ignored %d, bad %d, accepted %d, submitted %d, buffered %d, "
                "rejected %d %s, "
                "gaps %d (missing %d), dup %d, late %d, resets %d, dropped %d"
                % (self.frames, self.ignored, self.bad, s["added"], s["written"], len(self.store),
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

    # ---- frames that cannot be decoded ------------------------------------
    def _good_frame(self):
        self._do(self.guard.feed(C.FRAME_GOOD), None, None)

    def _bad_frame(self, data, why):
        self.bad += 1
        self._do(self.guard.feed(C.FRAME_BAD), data, why)

    def _do(self, actions, data, why):
        """Run the actions of one table row (framestate.py)."""
        for name in actions:
            self._actions[name](self, data, why)

    def _act_reset(self, data, why):
        pass                                  # the table already set state 0

    def _act_count(self, data, why):
        """Skip it: one rate-limited WARNING (length, first/last bytes)."""
        now = self.clock()
        last = self._bad_logged_at
        if last is not None and now - last < C.BAD_FRAME_LOG_INTERVAL_S:
            self._bad_unlogged += 1
            return
        raw = data.encode(C.TEXT_ENCODING, "replace") if isinstance(data, str) else bytes(data)
        n = C.BAD_FRAME_EXCERPT_BYTES
        log.warning("bad frame skipped (%s): len %d, first %d %r, last %d %r "
                    "(%d in a row, %d total, %d more not logged)",
                    why, len(raw), n, raw[:n], n, raw[-n:],
                    self.guard.state, self.bad, self._bad_unlogged)
        self._bad_logged_at = now
        self._bad_unlogged = 0

    def _act_disconnect(self, data, why):
        self.drop_reason = "%d bad frames in a row" % self.guard.state

    _actions = {C.ACT_RESET: _act_reset, C.ACT_COUNT: _act_count,
                C.ACT_DISCONNECT: _act_disconnect}

    def _reject(self, err, quiet=False):
        self.rejects[err.reason] = self.rejects.get(err.reason, 0) + 1
        if quiet:                     # the "bad frame" WARNING covers it
            return
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
