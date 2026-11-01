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
import socket
import time
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


# --- sandswing (the concentrator Pico) in tier 3, settings.json
# "link": {"ring_send": "udp"}: it runs no TCP server, so a command is one UDP
# datagram to its link.cmd_port.  It takes it only from its link.udp_host (this
# Pi), with its cpu uid and the boot_id of its current boot (both read from
# its last heartbeat in the ingest's link state), and a seq above the last
# one it took this boot (ms since 1970 here: rises across our restarts).
# Not protected against: anyone on the network can read uid and boot_id from
# the heartbeats and forge our address.  The worst a forger can do is turn
# the Pico's Wi-Fi off until its next reboot; MIDI is not affected.
SANDSWING_CMD_PORT = 5056          # sandswing link_health.CMD_PORT
SANDSWING_CMD_SCHEMA = "sand.cmd/v1"
MS_PER_S = 1000


def _udp_send(data: bytes, addr) -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.sendto(data, addr)
    finally:
        s.close()


def _pico_host(inst: dict) -> str | None:
    if inst.get("host"):
        return str(inst["host"])
    for k in ("status_url", "ws_url"):
        h = urlparse(inst.get(k) or "").hostname
        if h:
            return h
    return None


def _last_heartbeat() -> dict | None:
    from events.linkstate import read_link_state
    doc, _age = read_link_state()
    return (doc or {}).get("pico")


def _sandswing_wifi_off(inst: dict, _params: dict, send=_udp_send,
                        heartbeat=_last_heartbeat, clock=time.time) -> dict:
    host = _pico_host(inst)
    if not host:
        raise ActionError("no address for %s (farm entry host)" % inst.get("id"), 400)
    hb = heartbeat() or {}
    boot_id = hb.get("boot_id")
    uid = inst.get("uid") or (hb.get("body") or {}).get("uid")
    if not boot_id or not uid:
        raise ActionError("no heartbeat from the Pico yet (boot_id / uid unknown)", 409)
    seq = int(clock() * MS_PER_S)
    cmd = {"schema": SANDSWING_CMD_SCHEMA, "cmd": "wifi_off", "uid": uid,
           "boot_id": boot_id, "seq": seq}
    port = int(inst.get("cmd_port") or SANDSWING_CMD_PORT)
    try:
        send(json.dumps(cmd).encode("utf-8"), (host, port))
    except OSError as e:
        raise ActionError("could not send to %s:%d: %s" % (host, port, e), 504)
    return {"ok": True, "seq": seq,
            "message": "Wi-Fi off sent (seq %d). The Pico confirms with a link "
                       "net_command event, then stays MIDI-only until it is "
                       "rebooted or repowered." % seq}


# family "sandswing": (key, action) -> handler(inst, params) -> dict
SANDSWING = {
    ("wifi", "off"): _sandswing_wifi_off,
}

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
    if inst.get("family") == "sandswing" and (key, action) in SANDSWING:
        return SANDSWING[(key, action)](inst, params)
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
