"""linkstate.py -- the ingest's view of the concentrator link, for page 3.

The ingest process (wsclient.py) and the web workers (gunicorn) are
different processes, so the live link state goes through one small JSON
file on tmpfs (LINK_STATE_PATH, systemd RuntimeDirectory of the ingest
unit).  Written atomically (temp file + os.replace); never stored in the
DB.  Heartbeat frames (sand.panel/v1) only update this file; link events
(sand.event/v1 type "link" from the Pico, type "ingest" from here) are
stored as events as well.

    state = LinkState(path)          # path None: in memory only (tests)
    state.connected(url)
    state.frame(kind)                # every frame received
    state.heartbeat(doc)             # every sand.panel/v1 heartbeat
    state.disconnected(reason)
    state.maybe_write()              # from idle(): keeps the file fresh
    read_link_state(path)            # api.py: -> dict or None
"""

import json
import logging
import os
import tempfile
import time

from . import constants as C

log = logging.getLogger(C.LOGGER_NAME)


def link_state_path():
    return os.environ.get(C.LINK_STATE_ENV) or C.LINK_STATE_PATH


def _ms(wall):
    return int(wall() * C.MS_PER_S)


class LinkState:
    def __init__(self, path=None, wall=time.time, clock=time.monotonic):
        self.path = path
        self.wall = wall
        self.clock = clock
        self._written_at = None
        self._write_failed = False
        self.doc = {
            "schema": C.LINK_STATE_SCHEMA,
            "ingest": {
                "state": C.LINK_STARTING, "url": None, "since_ms": _ms(wall),
                "connects": 0, "reconnects": 0, "drops": 0,
                "connect_failures": 0, "last_drop_reason": None,
                "last_drop_ms": None, "last_error": None,
                "frames": 0, "events": 0, "last_frame_ms": None,
                "last_event_ms": None, "heartbeats": 0,
                "last_heartbeat_ms": None, "pid": os.getpid(),
            },
            "pico": None,                     # last heartbeat (envelope + body)
            "written_ms": None,
        }

    # ---- updates ---------------------------------------------------------
    @property
    def ingest(self):
        return self.doc["ingest"]

    def _set_state(self, state, **kw):
        i = self.ingest
        if i["state"] != state:
            i["state"] = state
            i["since_ms"] = _ms(self.wall)
        i.update(kw)
        self.write()

    def connected(self, url):
        i = self.ingest
        i["connects"] += 1
        if i["connects"] > 1:
            i["reconnects"] += 1
        self._set_state(C.LINK_CONNECTED, url=url, last_error=None)

    def disconnected(self, reason):
        i = self.ingest
        i["drops"] += 1
        self._set_state(C.LINK_DOWN, last_drop_reason=reason,
                        last_drop_ms=_ms(self.wall))

    def connect_failed(self, url, reason):
        self.ingest["connect_failures"] += 1
        self._set_state(C.LINK_DOWN, url=url, last_error=reason)

    def stopped(self):
        self._set_state(C.LINK_STOPPED)

    def frame(self, is_event):
        i = self.ingest
        now = _ms(self.wall)
        i["frames"] += 1
        i["last_frame_ms"] = now
        if is_event:
            i["events"] += 1
            i["last_event_ms"] = now
        self.maybe_write(C.LINK_WRITE_MIN_S)

    def heartbeat(self, doc):
        i = self.ingest
        i["heartbeats"] += 1
        i["last_heartbeat_ms"] = _ms(self.wall)
        self.doc["pico"] = doc
        self.maybe_write(C.LINK_WRITE_MIN_S)

    # ---- file ------------------------------------------------------------
    def maybe_write(self, min_gap_s=C.LINK_WRITE_MAX_S):
        """Write if min_gap_s has passed since the last write."""
        now = self.clock()
        if self._written_at is None or now - self._written_at >= min_gap_s:
            self.write()

    def write(self):
        self._written_at = self.clock()
        self.doc["written_ms"] = _ms(self.wall)
        if not self.path:
            return False
        d = os.path.dirname(self.path) or "."
        try:
            fd, tmp = tempfile.mkstemp(prefix=".link-", dir=d)
            with os.fdopen(fd, "w") as f:
                json.dump(self.doc, f, separators=(",", ":"))
            os.chmod(tmp, C.LINK_STATE_MODE)
            os.replace(tmp, self.path)
        except OSError as e:
            if not self._write_failed:          # once, not every second
                log.warning("link state %s not written: %s", self.path, e)
            self._write_failed = True
            return False
        self._write_failed = False
        return True


def read_link_state(path=None):
    """-> (doc or None, file age in ms or None)."""
    path = path or link_state_path()
    try:
        with open(path) as f:
            doc = json.load(f)
        age = int((time.time() - os.stat(path).st_mtime) * C.MS_PER_S)
    except (OSError, ValueError):
        return None, None
    return doc, age
