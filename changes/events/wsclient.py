"""wsclient.py -- read the concentrator's /ws and feed Ingest.

Blocking recv with a WS_RECV_TIMEOUT_S timeout: no busy loop, and every
quiet second runs ingest.idle() and checks stop.  Reconnects with a
capped exponential Backoff.  The websocket-client library is imported
only when no connect function is injected (tests use a fake socket).

Link health (docs/link-health.md):
  * every CLIENT_HEARTBEAT_S we send a small sand.hello/v1 text frame, so
    the Pico can drop us if we vanish (it never times out a client that
    has never sent anything, e.g. an old ingest);
  * once the Pico has sent a sand.panel/v1 heartbeat on this connection,
    PEER_SILENT_S without any frame means the link is dead (half-open):
    close and reconnect instead of waiting for ever;
  * TCP keepalive underneath, for the kernel's own view;
  * backoff only resets after a connection that delivered a frame, so a
    Pico refusing us (1013, max clients) is retried with growing delays;
  * every connect / disconnect (with reason) / first failed connect is an
    "ingest" event (Ingest.note) and in the LinkState file for page 3.
"""

import json
import logging
import socket
import time

from . import constants as C
from .backoff import Backoff

log = logging.getLogger(C.LOGGER_NAME)


def library_available():
    """True if websocket-client can be imported."""
    try:
        __import__(C.WS_LIBRARY_MODULE)
    except ImportError:
        return False
    return True


def keepalive_sockopts():
    """TCP keepalive (Linux names; whatever this Python has)."""
    opts = [(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)]
    for name, value in (("TCP_KEEPIDLE", C.TCP_KEEPIDLE_S),
                        ("TCP_KEEPINTVL", C.TCP_KEEPINTVL_S),
                        ("TCP_KEEPCNT", C.TCP_KEEPCNT)):
        if hasattr(socket, name):
            opts.append((socket.IPPROTO_TCP, getattr(socket, name), value))
    return tuple(opts)


def default_connect(url, timeout):
    import websocket                      # pip: websocket-client
    return websocket.create_connection(url, timeout=timeout,
                                       sockopt=keepalive_sockopts())


def hello(seq):
    """Our heartbeat to the Pico (any text frame keeps us live there)."""
    return json.dumps({C.F_SCHEMA: C.SCHEMA_HELLO_V1, C.F_TYPE: C.TYPE_HEARTBEAT,
                       C.F_SRC: C.INGEST_SRC, C.F_SEQ: seq})


def timeout_errors():
    try:
        import websocket
        return (socket.timeout, websocket.WebSocketTimeoutException)
    except ImportError:
        return (socket.timeout,)


class Disconnected(Exception):
    """read_frames() ended because the link went away (reason in str)."""


def read_frames(ws, ingest, stop, timeouts, clock=time.monotonic):
    """Until disconnect or stop.  Returns frames read; the reason for a
    disconnect is left in read_frames.reason (None after a stop)."""
    n = 0
    read_frames.reason = None
    send = getattr(ws, "send", None)          # fakes in tests may not send
    hb_at = None
    hb_seq = 0
    last_rx = clock()
    peer_hb0 = getattr(ingest, "pico_heartbeats", 0)
    while not stop.is_set():
        now = clock()
        if send is not None and (hb_at is None or now - hb_at >= C.CLIENT_HEARTBEAT_S):
            hb_at = now
            hb_seq += 1
            try:
                send(hello(hb_seq))
            except timeouts:
                pass                              # full buffer: the silence check decides
            except Exception as e:
                read_frames.reason = "send failed: %s" % (e or type(e).__name__)
                log.warning("disconnected: %s", read_frames.reason)
                return n
        try:
            msg = ws.recv()
        except timeouts:
            ingest.idle()
            heard = getattr(ingest, "pico_heartbeats", 0) > peer_hb0
            if heard and clock() - last_rx > C.PEER_SILENT_S:
                read_frames.reason = "peer silent %d s" % C.PEER_SILENT_S
                log.warning("disconnected: %s", read_frames.reason)
                return n
            continue
        except Exception as e:            # closed, reset, protocol error
            read_frames.reason = str(e) or type(e).__name__
            log.warning("disconnected: %s", read_frames.reason)
            return n
        last_rx = clock()
        if not msg:                       # close/control frame: no event
            if not getattr(ws, "connected", True):
                read_frames.reason = "closed by peer"
                log.warning("disconnected: closed by peer")
                return n
            continue
        n += 1
        ingest.handle_frame(msg)
    return n


read_frames.reason = None


def _note(ingest, what, **body):
    fn = getattr(ingest, "note", None)
    if fn is not None:
        fn(what, **body)


def _wait(stop, delay, ingest, link):
    """stop.wait(delay) in slices of at most LINK_WRITE_MAX_S, touching the
    link file between slices: a 30 s backoff must not let the file age past
    INGEST_FILE_STALE_MS, or page 3 says INGEST DOWN when the ingest is
    alive and the Pico is just unreachable (LOST is the truth)."""
    left = delay
    while left > 0 and not stop.is_set():
        step = min(left, C.LINK_WRITE_MAX_S)
        stop.wait(step)
        left -= step
        if left > 0 and not stop.is_set():
            ingest.idle()
            if link is not None:
                link.write()


def run(url, ingest, stop, connect=default_connect, backoff=None,
        connect_timeout_s=C.WS_CONNECT_TIMEOUT_S,
        recv_timeout_s=C.WS_RECV_TIMEOUT_S, clock=time.monotonic):
    """Connect, read, reconnect until stop is set.  Flushes on the way out."""
    backoff = backoff or Backoff()
    timeouts = timeout_errors()
    link = getattr(ingest, "link", None)
    failing = False                       # one "connect_failed" event per outage
    fails = 0
    _note(ingest, "started", url=url)
    while not stop.is_set():
        ws = None
        try:
            ws = connect(url, connect_timeout_s)
            ws.settimeout(recv_timeout_s)
        except Exception as e:
            delay = backoff.next()
            reason = str(e) or type(e).__name__
            log.warning("connect %s failed: %s; retry in %.0f s", url, e, delay)
            fails += 1
            if not failing:
                failing = True
                _note(ingest, "connect_failed", url=url, reason=reason)
            if link is not None:
                link.connect_failed(url, reason)
            ingest.idle()
            _wait(stop, delay, ingest, link)
            continue
        log.info("connected %s", url)
        _note(ingest, "connected", url=url, failed_tries=fails)
        if link is not None:
            link.connected(url)
        failing, fails = False, 0
        started = clock()
        n = 0
        try:
            n = read_frames(ws, ingest, stop, timeouts, clock=clock)
        finally:
            try:
                ws.close()
            except Exception:
                pass
        reason = read_frames.reason or ("stopped" if stop.is_set() else "ended")
        if n:
            backoff.reset()               # a real session, not a refusal
        if not stop.is_set():
            _note(ingest, "disconnected", url=url, reason=reason, frames=n,
                  up_s=round(clock() - started, 1))
            if link is not None:
                link.disconnected(reason)
        ingest.flush()                    # nothing waits in RAM while down
        if not stop.is_set():
            delay = backoff.next()
            log.info("reconnect in %.0f s", delay)
            _wait(stop, delay, ingest, link)
    _note(ingest, "stopped")
    if link is not None:
        link.stopped()
    ingest.flush()
    log.info("stopped: %s", ingest.summary())
