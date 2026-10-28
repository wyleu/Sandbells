# Sandtest page (`/sandtest/`)

Control side of the **Sandtest rig**: a Pico 2 W that presses the sandswing
trigger lines through opto-couplers and turns a stepper-mounted mirror /
reflector at the laser heads.  The firmware lives in its own project
(`sandtest`, CircuitPython); this page is how you drive it from the kiosk or
any browser on the network.  Menu button: **Sandtest** (top line, between the
farm devices and *Rings by day*).

Cheat sheet for unattended stress runs (controls, timing, recipes, logs): [sandtest-cheatsheet.md](sandtest-cheatsheet.md).

## Where the rig is

Set the address in `/etc/sandbells/settings.json` (read on every request, no
restart needed):

```json
"sandtest": { "host": "192.168.0.198", "token": "" }
```

or with the environment variables `SANDTEST_HOST` and `SANDTEST_TOKEN` (these
win over the file; the gunicorn unit needs an `Environment=` line for them).

| setting | default | meaning |
| --- | --- | --- |
| `host` / `SANDTEST_HOST` | `sandtest.local` | name or IPv4 address, optionally `:port`.  Use the Pico's DHCP address if `.local` does not resolve (its address is on its USB console at boot; it was 192.168.0.198 at the last check). |
| `token` / `SANDTEST_TOKEN` | none | sent as header `X-Sandtest-Token`; must equal the firmware's `http.token`.  Never sent to the browser; the page only says "token set". |

The host in use is shown at the top of the page.  A bad value (not a plain
host name or address) is reported on the page and by the proxy as an error;
nothing is sent anywhere.  The browser can not choose the host.

## How it works

* `GET /sandtest/status` -> rig `GET /status`
* `POST /sandtest/cmd` (JSON body, e.g. `{"cmd":"stop"}`) -> rig `POST /cmd`

Both answer JSON.  Success: `{"ok":true,"reachable":true,"host":...,"rig":{...}}`.
The rig refusing a command: HTTP 400, `{"ok":false,"reachable":true,"error":...}`.
Rig not answering: HTTP 502 (unreachable / refused / not JSON), 503 (bad host
setting, or earlier calls still waiting) or 504 (no answer), always with
`"reachable":false` and an `"error"` sentence.  Because the browser only talks
to Sandbells there is no CORS and no mixed-content problem.

* Every proxied call takes at most **2 s** in total (name lookup included, so a
  slow `.local` lookup cannot hold a worker).  At most 4 calls per gunicorn
  worker can be waiting on a silent rig; further ones fail at once.
* The rig is called **only when a browser asks**.  The page polls
  `/sandtest/status` once a second **only while it is visible** (it stops when
  the tab is hidden or another page is shown), backing off to every 5 s while
  the rig is unreachable.  Nothing polls the rig in the background.
* `/sandtest/cmd` only forwards the commands the firmware knows
  (`play press stress stop pause resume sweep park zero face status`); the rig
  checks the rest.
* While the rig is unreachable, Django logs a 502/504 line per poll.

## The page

* **STOP** (top left, stays on screen when scrolling): sends `{"cmd":"stop"}`
  (stops the pattern, releases every output, halts the mirror).  It is never
  disabled, retries once if the first try fails, and says plainly if it could
  not be confirmed.  It is gold, not red: red is reserved for "not coming".
* Connection pill: *connected* (green), *NO ANSWER · last good status N s ago*
  (gold, the last values stay on screen but dimmed), *not reachable* (grey).
* Rig: version, player state, presses sent, outputs pressed now, worst
  lateness, loop max, free memory.  Mirror: motion, shaft angle, beam angle (twice
  the shaft angle), face, speed, target, limits, and the **head window** flag
  (gold *IN WINDOW: head N (face)* when the angle is inside a head's window),
  profile progress and the rig's warnings.  Heads table: each head's shaft
  angle, width, and the shaft angle at which the mirror and the reflector face
  line up with it.
* Controls: press one channel; play a pattern; stress; sweep; scan every head;
  visit a head; menace; profile a head; mirror/reflector face toggle; park.
  **Menace** has a dashed gold *RISKY: allow hits* checkbox (off by default):
  with it ticked the mirror may dwell on a head and press its trigger line for
  real, and the button says so.
* The last 8 commands sent, with UK time and whether the rig took them.

Light on purpose (Luakit on the Pi): no libraries, no animation, one small
script and style sheet, cache-busted with `?v=<git hash>`.

## Tests

`python manage.py test sandtest` runs the proxy against a fake Pico on a local
socket (success, token, refusal, refused connection, slow rig, slow name
lookup, rubbish reply, bad host), the page render and menu entry, and the
page's JavaScript helpers with `node --test changes/sandtest/js_tests/`.
