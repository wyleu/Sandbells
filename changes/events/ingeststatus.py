"""ingeststatus.py -- ingest_udp's own counters, for the Ingest page.

The ingest process and the web workers (gunicorn) are different processes,
so, like linkstate.py, the numbers go through one small JSON file on tmpfs
(INGEST_STATUS_PATH, the ingest unit's RuntimeDirectory), written
atomically (temp file + os.replace).  Never stored in the DB.

Nothing here may hold up or break the receive loop: every method catches
its own errors (logged once), the work per datagram is a few dict stores,
and the file is written at most once per INGEST_STATUS_CHANGE_S while
datagrams come in, and every INGEST_STATUS_WRITE_S when quiet.

    status = IngestStatus(path, mode="udp", host=..., port=...)
    status.datagram(peer)                 # every datagram (Ingest.handle_frame)
    status.identity(uid=, boot_id=, ...)  # what the datagram said it was
    status.rejected(reason, data, peer)   # a datagram that was not stored
    status.maybe_write(ingest)            # snapshot ingest's counters
    status.stopped(ingest)                # on the way out
    read_ingest_status(path)              # the view: -> (doc or None, age ms)
"""

import collections
import json
import logging
import os
import tempfile
import time

from . import constants as C

log = logging.getLogger(C.LOGGER_NAME)


def ingest_status_path():
    return os.environ.get(C.INGEST_STATUS_ENV) or C.INGEST_STATUS_PATH


def _ms(wall):
    return int(wall() * C.MS_PER_S)


def _excerpt(data):
    if isinstance(data, (bytes, bytearray)):
        data = bytes(data).decode(C.TEXT_ENCODING, "replace")
    text = str(data)
    n = C.INGEST_STATUS_EXCERPT
    return text if len(text) <= n else text[:n] + "…"


class IngestStatus:
    def __init__(self, path=None, mode=C.INGEST_MODE_UDP, host=None, port=None,
                 wall=time.time, clock=time.monotonic,
                 write_s=C.INGEST_STATUS_WRITE_S,
                 change_s=C.INGEST_STATUS_CHANGE_S,
                 recent=C.INGEST_STATUS_RECENT):
        self.path = path
        self.wall = wall
        self.clock = clock
        self.write_s = float(write_s)
        self.change_s = float(change_s)
        self._written_at = None
        self._changed = True
        self._failed = False
        self.writes = 0
        self.recent = collections.deque(maxlen=int(recent))
        self.last = {"ms": None, "peer": None, "uid": None, "boot_id": None,
                     "src": None, "type": None, "seq": None}
        self.doc = {
            "schema": C.INGEST_STATUS_SCHEMA,
            "state": C.INGEST_STATE_RUNNING,
            "mode": mode, "host": host, "port": port,
            "pid": os.getpid(), "started_ms": _ms(wall),
            "counters": {}, "last": self.last, "recent_rejects": [],
            "written_ms": None,
        }

    def _oops(self, what, e):
        if not self._failed:                  # once, not every datagram
            log.warning("ingest status %s failed: %s", what, e)
        self._failed = True

    # ---- per datagram (cheap, never raises) ------------------------------
    def datagram(self, peer):
        try:
            self.last.update(ms=_ms(self.wall), peer=peer, uid=None,
                             boot_id=None, src=None, type=None, seq=None)
            self._changed = True
        except Exception as e:               # pragma: no cover - cannot happen
            self._oops("datagram", e)

    def identity(self, uid=None, boot_id=None, src=None, type=None, seq=None):
        try:
            self.last.update(uid=uid, boot_id=boot_id, src=src, type=type, seq=seq)
        except Exception as e:               # pragma: no cover
            self._oops("identity", e)

    def rejected(self, reason, data, peer=None):
        try:
            self.recent.append({"ms": _ms(self.wall), "reason": str(reason),
                                "peer": peer, "len": len(data),
                                "excerpt": _excerpt(data)})
            self._changed = True
        except Exception as e:
            self._oops("reject", e)

    # ---- file ------------------------------------------------------------
    def snapshot(self, ingest):
        """ingest's counters into the doc (the summary line's numbers)."""
        t, s = ingest.tracker, ingest.store.stats
        self.doc["counters"] = {
            "frames": ingest.frames, "ignored": ingest.ignored, "bad": ingest.bad,
            "accepted": s.get("added", 0), "written": s.get("written", 0),
            "buffered": len(ingest.store), "dropped": s.get("dropped", 0),
            "store_errors": s.get("errors", 0),
            "rejected": sum(ingest.rejects.values()),
            "rejects": dict(ingest.rejects),
            "seq_gaps": t.counts.get(C.GAP_GAP, 0),
            "seq_missing": t.missing_total,
            "duplicates": t.counts.get(C.GAP_DUPLICATE, 0),
            "late": t.counts.get(C.GAP_OUT_OF_ORDER, 0),
            "resets": t.counts.get(C.GAP_RESET, 0),
            "heartbeats": ingest.pico_heartbeats,
        }
        self.doc["recent_rejects"] = list(self.recent)

    def maybe_write(self, ingest, force=False):
        """Write if forced, if something changed and change_s has passed, or
        if write_s has passed.  Never raises; True if the file was written."""
        try:
            now = self.clock()
            age = None if self._written_at is None else now - self._written_at
            if not (force or age is None or age >= self.write_s
                    or (self._changed and age >= self.change_s)):
                return False
            self.snapshot(ingest)
            return self.write()
        except Exception as e:
            self._oops("snapshot", e)
            return False

    def stopped(self, ingest):
        self.doc["state"] = C.INGEST_STATE_STOPPED
        return self.maybe_write(ingest, force=True)

    def write(self):
        self._written_at = self.clock()
        self._changed = False
        self.doc["written_ms"] = _ms(self.wall)
        if not self.path:
            return False
        tmp = None
        try:
            fd, tmp = tempfile.mkstemp(prefix=".status-",
                                       dir=os.path.dirname(self.path) or ".")
            with os.fdopen(fd, "w") as f:
                json.dump(self.doc, f, separators=(",", ":"))
            os.chmod(tmp, C.LINK_STATE_MODE)
            os.replace(tmp, self.path)
        except Exception as e:
            self._oops("write to %s" % self.path, e)
            if tmp:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
            return False
        self._failed = False
        self.writes += 1
        return True


def read_ingest_status(path=None):
    """-> (doc or None, file age in ms or None)."""
    path = path or ingest_status_path()
    try:
        with open(path) as f:
            doc = json.load(f)
        age = int((time.time() - os.stat(path).st_mtime) * C.MS_PER_S)
    except (OSError, ValueError):
        return None, None
    return (doc, max(0, age)) if isinstance(doc, dict) else (None, None)
