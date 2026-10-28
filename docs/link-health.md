# Link health: concentrator <-> Sandbells

Who connects to whom: the Pico is the **server** (adafruit_httpserver on port
80, `/status` and `/ws`).  Sandbells connects to it twice: the ingest service
(`manage.py ingest_events`, Python websocket-client) and, while page 3 is
open, the kiosk browser (`farm_status.js`).  nginx and gunicorn are not in the
WebSocket path.  Up to `MAX_WS_CLIENTS` (4) clients.

## Wire

| direction | schema | type | when | stored by Sandbells |
|---|---|---|---|---|
| Pico -> all | `sand.event/v1` | `stroke` | each stroke | yes |
| Pico -> all | `sand.event/v1` | `link` | client connected / dropped / refused, wifi_lost, wifi_back, link_dead, reset | yes |
| Pico -> all | `sand.panel/v1` | `heartbeat` | every 5 s (`PICO_HEARTBEAT_S`) | no: page 3 widget only |
| client -> Pico | `sand.hello/v1` | `heartbeat` | every 5 s | (Pico only notes "heard") |

Every frame uses the same envelope: `schema, type, src, id, boot_id, seq,
tick_ms, utc_ms, err_ms, sync, acc, epoch, session, mode, srv, stratum, body`.
`seq` of `link` events is the normal event sequence (Sandbells' gap tracker
sees them); the heartbeat's `seq` is its own counter and `body.last_seq` is
the newest event seq of this boot.

`link` body: `what`, `reason`, `clients`, plus `peer`, `replay`, `up_s`, `hb`,
`count`, `down_s`, `ip` as relevant.

Heartbeat body: `panel` (6 x RGB, the ON phase of any blink), `panel_state`,
`link` (LED1 state), `tower`, `net` (`farm_ws.link_status()`: connects,
drops, refused, send_timeouts, silent_drops, last_drop_reason,
last_drop_age_s, clients, live, rx_age_s, wifi_lost, rejoins, radio_resets),
`wifi` (`ip`, `rssi`), `sync`, `time` (`srv`, `stratum`, `last` burst result
with `why`, `peer` = stratum/leap of the last reply even when rejected, so a
sandmon GPS NO Lock shows as stratum 16 / leap 3), `last_seq`, `uptime_s`,
`last_reset`, `watchdog`, `mem_free`.

## Rules (code constants, no settings)

* Pico: a client that has sent a text frame must keep sending; silent
  `CLIENT_SILENT_S` (20 s) -> dropped.  Clients that never send (old ingest,
  debug listeners) are not timed out.
* Pico: every send has a deadline (`SEND_TIMEOUT_S` 1 s).  adafruit_httpserver
  4.8.2 `send_message()` / `close()` retry EAGAIN for ever on a full TCP
  buffer, which froze the whole concentrator on a dead peer.
* Pico: the last `REPLAY_N` (32) events are replayed to every new client;
  Sandbells ignores duplicates (UNIQUE src, boot_id, seq).
* Pico: LED1 green = a heartbeat client heard within 20 s (before any client
  has sent a heartbeat this boot, any client counts, as before).
* Pico: Wi-Fi supervision every 2 s: lost -> LED1 orange (`no_wifi`), clients
  dropped, rejoin every 30 s (120 s while ringing; a join blocks sensing up to
  10 s per network, watchdog paused), server rebound if the IP changed, SNTP
  started if boot had no Wi-Fi.
* Pico: Wi-Fi "up" but nothing heard for `LINK_DEAD_S` (120 s, tower
  inactive, after a heartbeat client was seen this boot): one radio off/on
  per silent spell.  `LINK_DEAD_RESET_S` (600 s): `microcontroller.reset()`,
  only if the watchdog is armed (settings `watchdog.enabled`).
* Pico LED6 (tower inactive): white = synced, amber = holdover (time server
  lost; strokes still carry utc_ms, err_ms grows), red = never synced.
* Sandbells ingest: hello every 5 s; once a Pico heartbeat was seen on the
  connection, `PEER_SILENT_S` (20 s) without a frame -> reconnect.  TCP
  keepalive 10/5/3.  Backoff resets only after a connection that delivered
  frames.
