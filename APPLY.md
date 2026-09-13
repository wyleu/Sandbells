# feature/status-v1 — apply on the Pi

Current `main` / `v1.0.0` stays as the ringing kiosk. This work belongs on a new branch.

```bash
cd ~/Code/Sandbells
git checkout main
git pull origin main
git checkout -b feature/status-v1
```

Copy from this packet:

```
docs/status-v1.md
changes/bells/status_schema.py
changes/bells/templates/bells/farm_status.html
changes/bells/static/css/farm_status.css
changes/bells/static/js/farm_status.js
```

## Wire the wrapper (small edits)

### `changes/bells/status_views.py`

At the top:

```python
from bells.status_schema import wrap_document
```

Change the end of `system_status()` from `return JsonResponse({...})` to:

```python
    payload = {
        # existing keys unchanged …
    }
    return JsonResponse(wrap_document(payload))
```

Leave the flat keys in `payload` so `legacy` still has them.

### `changes/bells/views.py` — `farm_device_status`

```python
from bells.status_schema import wrap_document

# inside the successful fetch:
data = json.loads(resp.read().decode("utf-8"))
return JsonResponse(wrap_document(data))
```

### `load_farm_instances()`

Replace the static list with settings when present:

```python
def load_farm_instances():
    from pathlib import Path
    import json
    path = Path("/etc/sandbells/settings.json")
    try:
        cfg = json.loads(path.read_text()) if path.is_file() else {}
    except Exception:
        cfg = {}
    devices = (cfg.get("status") or {}).get("devices")
    if devices:
        return devices
    return [ /* existing three stubs as fallback */ ]
```

Give the local kiosk a `status_url` of `http://127.0.0.1/api/system-status/` so the farm page does not assume “host always means myself”.

### settings

Add under `status` in `/etc/sandbells/settings.json` (and `install-steps/settings.example.json`):

```json
"devices": [
  {
    "id": "sandbells",
    "name": "sandbells",
    "kind": "host",
    "family": "sandbells",
    "role": "kiosk",
    "status_url": "http://127.0.0.1/api/system-status/"
  },
  {
    "id": "sandbells2",
    "name": "sandbells2",
    "kind": "host",
    "family": "sandbells",
    "role": "kiosk",
    "status_url": "http://sandbells2.local/api/system-status/"
  },
  {
    "id": "sandsense-clock",
    "name": "sandsense-clock",
    "kind": "pico",
    "family": "sandsense",
    "role": "sense",
    "status_url": "http://192.168.0.154/status",
    "ws_url": "ws://192.168.0.154/ws"
  }
]
```

Then:

```bash
cd ~/Code/Sandbells
source Bellvirtenv/bin/activate
cd changes
python manage.py collectstatic --noinput
sudo systemctl reload gunicorn
```

Open `/farm/status/` fullscreen (`target=_top`, already used from the pattern windows). Prev/Next still walks **one** device. Only that device is polled; the websocket is opened only if that entry has `ws_url` and the page is visible.

## Why the old page looked half-height

`farm_status.css` capped `#st-json` / `#ss-lines` at `max-height: 24rem` with `overflow: auto`. The new CSS uses the leftover viewport under the header (`body` flex column, `#farm-main` `flex: 1`, `overflow: hidden`) so the section grid fills the HDMI frame the same way `pagesize.js` fills `#ishow`.
