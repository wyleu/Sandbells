"""sand.status/v1 helpers.

Wrap today's flat Sandbells / Sandsense payloads so the farm page can
render sections without knowing device-specific keys.

Flat keys (time_label, wifi_ssid, …) are also copied onto the Sandbells
document so the kiosk overlay in system_info.js keeps working.
"""
from __future__ import annotations

import time
from typing import Any

SCHEMA = "sand.status/v1"
LEVELS = ("ok", "warn", "error", "unknown")


def _level(value: str | None) -> str:
    v = (value or "unknown").lower()
    return v if v in LEVELS else "unknown"


def _item(key: str, label: str, value: Any, level: str | None = None, hint: str | None = None,
          actions: list[dict] | None = None) -> dict:
    item = {
        "key": key,
        "label": label,
        "value": "—" if value is None or value == "" else str(value),
    }
    if level:
        item["level"] = _level(level)
    if hint:
        item["hint"] = hint
    if actions:
        item["actions"] = actions     # [{"id", "label"}]; see status-v1.md
    return item


def _section(sid: str, title: str, items: list[dict], level: str | None = None) -> dict:
    sec = {"id": sid, "title": title, "items": items}
    if level:
        sec["level"] = _level(level)
    return sec


def is_v1(data: Any) -> bool:
    return isinstance(data, dict) and data.get("schema") == SCHEMA


def worst_level(*levels: str) -> str:
    rank = {"ok": 0, "unknown": 1, "warn": 2, "error": 3}
    best = "ok"
    for lv in levels:
        if rank.get(_level(lv), 1) > rank[best]:
            best = _level(lv)
    return best


def wrap_document(data: dict, meta: dict | None = None) -> dict:
    """Pass through v1, else wrap known flat shapes."""
    if is_v1(data):
        out = dict(data)
    elif _looks_sandsense(data):
        out = from_sandsense_flat(data)
    else:
        out = from_sandbells_flat(data)
    if meta:
        for k in ("seen_at", "stale", "fetch_ms"):
            if k in meta:
                out[k] = meta[k]
    return out


def _looks_sandsense(data: dict) -> bool:
    keys = set(data)
    return bool(keys & {"pll_locked", "ticks_this_period", "adc_avg", "tick_seq"})


def from_sandbells_flat(d: dict) -> dict:
    host = d.get("hostname_local") or d.get("hostname") or ""
    time_locked = bool(d.get("time_locked"))
    time_level = "ok" if time_locked else "warn"
    using_fallback = bool(d.get("using_fallback"))

    net_items = [
        _item("ip", "IP", d.get("ip")),
        _item("ip_list", "Addresses", d.get("ip_list")),
        _item("wifi", "WiFi", _join(d.get("wifi_state"), d.get("wifi_ssid"), d.get("wifi_ip"))),
        _item("wired", "Wired", _join(d.get("wired_state"), d.get("wired_ip"), d.get("wired_method"))),
        _item(
            "fallback",
            "Fallback",
            "yes" if using_fallback else "no",
            "warn" if using_fallback else "ok",
            hint=f"{d.get('fallback_ip')}/{d.get('fallback_prefix')}",
        ),
    ]
    server_items = [
        _item("host", "Host", host),
        _item("git", "Git", _join(d.get("git_branch"), d.get("git_hash"))),
        _item("nginx", "Nginx", d.get("nginx"), _svc_level(d.get("nginx"))),
        _item("gunicorn", "Gunicorn", d.get("gunicorn"), _svc_level(d.get("gunicorn"))),
        _item("kiosk", "Kiosk", d.get("kiosk"), _svc_level(d.get("kiosk"))),
    ]
    hw_items = [
        _item("model", "Model", d.get("pi_model")),
        _item("arch", "Arch", d.get("arch")),
        _item("memory", "Memory", d.get("memory")),
        _item("cpu", "CPU", _join(d.get("cpu"), f"load {d.get('load1')}" if d.get("load1") else None)),
        _item("temp", "Temp", d.get("temp")),
        _item("fan", "Fan", d.get("fan"), actions=_fan_actions(d.get("fan"))),
        _item(
            "throttled",
            "Throttled",
            d.get("throttled"),
            "error" if str(d.get("throttled", "")).lower() in ("yes", "true") else "ok",
        ),
    ]
    time_items = [
        _item("source", "Source", d.get("time_source"), time_level),
        _item("lock", "Lock", d.get("time_label") or ("locked" if time_locked else "NO LOCK"), time_level),
    ]
    display_items = [
        _item("bells", "Random bells", d.get("random_bells")),
        _item("windows", "Windows", d.get("random_windows")),
        _item("pattern_mode", "Pattern mode", d.get("pattern_mode")),
        _item("settings", "Settings", d.get("settings_path")),
    ]

    level = worst_level(
        time_level,
        "warn" if using_fallback else "ok",
        _svc_level(d.get("nginx")),
        _svc_level(d.get("gunicorn")),
    )
    summary = d.get("time_label") or host or "sandbells"
    if using_fallback:
        summary = "fallback IP · " + str(summary)

    doc = {
        "schema": SCHEMA,
        "id": d.get("hostname") or "sandbells",
        "name": d.get("hostname") or "sandbells",
        "role": "kiosk",
        "family": "sandbells",
        "host": host,
        "ts": int(d.get("status_tick") or time.time()),
        "level": level,
        "summary": str(summary),
        "poll_hint_sec": int(d.get("poll_hint_sec") or 5),
        "sections": [
            _section("network", "Network", net_items),
            _section("server", "Server", server_items),
            _section("hardware", "Hardware", hw_items),
            _section("time", "Time", time_items, time_level),
            _section("display", "Display", display_items),
        ],
        "legacy": d,
    }
    for k, v in d.items():
        if k not in doc:
            doc[k] = v
    return doc


