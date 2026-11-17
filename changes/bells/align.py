"""align.py -- what the Alignment page needs from the farm registry.

The page talks to the concentrator Pico directly (its own WebSocket, like the
farm page), so Django only has to say which device and at which addresses.
Or, when the concentrator's USB data port is on this Pi (ingest_serial has it
open; the way with link.ring_send "off", no Wi-Fi), through Django and
ingest_serial: commands POSTed to /farm/heads/serial/cmd/, the Pico's lines
polled from /farm/heads/serial/ (events/serialheads.py).  pick_via() chooses;
?via=ws or ?via=serial on the page's address overrides.
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
VIA_WS = "ws"
VIA_SERIAL = "serial"
VIAS = (VIA_WS, VIA_SERIAL)


def pick_via(inst, serial_open, override=None):
    """"serial" or "ws": an override that is one of VIAS wins; else serial
    when ingest_serial has the Pico's data port open; else ws if the entry
    has an address; else serial (it says what is missing)."""
    if override in VIAS:
        return override
    if serial_open:
        return VIA_SERIAL
    return VIA_WS if ws_urls(inst) else VIA_SERIAL


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


def sweep_settings(path=None):
    """The line-up suggestion's numbers: HEADS_SWEEP_DEFAULTS, each
    overridden by settings.json "sandheads": {"sweep": {...}} when it is a
    number from 0 up to (not including) 1 (min_range_v: any positive
    number).  Read only; a missing or bad file means the defaults."""
    from events import constants as EC
    from events.config import settings_path
    out = dict(EC.HEADS_SWEEP_DEFAULTS)
    try:
        cfg = json.loads(open(path or settings_path()).read())
        sec = ((cfg.get(EC.HEADS_SWEEP_SETTINGS_KEY) or {}).get("sweep") or {})
    except (OSError, ValueError, AttributeError):
        return out
    if not isinstance(sec, dict):
        return out
    for k in out:
        v = sec.get(k)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
            continue
        if k != "min_range_v" and v >= 1:
            continue
        out[k] = v
    return out


def chatter_settings(path=None, read=True):
    """The chatter test's numbers: HEADS_CHATTER_DEFAULTS, each overridden by
    settings.json "sandheads": {"chatter": {...}} when it is the right kind
    and in range (passes a whole number 1..HEADS_CHATTER_PASSES_MAX; speeds
    and pad positive numbers; fast_pwm_hz within the Pico's PWM limits;
    drives_pct whole percents 1..100; face a name).  Read only."""
    from events import constants as EC
    from events.config import settings_path
    out = dict(EC.HEADS_CHATTER_DEFAULTS)
    out["drives_pct"] = list(out["drives_pct"])
    try:
        cfg = json.loads(open(path or settings_path()).read()) if read else {}
        sec = (cfg.get(EC.HEADS_SWEEP_SETTINGS_KEY) or {}).get(EC.HEADS_CHATTER_SETTINGS_KEY) or {}
    except (OSError, ValueError, AttributeError):
        sec = {}
    if not isinstance(sec, dict):
        sec = {}

    def whole(v, lo, hi):
        return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi

    def pos(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0
    v = sec.get("passes")
    if whole(v, 1, EC.HEADS_CHATTER_PASSES_MAX):
        out["passes"] = v
    for k in ("speed_dps", "pad_deg"):
        if pos(sec.get(k)):
            out[k] = sec[k]
    if whole(sec.get("fast_pwm_hz"), EC.HEADS_PWM_HZ_MIN, EC.HEADS_PWM_HZ_MAX):
        out["fast_pwm_hz"] = sec["fast_pwm_hz"]
    d = sec.get("drives_pct")
    if isinstance(d, list) and d and all(whole(x, 1, EC.HEADS_CHATTER_PCT_MAX) for x in d):
        out["drives_pct"] = list(d)
    if isinstance(sec.get("face"), str) and sec["face"].strip():
        out["face"] = sec["face"].strip()
    out.update(pwmMin=EC.HEADS_PWM_HZ_MIN, pwmMax=EC.HEADS_PWM_HZ_MAX, pwmNow=EC.HEADS_PWM_HZ_NOW,
               transPerPass=EC.HEADS_CHATTER_TRANS_PER_PASS)
    return out


def page_config(inst, via=VIA_WS, serial_urls=None, sweep=None, chatter=None):
    """The dict the page's JS reads (rendered with json_script).
    serial_urls: {"cmdUrl", "pollUrl", "logUrl", ...} (the views' reverse()).
    sweep: sweep_settings() (the line-up suggestion); chatter:
    chatter_settings() (the chatter test)."""
    from events import constants as EC
    cfg = {"id": inst.get("id", ""), "name": inst.get("name", ""),
           "wsUrls": ws_urls(inst), "keepAliveMs": KEEPALIVE_MS,
           "windowMs": WINDOW_MS, "activeKinds": list(ACTIVE_KINDS), "via": via,
           "lineup": dict(sweep or EC.HEADS_SWEEP_DEFAULTS, slots=EC.HEADS_LINEUP_SLOTS,
                          labelMax=EC.HEADS_LABEL_MAX),
           "chatter": chatter or chatter_settings(read=False)}
    if serial_urls:
        cfg["serial"] = dict(serial_urls, pollMs=EC.SERIAL_HEADS_POLL_MS,
                             liveMs=EC.SERIAL_HEADS_LIVE_MS)
    return cfg