* Sandbells display (browser): every page that opens the Pico's `/ws`
  (`farm_status.js`, `align.js`, `kiosk_bells.js`, `tick-ws.js`) waits through
  one shared helper, `static/js/reconnect_delay.js`: 1, 2, 4, 8, 15 s (cap),
  each cut by a random 0-30 %, and back to 1 s only after a connection has
  stayed up 30 s.  A socket that opens and is dropped within a second does not
  reset it (the old pages reset at `onopen`, so a Pico dropping every new
  client was asked again every 2 s).  A Pico in its send-path backoff answers
  `/ws` with a 503 (see the sandswing repo's `docs/link-health.md`, "Send
  path"); the browser sees a failed connect and the same schedule applies.

## Frames the ingest cannot decode

A frame that is not valid UTF-8 or not valid JSON (seen: a ~1.4 kB sandswing
heartbeat cut off mid-string) used to end the connection when it was
rejected by websocket-client itself (`disconnected: cannot decode: b'...'`),
and so dropped a working link.  Now it is a **bad frame**: skipped, counted,
logged, and the link is only dropped after `BAD_FRAME_LIMIT` in a row.

The behaviour is a transition table (`events/framestate.py`); the state is
the number of bad frames in a row, N = `BAD_FRAME_LIMIT`:

| state | `good_frame` | `bad_frame` |
|---|---|---|
| 0 .. N-2 | -> 0, reset | -> state+1, count |
| N-1 | -> 0, reset | -> N, count + disconnect |
| N | -> 0, reset | -> N, count + disconnect |

* **bad_frame** = text that is not UTF-8 (`UnicodeDecodeError`, or the
  library's `WebSocketPayloadException` "cannot decode") or not JSON
  (`ParseError` `not_utf8` / `not_json`).  The ingest asks websocket-client
  to skip its own UTF-8 check (`skip_utf8_validation`) so it gets the bytes
  back.  The library has read the whole frame before it complains, so the
  stream stays in step and the next `recv()` is the next frame.
* **good_frame** = any frame that decoded, including a heartbeat
  (`sand.panel/v1`, ignored) and a frame Sandbells rejects for its content
  (wrong schema, missing field): those are not decode failures.  It resets
  the count; a new connection starts at 0.
* **N = 5** is a first guess.  Replace it with a number taken from the
  journal (how long do bad runs get? do they end by themselves?) in
  `constants.BAD_FRAME_LIMIT`.
* The skipped frame is not stored.  If it was an event, the next event shows
  a **gap** (`gap sandswing/<boot>: missing seq 7-7`), exactly as for any
  lost frame; a skipped heartbeat leaves no gap (its `seq` is not tracked).

Log lines (logger `events.ingest`, at most one `bad frame` WARNING per
`BAD_FRAME_LOG_INTERVAL_S` = 10 s, the rest are counted in "more not logged"):

```
WARNING bad frame skipped (not_json): len 1400, first 60 b'...', last 60 b'...' (1 in a row, 1 total, 0 more not logged)
WARNING bad frame skipped (cannot decode): len 1058, first 60 b'...', last 60 b'...' (1 in a row, 1 total, 0 more not logged)
WARNING disconnected: 5 bad frames in a row
INFO    frames 412, ignored 80, bad 3, accepted 329, ... rejected 1 {'not_json': 1}, gaps 1 (missing 1), ...
```

Only the length and the first and last 60 bytes are logged (as a Python
bytes repr, so control characters are escaped).  The sandswing heartbeat
carries no passwords; if a frame ever might, cut the excerpt in
`Ingest._act_count`.  The "disconnected" reason also goes into the stored
`ingest` / `disconnected` event.  `rejected` in the summary still counts a
`not_json` / `not_utf8` frame as well (so `bad` is the figure to watch), but
its own WARNING is replaced by the `bad frame` line.

After changing the code: `sudo systemctl restart sandbells-ingest`, then
`journalctl -u sandbells-ingest -f`.  Tests: `python manage.py test
events.tests_badframe events.tests_ingest`.