def from_sandsense_flat(d: dict) -> dict:
    pll_on = bool(d.get("pll_enabled"))
    pll_locked = bool(d.get("pll_locked"))
    pll_level = "ok" if pll_locked else ("warn" if pll_on else "unknown")
    lines = d.get("lines") or []
    if isinstance(lines, list):
        line_text = "\n".join(str(x) for x in lines[-8:])
    else:
        line_text = str(lines)

    items_net = [
        _item("ip", "IP", d.get("ip")),
        _item("ssid", "WiFi", d.get("ssid")),
    ]
    items_sense = [
        _item("pll", "PLL", f"{'ON' if pll_on else 'OFF'} locked={pll_locked}", pll_level),
        _item("misses", "Misses", d.get("misses")),
        _item(
            "ticks",
            "Ticks",
            f"{d.get('ticks_this_period', '—')} / {d.get('report_interval_s', '—')}s",
        ),
        _item("adc", "ADC avg", d.get("adc_avg")),
        _item("tick_seq", "Tick seq", d.get("tick_seq")),
        _item("last", "Last message", d.get("last_line")),
    ]
    items_hw = [
        _item("temp", "Temp", None if d.get("temp_c") is None else f"{d.get('temp_c')} °C"),
    ]
    if line_text:
        items_sense.append(_item("log", "Recent", line_text))

    level = worst_level(pll_level, "ok")
    summary = d.get("last_line") or ("PLL locked" if pll_locked else "PLL unlocked")

    return {
        "schema": SCHEMA,
        "id": d.get("id") or "sandsense",
        "name": d.get("name") or "Sandsense",
        "role": "sense",
        "family": "sandsense",
        "host": d.get("ip") or "",
        "ts": int(time.time()),
        "level": level,
        "summary": str(summary)[:80],
        "poll_hint_sec": int(d.get("report_interval_s") or d.get("poll_hint_sec") or 5),
        "sections": [
            _section("network", "Network", items_net),
            _section("sense", "Sensing", items_sense, pll_level),
            _section("hardware", "Hardware", items_hw),
        ],
        "legacy": d,
    }


def _fan_actions(fan: Any) -> list[dict] | None:
    """Only a machine whose fan service reports a percentage has a fan to nudge."""
    if str(fan or "").endswith("%"):
        return [{"id": "nudge_down", "label": "-2%"}]
    return None


