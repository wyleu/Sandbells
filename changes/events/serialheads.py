"""serialheads.py -- the sandheads page over the Pico's USB data port.

With link.ring_send "off" the concentrator has no Wi-Fi and no /ws, so the
sandheads page cannot talk to it directly.  ingest_serial is the one owner
of the data port (ttyACM1); this is the small path through it:

  page --POST--> Django (check_command) --datagram--> SERIAL_CMD_SOCK_PATH
       --> ingest_serial (CommandInbox) --line--> Pico (tune.SerialTune ->
       align_scope.Aligner)
  Pico --align / align_ack / align_info lines--> ingest_serial (HeadsFile)
       --> SERIAL_HEADS_PATH (tmpfs) <--GET poll-- page

Only {"cmd":"align",...} commands go through, re-serialised here from the
checked fields (a page can never put a newline or anything else on the
port).  The Pico stops the scope by itself 10 s after the last keep-alive
and at once when the port is closed, so a page or ingest_serial going away
leaves nothing running.  No Django import here (ingest_serial and the views
both use it).  Protocol: sandswing docs/align-scope.md.
"""

import errno
import json
import logging
import os
import socket
import time
from collections import deque

from . import constants as C
from .ingeststatus import read_ingest_status, write_json_atomic

log = logging.getLogger(C.LOGGER_NAME + ".serial")


def cmd_sock_path():
    return os.environ.get(C.SERIAL_CMD_SOCK_ENV) or C.SERIAL_CMD_SOCK_PATH


def heads_path():
    return os.environ.get(C.SERIAL_HEADS_ENV) or C.SERIAL_HEADS_PATH


# ---- the page's command -------------------------------------------------------
def _int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def check_command(doc):
    """A page command (parsed JSON) -> its line (bytes, no newline), built
    from the checked fields only.  ValueError(reason) if it is not one."""
    if not isinstance(doc, dict) or doc.get("cmd") != C.SERIAL_CMD_NAME:
        raise ValueError("not an align command")
    for k in doc:
        if k not in C.SERIAL_CMD_KEYS:
            raise ValueError("unknown key %r" % str(k)[:20])
    out = {"cmd": C.SERIAL_CMD_NAME}
    if doc.get("info") is True:
        out["info"] = True
    else:
        ch = doc.get("ch")
        if not _int(ch) or not 1 <= ch <= C.SERIAL_CMD_MAX_CH:
            raise ValueError("bad channel")
        out["ch"] = ch
        if "scope" in doc:
            if not isinstance(doc["scope"], bool):
                raise ValueError("bad scope")
            out["scope"] = doc["scope"]
        elif "thr_mid" in doc:
            if doc["thr_mid"] is not True:
                raise ValueError("bad thr_mid")
            out["thr_mid"] = True
        else:
            for key in ("thr", "drive"):
                if key in doc:
                    v = doc[key]
                    if not _int(v) or v not in (-1, 1):
                        raise ValueError("bad step")
                    out[key] = v
                    break
            else:
                raise ValueError("nothing to do")
    line = json.dumps(out, separators=(",", ":")).encode(C.TEXT_ENCODING)
    if len(line) > C.SERIAL_CMD_MAX_B:
        raise ValueError("too long")
    return line


