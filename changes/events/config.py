"""config.py -- where to ingest from.

Order: --url, then an existing status.devices[] entry with family
"sandswing" and a ws_url in the Sandbells settings.json, then
WS_DEFAULT_URL.  Adds no settings.json entries.
"""

import json
import os
from pathlib import Path

from . import constants as C


def settings_path():
    return Path(os.environ.get(C.SANDBELLS_SETTINGS_ENV)
                or C.SANDBELLS_SETTINGS_PATH)


def url_from_settings(path):
    """ws_url of the first concentrator device in settings.json, or None."""
    try:
        cfg = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None
    devices = ((cfg.get("status") or {}).get("devices") or []
               if isinstance(cfg, dict) else [])
    for dev in devices:
        if (isinstance(dev, dict) and dev.get("family") == C.CONCENTRATOR_FAMILY
                and dev.get("ws_url")):
            return str(dev["ws_url"])
    return None


def resolve_url(cli_url=None, path=None):
    """-> (url, where_from) with where_from in "option" | "settings" | "default"."""
    if cli_url:
        return cli_url, "option"
    url = url_from_settings(settings_path() if path is None else path)
    if url:
        return url, "settings"
    return C.WS_DEFAULT_URL, "default"
