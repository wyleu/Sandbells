"""proxy.py -- one bounded HTTP call to the Sandtest rig.

The rig is a Pico 2 W with a tiny HTTP server (GET /status, POST /cmd).  The
browser never talks to it; the two views in views.py do, through here, so
there is no CORS and no mixed content.

Rules this module keeps:
  * A call returns within TIMEOUT_S, whatever the network does.  The request
    runs in a helper thread and the caller waits for it at most that long;
    that covers a slow DNS lookup (mDNS .local names can hang) as well as a
    slow connect or a reply that trickles in.
  * At most MAX_INFLIGHT calls are outstanding per worker process.  If the
    rig has stopped answering, further calls fail at once with a clear
    message instead of piling up threads.
  * The rig's address is looked up at most once every DNS_TTL_S, and is
    forgotten when a call fails.
  * Replies are capped at MAX_REPLY_BYTES.
Nothing here ever raises: every outcome is a Result.
"""
import http.client
import json
import socket
import threading
import time
from dataclasses import dataclass, field

from . import config as cfgmod

TIMEOUT_S = cfgmod.TIMEOUT_S
MAX_INFLIGHT = 4
MAX_REPLY_BYTES = 65536
DNS_TTL_S = 30.0

# Result.kind
OK = "ok"                    # the rig answered 2xx with JSON
REFUSED = "refused"          # the rig answered, but not 2xx (data may hold its JSON)
DOWN = "down"                # could not reach it, or it sent rubbish
TIMEOUT = "timeout"          # no answer within TIMEOUT_S
BUSY = "busy"                # earlier calls are still waiting; none made
BAD_CONFIG = "bad_config"    # the host setting is unusable; none made


@dataclass
class Result:
    kind: str
    data: dict = field(default_factory=dict)
    error: str = ""
    rig_status: int = 0
    ms: int = 0


_lock = threading.Lock()
_inflight = 0
_dns = {}                    # hostname -> (ip, expires at monotonic s)


def _resolve(host):
    now = time.monotonic()
    hit = _dns.get(host)
    if hit and hit[1] > now:
        return hit[0]
    infos = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)
    ip = infos[0][4][0]
    _dns[host] = (ip, now + DNS_TTL_S)
    return ip


def forget_address(host=None):
    if host is None:
        _dns.clear()
    else:
        _dns.pop(host, None)


def _do(box, cfg, method, path, body):
    """Runs in the helper thread; puts its Result in box[0]."""
    t0 = time.monotonic()
    deadline = t0 + TIMEOUT_S

    def left():
        return max(0.05, deadline - time.monotonic())

    conn = None
    try:
        ip = _resolve(cfg.hostname)
        conn = http.client.HTTPConnection(ip, cfg.port, timeout=left())
        headers = {"Host": cfg.host, "Accept": "application/json", "Connection": "close"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if cfg.token:
            headers["X-Sandtest-Token"] = cfg.token
        conn.connect()
        # http.client sends the headers and the body as two packets; Nagle holds the
        # second back until the first is acknowledged, and the rig gives up on a body
        # that is more than 0.3 s late ("bad JSON: syntax error").  Send both at once.
        try:
            conn.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        conn.request(method, path, body=body, headers=headers)
        if conn.sock is not None:
            conn.sock.settimeout(left())
        resp = conn.getresponse()
        chunks, size = [], 0
        while True:
            if conn.sock is not None:
                conn.sock.settimeout(left())
            chunk = resp.read(4096)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_REPLY_BYTES:
                raise ValueError("reply too long")
            chunks.append(chunk)
        raw = b"".join(chunks)
        ms = int((time.monotonic() - t0) * 1000)
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
            if not isinstance(data, dict):
                raise ValueError("not an object")
        except ValueError:
            box.append(Result(DOWN, error="the rig answered, but not with JSON (HTTP %d)"
                              % resp.status, rig_status=resp.status, ms=ms))
            return
        if 200 <= resp.status < 300:
            box.append(Result(OK, data=data, rig_status=resp.status, ms=ms))
        else:
            why = data.get("error") or ("HTTP %d" % resp.status)
            if resp.status == 401 or resp.status == 403:
                why = "the rig refused the token (HTTP %d); set SANDTEST_TOKEN" % resp.status
            box.append(Result(REFUSED, data=data, error=str(why),
                              rig_status=resp.status, ms=ms))
    except socket.timeout:
        forget_address(cfg.hostname)
        box.append(Result(TIMEOUT, error="no answer from %s within %g s" % (cfg.host, TIMEOUT_S),
                          ms=int((time.monotonic() - t0) * 1000)))
    except Exception as e:
        forget_address(cfg.hostname)
        box.append(Result(DOWN, error="cannot reach %s: %s" % (cfg.host, _why(e)),
                          ms=int((time.monotonic() - t0) * 1000)))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _why(e):
    if isinstance(e, socket.gaierror):
        return "name not found"
    if isinstance(e, ConnectionRefusedError):
        return "connection refused"
    if isinstance(e, TimeoutError):
        return "timed out"
    return str(e) or e.__class__.__name__


def _truncated(res):
    """True when the rig refused a command only because its body arrived cut short.
    The rig parses before it acts, so nothing ran and sending it again is safe."""
    return (res.kind == REFUSED and res.rig_status == 400 and
            ("bad JSON" in (res.error or "") or "incomplete body" in (res.error or "")))


def _run(box, cfg, method, path, body):
    global _inflight
    try:
        _do(box, cfg, method, path, body)
        if method == "POST" and box and _truncated(box[0]):
            first = box.pop()
            _do(box, cfg, method, path, body)
            if box and box[0].kind == REFUSED and _truncated(box[0]):
                box[0].error = first.error
    finally:
        with _lock:
            _inflight -= 1


def call(cfg, method, path, body=None):
    """-> Result, within TIMEOUT_S (plus a few ms of thread start-up)."""
    global _inflight
    if cfg.error:
        return Result(BAD_CONFIG, error=cfg.error)
    with _lock:
        if _inflight >= MAX_INFLIGHT:
            return Result(BUSY, error="the rig is not answering and %d earlier calls are "
                          "still waiting; not sending more" % _inflight)
        _inflight += 1
    box = []
    t = threading.Thread(target=_run, args=(box, cfg, method, path, body), daemon=True)
    t0 = time.monotonic()
    t.start()
    t.join(TIMEOUT_S)
    if box:
        return box[0]
    forget_address(cfg.hostname)
    return Result(TIMEOUT, error="no answer from %s within %g s" % (cfg.host, TIMEOUT_S),
                  ms=int((time.monotonic() - t0) * 1000))


def inflight():
    with _lock:
        return _inflight
