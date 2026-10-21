"""wsclient.py -- read the concentrator's /ws and feed Ingest.

Blocking recv with a WS_RECV_TIMEOUT_S timeout: no busy loop, and every
quiet second runs ingest.idle() and checks stop.  Reconnects with a
capped exponential Backoff.  The websocket-client library is imported
only when no connect function is injected (tests use a fake socket).
"""

import logging
import socket

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


def default_connect(url, timeout):
    import websocket                      # pip: websocket-client
    return websocket.create_connection(url, timeout=timeout)


def timeout_errors():
    try:
        import websocket
        return (socket.timeout, websocket.WebSocketTimeoutException)
    except ImportError:
        return (socket.timeout,)


def read_frames(ws, ingest, stop, timeouts):
    """Until disconnect or stop.  Returns frames read."""
    n = 0
    while not stop.is_set():
        try:
            msg = ws.recv()
        except timeouts:
            ingest.idle()
            continue
        except Exception as e:            # closed, reset, protocol error
            log.warning("disconnected: %s", e or type(e).__name__)
            return n
        if not msg:                       # close/control frame: no event
            if not getattr(ws, "connected", True):
                log.warning("disconnected: closed by peer")
                return n
            continue
        n += 1
        ingest.handle_frame(msg)
    return n


def run(url, ingest, stop, connect=default_connect, backoff=None,
        connect_timeout_s=C.WS_CONNECT_TIMEOUT_S,
        recv_timeout_s=C.WS_RECV_TIMEOUT_S):
    """Connect, read, reconnect until stop is set.  Flushes on the way out."""
    backoff = backoff or Backoff()
    timeouts = timeout_errors()
    while not stop.is_set():
        ws = None
        try:
            ws = connect(url, connect_timeout_s)
            ws.settimeout(recv_timeout_s)
        except Exception as e:
            delay = backoff.next()
            log.warning("connect %s failed: %s; retry in %.0f s", url, e, delay)
            ingest.idle()
            stop.wait(delay)
            continue
        log.info("connected %s", url)
        backoff.reset()
        try:
            read_frames(ws, ingest, stop, timeouts)
        finally:
            try:
                ws.close()
            except Exception:
                pass
        ingest.flush()                    # nothing waits in RAM while down
        if not stop.is_set():
            delay = backoff.next()
            log.info("reconnect in %.0f s", delay)
            stop.wait(delay)
    ingest.flush()
    log.info("stopped: %s", ingest.summary())
