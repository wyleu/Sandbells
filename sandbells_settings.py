#!/usr/bin/env python3
"""
sandbells_settings.py

Programme: sandbells_settings
Family:    Sandbells shared host tooling (generic — any machine)

Purpose
  Load host configuration from outside the git tree so secrets and
  per-machine values are not hard-coded in network/time scripts.

Canonical path
  /etc/sandbells/settings.json
  Override with env SANDBELLS_SETTINGS if needed.

Typical keys
  networks[]     — {ssid, psk} WiFi fallbacks for network-select
  time_hosts[]   — GPS/NTP mDNS names for time-select
  ethernet       — dhcp_timeout_sec, fallback_ip, fallback_prefix
  status         — optional UI hints (never used for secrets)

Security
  Real file should be mode 600, root-owned.
  Do not expose psk values via /api/system-status/ or logs.

Returns
  dict — always a usable structure; missing file yields safe defaults
  (empty networks list, standard sandgps*.local time_hosts).

Usage
  from sandbells_settings import load_sandbells_settings
  cfg = load_sandbells_settings()

  python3 sandbells_settings.py   # self-test (no PSKs printed)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SETTINGS_PATH = Path(os.environ.get("SANDBELLS_SETTINGS", "/etc/sandbells/settings.json"))

DEFAULTS = {
    "networks": [],
    "time_hosts": [
        "sandgps.local",
        "sandgps1.local",
        "sandgps2.local",
        "sandgps3.local",
    ],
    "ethernet": {
        "dhcp_timeout_sec": 15,
        "fallback_ip": "192.168.99.2",
        "fallback_prefix": 24,
    },
    "status": {
        "poll_hint_sec": 3,
    },
}


def load_sandbells_settings(path: Path | None = None) -> dict:
    """Load settings JSON; merge on top of DEFAULTS. Never raises for missing file."""
    cfg = {
        **DEFAULTS,
        "ethernet": dict(DEFAULTS["ethernet"]),
        "status": dict(DEFAULTS["status"]),
        "time_hosts": list(DEFAULTS["time_hosts"]),
        "networks": list(DEFAULTS["networks"]),
    }
    p = path or SETTINGS_PATH
    if not p.is_file():
        return cfg
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return cfg
    if not isinstance(data, dict):
        return cfg
    for key in ("networks", "time_hosts", "ethernet", "status"):
        if key not in data or data[key] is None:
            continue
        if key in ("ethernet", "status") and isinstance(data[key], dict):
            cfg[key] = {**cfg[key], **data[key]}
        else:
            cfg[key] = data[key]
    return cfg


if __name__ == "__main__":
    errors = []
    s = load_sandbells_settings()

    if not isinstance(s.get("networks"), list):
        errors.append("networks must be a list")
    if not isinstance(s.get("time_hosts"), list) or not s["time_hosts"]:
        errors.append("time_hosts must be a non-empty list")

    eth = s.get("ethernet") or {}
    if "fallback_ip" not in eth:
        errors.append("ethernet.fallback_ip missing")

    print("path:", SETTINGS_PATH)
    print("exists:", SETTINGS_PATH.is_file())
    print("networks (ssids only):", [n.get("ssid") for n in s.get("networks") or []])
    print("time_hosts:", s.get("time_hosts"))
    print("ethernet:", eth)

    if errors:
        print("SELF-TEST FAIL:")
        for e in errors:
            print(" ", e)
        sys.exit(1)

    print("SELF-TEST OK")
    sys.exit(0)
