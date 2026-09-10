from pathlib import Path
import json
import os

PATHS = (
    Path(os.environ.get("SANDBELLS_SETTINGS", "")),
    Path("/etc/sandbells/settings.json"),
    Path(__file__).resolve().parents[2] / "settings.json",
)

_DEFAULT = {
    "random_bells": 6,
    "random_windows": 3,
    "pattern_position_mode": "centre",
}

def _load():
    for p in PATHS:
        if p and p.is_file():
            return json.loads(p.read_text()), p
    return {}, None

def display_settings() -> dict:
    raw, path = _load()
    data = dict(_DEFAULT)
    data.update(raw.get("display") or {})
    data["random_bells"] = int(data.get("random_bells") or 6)
    data["random_windows"] = int(data.get("random_windows") or 3)
    mode = str(data.get("pattern_position_mode") or "centre").lower()
    if mode not in ("centre", "shorter", "float"):
        mode = "centre"
    data["pattern_position_mode"] = mode
    data["_settings_path"] = str(path) if path else ""
    return data
