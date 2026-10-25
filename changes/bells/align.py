"""align.py -- what the Alignment page needs from the farm registry.

The page talks to the concentrator Pico directly (its own WebSocket, like the
farm page), so Django only has to say which device and at which addresses.
Which heads are active comes from the Pico itself (align_info / heartbeat);
the rule lives here as ACTIVE_KINDS so the page and its tests agree with
sandswing's src/align_scope.py.
"""
import json

from events.constants import CONCENTRATOR_FAMILY

# survey kinds with a laser AND a sensor fitted and allowed to be driven
# (sandswing align_scope.ACTIVE_KINDS).  Not: empty, trigger, loopback, fault.
ACTIVE_KINDS = ("head_new", "head_old")
KEEPALIVE_MS = 2000          # page -> Pico scope keep-alive (Pico stops after 10 s)
WINDOW_MS = 2000             # width of the rolling trace


def ws_urls(inst):
    """Every WebSocket address of a registry entry, the main one first, then
    alt_ws_urls (home / tower), without repeats."""
    out = []
    for u in [inst.get("ws_url")] + list(inst.get("alt_ws_urls") or []):
        if u and str(u) not in out:
            out.append(str(u))
    return out


def is_concentrator(inst):
    return inst.get("family") == CONCENTRATOR_FAMILY


def pick(instances, index=None):
    """-> (index, inst) of the concentrator to align, or (None, None).
    index None: the first concentrator.  An index that is not a concentrator
    gives (None, None) too (the view turns that into a 404)."""
    if index is None:
        for i, d in enumerate(instances):
            if is_concentrator(d):
                return i, d
        return None, None
    if 0 <= index < len(instances) and is_concentrator(instances[index]):
        return index, instances[index]
    return None, None


def page_config(inst):
    """The dict the page's JS reads (rendered with json_script)."""
    return {"id": inst.get("id", ""), "name": inst.get("name", ""),
            "wsUrls": ws_urls(inst), "keepAliveMs": KEEPALIVE_MS,
            "windowMs": WINDOW_MS, "activeKinds": list(ACTIVE_KINDS)}