def _svc_level(state: Any) -> str:
    s = str(state or "").lower()
    if s == "active":
        return "ok"
    if s in ("inactive", "failed"):
        return "error"
    if not s or s in ("unknown", "—"):
        return "unknown"
    return "warn"


def _join(*parts: Any) -> str:
    bits = [str(p) for p in parts if p not in (None, "", "—")]
    return "  ".join(bits) if bits else "—"



# ---- sandswing over its USB data port (events.serialingest, no Wi-Fi) -------
SERIAL_SOURCE = "usb serial"
PANEL_LEDS = ("Link", "LED 2", "LED 3", "LED 4", "LED 5", "Sync")   # sandswing panel.py order
PANEL_KEY = "led%d"     # the Panel items' keys, led1..led6 (bells/farm_leds.js paints them live)


def _ago_text(ms: Any) -> str | None:
    if ms is None:
        return None
    s = int(ms) // 1000
    if s < 120:
        return f"{s} s"
    if s < 7200:
        return f"{s // 60} min"
    return f"{s // 3600} h {(s % 3600) // 60} min"


def panel_css(rgb: Any) -> str:
    """A panel LED's rgb (dim on purpose) -> a CSS colour bright enough to
    see: the brightest channel scaled to PANEL_CSS_FULL, black (or no
    colour) PANEL_CSS_DARK.  Same output as link_widget.js cssColour."""
    from events import constants as EC
    try:
        r, g, b = (max(0, int(x)) for x in list(rgb)[:3])
    except (TypeError, ValueError):
        return EC.PANEL_CSS_DARK
    m = max(r, g, b)
    if m <= 0:
        return EC.PANEL_CSS_DARK
    k = EC.PANEL_CSS_FULL / m
    half = 0.5                                     # Math.round, not banker's rounding
    return "rgb(%d,%d,%d)" % tuple(int(v * k + half) for v in (r, g, b))


