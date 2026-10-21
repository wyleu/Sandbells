"""store.py -- buffer parsed events, write them in batches.

    store = EventStore()
    store.add(parsed)        # flushes itself when a threshold is reached
    store.poll()             # call when idle: flushes if the interval passed
    store.flush()            # on shutdown

One bulk_create(ignore_conflicts=True) per batch: re-sent events
(same src, boot_id, seq) are dropped by the UNIQUE constraint.
"""

import time

from . import constants as C
from .models import Event, receiving_host


class EventStore:
    def __init__(self, flush_count=C.STORE_FLUSH_COUNT,
                 flush_interval_s=C.STORE_FLUSH_INTERVAL_S,
                 max_buffered=C.STORE_MAX_BUFFERED,
                 clock=time.monotonic, host=None):
        self.flush_count = int(flush_count)
        self.flush_interval_s = float(flush_interval_s)
        self.max_buffered = int(max_buffered)
        self.clock = clock
        self.host = receiving_host() if host is None else host
        self._buf = []
        self._oldest_at = None          # clock() when the buffer's first event came
        self.stats = {"added": 0, "written": 0, "flushes": 0, "dropped": 0,
                      "errors": 0}

    def __len__(self):
        return len(self._buf)

    def add(self, parsed):
        """Buffer one ParsedEvent.  Returns rows submitted if it flushed."""
        if not self._buf:
            self._oldest_at = self.clock()
        self._buf.append(Event.from_parsed(parsed, host=self.host))
        self.stats["added"] += 1
        self._trim()
        if len(self._buf) >= self.flush_count:
            return self.flush()
        return self.poll()

    def due(self):
        return (bool(self._buf) and
                self.clock() - self._oldest_at >= self.flush_interval_s)

    def poll(self):
        """Flush if the oldest buffered event has waited long enough."""
        return self.flush() if self.due() else 0

    def flush(self):
        """Write everything buffered.  On a DB error the buffer is kept
        (for a later retry) and the error is re-raised."""
        if not self._buf:
            return 0
        batch = self._buf
        try:
            Event.objects.bulk_create(batch, ignore_conflicts=True)
        except Exception:
            self.stats["errors"] += 1
            raise
        self._buf = []
        self._oldest_at = None
        self.stats["written"] += len(batch)
        self.stats["flushes"] += 1
        return len(batch)

    def _trim(self):
        extra = len(self._buf) - self.max_buffered
        if extra > 0:
            del self._buf[:extra]
            self.stats["dropped"] += extra
