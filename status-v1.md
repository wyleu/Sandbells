# sand.status/v1

Shared status document for Sandbells, Sandmon, Sandsense, and later boxes.

Branch intent: `feature/status-v1` (do not land on `v1.0.0` / current `main` until the kiosk still renders).

## Rules

1. The **device** owns the facts. The hub only names the device and fetches one URL.
2. The UI paints `sections` / `items`. It must not know `encoder_leds`, `pll_locked`, or `fan`.
3. **One live enquiry at a time.** The farm list is static (or last-cached). Only the open device page polls or opens a websocket.
4. Use the **full kiosk frame** (same sizing idea as `pagesize.js` on `#ishow`). Do not lock the value list to half a page.

## Envelope

```json
{
  "schema": "sand.status/v1",
  "id": "sandsense-clock",
  "name": "Sandsense",
  "role": "sense",
  "family": "sandsense",
  "host": "sandsense.local",
  "instance": "tower",
  "ts": 1757769000,
  "uptime_s": 172800,
  "level": "ok",
  "summary": "test mode, encoder LEDs off",
  "poll_hint_sec": 5,
  "sections": []
}
```

| Field | Who sets it | Notes |
|---|---|---|
| `schema` | device | Must be `sand.status/v1` |
| `id` | device | Stable slug |
| `name` | device | Display title |
| `role` | device | `kiosk` `time` `ap` `sense` `gps` `swing` `other` |
| `family` | device | `sandbells` `sandmon` `sandsense` `sandswing` |
| `host` | device | `.local` or IP |
| `ts` | device | Unix seconds when built |
| `uptime_s` | device | Optional |
| `level` | device | `ok` `warn` `error` `unknown` — rollup **on the device** |
| `summary` | device | One line for the header |
| `poll_hint_sec` | device | Hint only; page may use a slower default |
| `sections` | device | Ordered groups |

Hub may add (never overwrite device fields):

```json
{
  "seen_at": 1757769010,
  "stale": false,
  "fetch_ms": 42
}
```

## Section / item

```json
{
  "id": "sense",
  "title": "Sensing",
  "level": "ok",
  "items": [
    {
      "key": "encoder_leds",
      "label": "Encoder LEDs",
      "value": "off",
      "level": "ok",
      "hint": "idle 2d"
    }
  ]
}
```

`value` is a string in v1. `level` on an item is optional; missing means inherit section / document.

## Transport

Each device serves **one** document:

| Device | URL |
|---|---|
| Sandbells kiosk | `http://<host>/api/system-status/` (wrapped; see below) |
| Sandmon | `http://sandmon.local/status.json` |
| Sandsense | `http://<pico>/status` or `/status.json` |

Hub proxy stays `GET /api/farm/device-status/?url=…` and may only fetch URLs listed in the farm registry.

### Chatter

On a device detail page:

- One HTTP poll of **that** URL.
- Interval from `poll_hint_sec`, floored at 3s, capped at 15s.
- Websocket **only** if this page’s registry entry has `ws_url` **and** the page is visible (`document.visibilityState === "visible"`). Close the socket on hide / prev / next.
- Prev / Next (already on `farm_status.html`) is the pager. Do not prefetch neighbours.

The farm index must not start N polls or N sockets.

## Farm registry

Move the hardcoded `load_farm_instances()` list into settings:

```json
"status": {
  "poll_hint_sec": 5,
  "devices": [
    {
      "id": "sandbells2",
      "name": "sandbells2",
      "family": "sandbells",
      "role": "kiosk",
      "status_url": "http://sandbells2.local/api/system-status/"
    },
    {
      "id": "sandmon",
      "name": "sandmon",
      "family": "sandmon",
      "role": "ap",
      "status_url": "http://sandmon.local/status.json"
    },
    {
      "id": "sandsense-clock",
      "name": "sandsense-clock",
      "family": "sandsense",
      "role": "sense",
      "status_url": "http://192.168.0.154/status",
      "ws_url": "ws://192.168.0.154/ws"
    }
  ]
}
```

`id` / `name` / `status_url` / `ws_url` are hub naming. Everything inside the document is the device’s.

## Display

Farm detail is opened `target="_top"` (already true from the pattern-window links) so it owns the whole HDMI frame.

Layout:

- Thin header: brand, Prev, `i / n`, Next, `name`, `level`, `summary`.
- Remaining viewport is a CSS grid of sections (two or three columns on a landscape kiosk).
- Each section is a definition list of label / value. Colour the value by `level`.
- No `max-height: 24rem` + scroll dump. That is why the current page looks half-height.
- Size the main area with the same window math as `pagesize.js` (`innerHeight` minus header). If a section still overflows, page sections with the existing prev/next idea rather than a nested scrollbar.

Do not special-case Sandsense in the template. An orb is just another item (`key: beacon`, `value: green`) or a single optional `beacon` field on the envelope later. v1 can show the red/green as a normal row.

## Compatibility wrapper

Old Sandbells payload is a flat dict (`wifi_ssid`, `fan`, `time_locked`, …).

`bells/status_schema.py` wraps that dict into `sand.status/v1` so:

- `/api/system-status/` can start returning the envelope.
- Farm host view stops printing raw JSON.
- Old `status_panel.js` can keep reading flat keys **or** we keep a `legacy` object on the envelope for one release:

```json
{ "schema": "sand.status/v1", "sections": [ … ], "legacy": { "wifi_ssid": "…", "fan": "12%" } }
```

Prefer dropping `legacy` once the kiosk panel reads sections.

If a fetch is already `sand.status/v1`, pass it through.

If a fetch is Sandsense’s current ad-hoc JSON (`ip`, `ssid`, `temp_c`, `pll_locked`, `lines`, …), wrap it the same way in the hub **only until** the Pico emits v1 itself.

## Implementation order

1. Add `docs/status-v1.md` and `bells/status_schema.py`.
2. `system_status()` returns the wrapped envelope (plus `legacy` for now).
3. Replace farm host `<pre id="st-json">` with the section grid; use full viewport CSS.
4. Farm page polls **only** `inst.status_url` (via the existing proxy). Stop assuming `/api/system-status/` for every host.
5. Sandsense page uses the same renderer; websocket only while that page is open.
6. Pico / Sandmon grow a native `/status.json`. Remove hub-side Sandsense field mapping when they do.

## Out of scope for v1

- History / graphs
- Polling the whole farm every few seconds
- Changing pattern display or `v1.0.0` kiosk behaviour
- Hard-coded encoder or PLL widgets on Sandbells