def from_serial_heartbeat(latest: dict, inst: dict | None = None) -> dict:
    """events.serialingest.latest() -> sand.status/v1 for the sandswing
    page: the Pico's slim heartbeat, read over USB serial, with its age.
    Stale: level warn and the summary says how old."""
    inst = inst or {}
    hb = latest.get("heartbeat") or {}
    b = hb.get("body") or {}
    age_ms, stale = latest.get("age_ms"), bool(latest.get("stale"))
    age = _ago_text(age_ms)
    pico = hb.get("serial") or {}
    reader = latest.get("serial") or {}

    src_items = [
        _item("source", "Status from", f"{SERIAL_SOURCE} {latest.get('port') or ''}".strip(),
              "warn" if stale else "ok",
              hint="no Wi-Fi needed; the Pico's USB data port"),
        _item("age", "Last line", f"{age} ago" if age else None,
              "warn" if stale else "ok",
              hint=f"stale after {latest.get('stale_ms', 0) // 1000} s"),
        _item("every", "Every", f"{latest.get('period_s'):g} s" if latest.get("period_s") else None),
        _item("lines", "Lines read", _join(f"{reader.get('good', 0)} good",
                                           f"{reader.get('bad', 0)} cut" if reader.get("bad") else None),
              "ok"),
        _item("pico", "Pico writer", _join(f"{pico.get('lines', 0)} sent",
                                           f"{pico.get('cut', 0)} cut" if pico.get("cut") else None,
                                           f"{pico.get('errors', 0)} errors" if pico.get("errors") else None),
              "warn" if pico.get("errors") else "ok", hint=pico.get("last_error")),
    ]
    sync = b.get("sync") or "unsynced"
    sync_level = {"synced": "ok", "held": "ok", "stale": "warn"}.get(sync, "error")
    t = b.get("time") or {}
    last = t.get("last") or {}
    time_items = [
        _item("sync", "Sync", sync, sync_level),
        _item("srv", "Source", _join(t.get("srv"), f"stratum {t['stratum']}" if t.get("stratum") is not None else None)),
    ]
    if last.get("ok") is False and last.get("why"):
        time_items.append(_item("why", "Last attempt", last["why"], "warn"))

    heads, head_level = [], "ok"
    for i, c in enumerate(b.get("chan") or []):
        kind = c[0] if isinstance(c, list) and c else c
        why = c[1] if isinstance(c, list) and len(c) > 1 else None
        lvl = "error" if kind == "fault" else ("warn" if kind == "unknown" else "ok")
        head_level = worst_level(head_level, lvl)
        heads.append(_item(f"ch{i + 1}", f"Channel {i + 1}", _join(kind, why), lvl))

    panel = []
    states = b.get("panel_state") or []
    for i, rgb in enumerate(b.get("panel") or []):
        it = _item(PANEL_KEY % (i + 1), PANEL_LEDS[i] if i < len(PANEL_LEDS) else f"LED {i + 1}",
                   states[i] if i < len(states) else None)
        it["color"] = panel_css(rgb)
        panel.append(it)

    wifi = b.get("wifi") or {}
    net = b.get("net") or {}
    net_items = [
        _item("link", "Link", b.get("link")),
        _item("ip", "Wi-Fi IP", wifi.get("ip")),
        _item("rssi", "Signal", f"{wifi['rssi']} dBm" if wifi.get("rssi") is not None else None),
        _item("drops", "Drops", net.get("drops"), "warn" if net.get("drops") else None,
              hint=net.get("last_drop_reason")),
    ]
    mem = b.get("mem_free")
    lost, late = b.get("edges_lost") or 0, b.get("late_drains") or 0
    conc = [
        _item("uptime", "Up", _ago_text((b.get("uptime_s") or 0) * 1000) if b.get("uptime_s") is not None else None),
        _item("reset", "Last reset", b.get("last_reset"),
              "warn" if str(b.get("last_reset") or "").upper() == "WATCHDOG" else None),
        _item("watchdog", "Watchdog", None if b.get("watchdog") is None else ("armed" if b["watchdog"] else "off")),
        _item("mem", "Free memory", f"{mem // 1024} kB" if isinstance(mem, int) else None,
              hint=f"VM heap {b['gc_heap_kb']} kB" if b.get("gc_heap_kb") is not None else None),
        _item("edges", "Edge stamps", f"{lost} lost, {late} late drains",
              "warn" if lost or late else "ok"),
        _item("undelivered", "Strokes not delivered (Wi-Fi)", b.get("strokes_undelivered")),
        _item("boot", "Boot / event", _join(hb.get("boot_id"), b.get("last_seq"))),
        _item("uid", "UID", b.get("uid")),
    ]
    tower = b.get("tower") or "unknown"
    tower_level = "ok" if tower == "active" else ("warn" if tower == "ringing_down" else "unknown")
    sections = [
        _section("serial", "USB serial", src_items, "warn" if stale else "ok"),
        _section("panel", "Panel", panel),
        _section("time", "Time", time_items, sync_level),
        _section("heads", "Heads", heads, head_level),
        _section("tower", "Tower", [_item("state", "State", tower, tower_level)], tower_level),
        _section("network", "Network", net_items),
        _section("concentrator", "Concentrator", conc),
    ]
    level = "warn" if stale else worst_level(sync_level, head_level)
    kinds = " ".join(str(h["value"]).split("  ")[0] for h in heads)
    if stale:
        summary = f"USB serial status STALE ({age} old)" if age else "USB serial status STALE"
    else:
        summary = f"USB serial, {age} ago" if age else "USB serial"
    if kinds:
        summary += f" · heads {kinds}"
    return {
        "schema": SCHEMA,
        "id": inst.get("id") or hb.get("id") or "sandswing",
        "name": inst.get("name") or hb.get("id") or "sandswing",
        "role": inst.get("role") or "concentrator",
        "family": inst.get("family") or "sandswing",
        "host": "",
        "ts": int(time.time()),
        "level": level,
        "summary": summary[:100],
        "poll_hint_sec": int(latest.get("period_s") or 10),
        "uptime_s": b.get("uptime_s"),
        "via": SERIAL_SOURCE,
        "stale": stale,
        "age_ms": age_ms,
        "sections": sections,
    }
