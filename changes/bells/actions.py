"""Device actions: one place that turns a button press on the farm page into
a change on a device.

A device lists what can be pressed as "actions" on an item of its
sand.status/v1 document: {"id": "nudge_down", "label": "-2%"}.  The page POSTs
{"device", "key", "action"} to /api/farm/action/ and run() routes it:

  * a device whose farm entry has "action_url" gets the request forwarded to
    it as JSON {"key", "action"} (sandswing, sandmon... implement that side);
  * this Sandbells machine's own actions are the handlers in LOCAL below.

Anything not listed is refused, so a page can never ask for more than the
code here allows.
"""
from __future__ import annotations

import json
from urllib.parse import urlparse
from urllib.request import Request, urlopen

FAN_NUDGE_FILE = "/run/sandbells-fan.nudge"   # created 0666 by the fan service
FAN_NUDGE_STEP = 2                            # percent per press


class ActionError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _fan_nudge_down(_params: dict) -> dict:
    """Ask the fan service to drop its duty by FAN_NUDGE_STEP.  The service
    (root) owns the PWM pin; it reads and empties this file every poll."""
    try:
        with open(FAN_NUDGE_FILE, "a") as f:
            f.write("-%d\n" % FAN_NUDGE_STEP)
    except OSError as e:
        raise ActionError("fan service not accepting nudges: %s" % e, 503)
    return {"ok": True, "message": "fan -%d%% requested" % FAN_NUDGE_STEP}


# (key, action id) -> handler(params) -> dict
LOCAL = {
    ("fan", "nudge_down"): _fan_nudge_down,
}


def _is_this_machine(inst: dict) -> bool:
    """The kiosk's own entry polls 127.0.0.1; any other host is someone else."""
    if inst.get("family", "sandbells") != "sandbells":
        return False
    host = urlparse(inst.get("status_url") or "").hostname
    return host in (None, "", "127.0.0.1", "localhost")


def run(inst: dict, key: str, action: str, params: dict | None = None) -> dict:
    params = params or {}
    url = (inst.get("action_url") or "").strip()
    if url:
        body = json.dumps({"key": key, "action": action, "params": params}).encode()
        req = Request(url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=5) as resp:
                out = json.loads(resp.read().decode("utf-8") or "{}")
        except Exception as e:
            raise ActionError("device did not take the action: %s" % e, 504)
        out.setdefault("ok", True)
        return out
    if not _is_this_machine(inst):
        raise ActionError("this device takes no actions (no action_url)", 501)
    handler = LOCAL.get((key, action))
    if handler is None:
        raise ActionError("unknown action %s/%s" % (key, action), 404)
    return handler(params)