def send_command(line, path=None):
    """Django side: one checked line to ingest_serial.  -> True, or
    OSError (ingest_serial not running / not listening)."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        s.setblocking(False)
        s.sendto(line, path or cmd_sock_path())
    finally:
        s.close()
    return True


class CommandInbox:
    """ingest_serial side: the datagram socket the views send to.
    fileno() for select; take() -> checked lines (bytes, newline added)."""

    def __init__(self, path=None):
        self.path = path or cmd_sock_path()
        self.sock = None
        self.received = 0
        self.refused = 0

    def open(self):
        try:
            os.unlink(self.path)                  # a socket left by an earlier run
        except FileNotFoundError:
            pass
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        s.setblocking(False)
        s.bind(self.path)
        os.chmod(self.path, C.SERIAL_CMD_SOCK_MODE)
        self.sock = s
        return self

    def fileno(self):
        return self.sock.fileno()

    def take(self):
        out = []
        while self.sock is not None:
            try:
                data = self.sock.recv(C.SERIAL_CMD_MAX_B + 1)
            except OSError as e:
                if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EINTR):
                    break
                raise
            self.received += 1
            try:
                if len(data) > C.SERIAL_CMD_MAX_B:
                    raise ValueError("too long")
                line = check_command(json.loads(data.decode(C.TEXT_ENCODING)))
            except (ValueError, UnicodeDecodeError) as e:
                self.refused += 1                 # the view checks first; never trust it
                log.debug("serial command refused: %s", e)
                continue
            out.append(line + b"\n")
        return out

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            finally:
                self.sock = None
                try:
                    os.unlink(self.path)
                except OSError:
                    pass


# ---- the Pico's replies, for the page ----------------------------------------
def is_heads_line(doc):
    return (isinstance(doc, dict) and doc.get("schema") == C.SERIAL_HB_SCHEMA
            and doc.get("type") in C.SERIAL_HEADS_TYPES and isinstance(doc.get("body"), dict))


class HeadsFile:
    """The newest SERIAL_HEADS_KEEP scope lines, numbered, in SERIAL_HEADS_PATH
    (atomic, tmpfs), plus the relay's counters.  Never raises."""

    def __init__(self, path, wall=time.time, keep=C.SERIAL_HEADS_KEEP):
        self.path = path
        self.wall = wall
        self.items = deque(maxlen=keep)
        self.errors = 0
        self.doc = {"schema": C.SERIAL_HEADS_SCHEMA, "pid": os.getpid(),
                    "started_ms": self._now(), "connected": False, "n": 0,
                    "items": [], "relayed": 0, "dropped": 0, "refused": 0,
                    "last_cmd_ms": None, "last_line_ms": None}

    def _now(self):
        return int(self.wall() * C.MS_PER_S)

    def write(self):
        if not self.path:
            return
        self.doc["items"] = list(self.items)
        self.doc["written_ms"] = self._now()
        try:
            write_json_atomic(self.path, self.doc, prefix=".heads-")
        except Exception as e:
            self.errors += 1
            if self.errors == 1:
                log.warning("heads file %s: %s", self.path, e)

    def line(self, doc):
        now = self._now()
        self.doc["n"] += 1
        self.doc["last_line_ms"] = now
        self.items.append({"n": self.doc["n"], "ms": now, "doc": doc})
        self.write()

    def connected(self, yes):
        self.doc["connected"] = bool(yes)
        if not yes:
            self.items.clear()                    # a scope never outlives the port
        self.write()

    def relayed(self, n_ok, n_dropped, n_refused=0):
        self.doc["relayed"] += n_ok
        self.doc["dropped"] += n_dropped
        self.doc["refused"] += n_refused
        self.doc["last_cmd_ms"] = self._now()
        self.write()


def heads(after=0, now_ms=None, path=None):
    """For the page's poll: {"running", "connected", "n", "items" (newer than
    after, oldest first: the Pico's docs), "age_ms" (of the newest line),
    "relayed", "dropped"}.  running False: no file, or ingest_serial is not
    writing it."""
    doc, file_age = read_ingest_status(path or heads_path())
    now = int(time.time() * C.MS_PER_S) if now_ms is None else now_ms
    if not doc or doc.get("schema") != C.SERIAL_HEADS_SCHEMA:
        return {"running": False, "connected": False, "n": 0, "items": [], "age_ms": None,
                "relayed": 0, "dropped": 0}
    items = [i["doc"] for i in doc.get("items") or []
             if isinstance(i, dict) and isinstance(i.get("n"), int) and i["n"] > after]
    last = doc.get("last_line_ms")
    return {"running": True, "connected": bool(doc.get("connected")), "n": doc.get("n", 0),
            "items": items, "age_ms": None if last is None else max(0, now - last),
            "relayed": doc.get("relayed", 0), "dropped": doc.get("dropped", 0)}
