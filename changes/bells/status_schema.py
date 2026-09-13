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


def _item(key: str, label: str, value: Any, level: str | None = None, hint: str | None = None) -> dict:
    item = {
        "key": key,
        "label": label,
        "value": "—" if value is None or value == "" else str(value),
    }
    if level:
        item["level"] = _level(level)
    if hint:
        item["hint"] = hint
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
        _item("fan", "Fan", d.get("fan")),
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

