"""views.py -- the Sandtest page and its two proxy endpoints.

  GET  /sandtest/          the page
  GET  /sandtest/status    -> rig GET /status
  POST /sandtest/cmd       JSON body -> rig POST /cmd

The rig is only called when the browser asks (the page polls /status while it
is visible), never from a background job.  Replies are always JSON:

  {"ok": true,  "reachable": true,  "host": "...", "rig": {<the rig's reply>}, "ms": 12}
  {"ok": false, "reachable": true,  "host": "...", "error": "...", "rig": {...}}   rig said no (400)
  {"ok": false, "reachable": false, "host": "...", "error": "..."}                 502/503/504
"""
import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from . import config, proxy

POLL_MS = 1000
MAX_BODY_BYTES = 2048
# every command the rig's firmware knows; the rig validates the keys
COMMANDS = ("play", "press", "stress", "stop", "pause", "resume", "sweep",
            "park", "zero", "face", "status")


def _reply(cfg, res):
    """Result -> JsonResponse."""
    base = {"host": cfg.host, "ms": res.ms}
    if res.kind == proxy.OK:
        return JsonResponse(dict(base, ok=True, reachable=True, rig=res.data))
    if res.kind == proxy.REFUSED:
        body = dict(base, ok=False, reachable=True, error=res.error, rig=res.data)
        return JsonResponse(body, status=400 if res.rig_status == 400 else 502)
    code = {proxy.TIMEOUT: 504, proxy.BAD_CONFIG: 503, proxy.BUSY: 503}.get(res.kind, 502)
    return JsonResponse(dict(base, ok=False, reachable=False, error=res.error), status=code)


@ensure_csrf_cookie
@never_cache
def page(request):
    cfg = config.load()
    return render(request, "sandtest/page.html", {
        "host": cfg.host or "(bad host setting)",
        "host_source": cfg.source,
        "token_set": cfg.token_set,
        "config_error": cfg.error,
        "poll_ms": POLL_MS,
        "timeout_ms": int(proxy.TIMEOUT_S * 1000),
    })


@require_GET
@never_cache
def status(request):
    cfg = config.load()
    return _reply(cfg, proxy.call(cfg, "GET", "/status"))


@require_POST
@never_cache
def cmd(request):
    cfg = config.load()
    if len(request.body) > MAX_BODY_BYTES:
        return JsonResponse({"ok": False, "reachable": None, "host": cfg.host,
                             "error": "command too long"}, status=413)
    try:
        body = json.loads(request.body.decode("utf-8") or "null")
    except (ValueError, UnicodeDecodeError):
        body = None
    if not isinstance(body, dict):
        return JsonResponse({"ok": False, "reachable": None, "host": cfg.host,
                             "error": "body must be a JSON object like {\"cmd\": \"stop\"}"},
                            status=400)
    if body.get("cmd") not in COMMANDS:
        return JsonResponse({"ok": False, "reachable": None, "host": cfg.host,
                             "error": "cmd must be one of: %s" % ", ".join(COMMANDS)},
                            status=400)
    payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
    return _reply(cfg, proxy.call(cfg, "POST", "/cmd", payload))
