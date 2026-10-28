# Sandtest cheat sheet: unattended trigger tests

For the **Sandtest** page (`/sandtest/`, see [sandtest.md](sandtest.md)) and the rig
firmware behind it (Pico 2 W, repo `sandtest`, HEAD 54e8228).  Read from `page.html`,
`sandtest.js`, `commands.py`, `patterns.py`, `player.py`, `sweep.py` and the README;
the numbers were run with `src/patterns.py` and `sim.py` on a PC.  **unconfirmed** =
not provable from source (mostly: needs the real rig).  Example values assume
`settings_example.json`: 8 optos GP8-GP15 (bell N = line N), 4 heads, soft limits +-270 deg.
The rig's real `settings.json` is not in git.

## What does what

* **Presses sandswing trigger lines** (opto pulls the line LOW): *Press*, *Play*, *Stress*.
  These are the longevity tools.
* **Moves the mirror**: *Sweep, Scan, Visit, Menace, Profile, Park*.  If the beam lands
  in a head's window the head fires for real.  *Face* only changes a label.
* A new *Press/Play/Stress* **replaces** the press run in progress (lines released
  first); a new mirror command replaces the mirror run; the two halves run side by side.
  So one stray *Press* click ends a 2 h stress run.  *STOP* ends both.

## The controls (page default; firmware limit)

The page leaves a blank field out (the rig then uses its own default).  Its form `min`s
are looser than the firmware, so the rig can still refuse (HTTP 400, error shown).

| Control | In plain words | Fields: unit, page default; firmware limit | Beam on a head / real press? |
| --- | --- | --- | --- |
| **Press** | One press of one line. | `channel` 1 (1-8, needs an opto pin); `press_ms` ms, 120 (**5**-5000) | **Presses a line** |
| **Play** | Presses bell numbers in order, one stroke after another. | `pattern` `13425678` (digits 1-8, rows split by a space, or `rounds` = 1..N for the N configured bells, 8 here; max **2048** strokes written); `interval_ms` 400 (**10**-60000); `press_ms` 120 (**5**-5000); `repeat` 1 (1-**100000**) | **Presses lines** |
| **Stress** | Seeded random bursts of presses. | `seed` 1 (0-4294967295); `seconds` 60 (1-**86400**). Not on the page, rig defaults: `bells` 8 (1-8), `press_ms` 120, `burst_min`/`burst_max` 2/8 (1-64), `interval_min_ms`/`interval_max_ms` 40/400 (10-60000), `idle_min_ms`/`idle_max_ms` 200/1500 (0-60000) | **Presses lines** |
| **Sweep** | Mirror runs A to B and back. | `from_deg` -30, `to_deg` 30 (+-36000, clamped to the soft limits); `speed_dps` deg/s 10 (0.05-3600, capped by the stepper's max); `dwell_ms` 500 (>=0) at each end; `cycles` 0 = forever (round trips) | **Yes**: crosses every window between A and B |
| **Scan** | One slow pass over every head's angle and back. | `speed_dps` 4; `dwell_ms` 300 (rig alone: 0); `cycles` 1 (0 = forever); `face` as now/mirror/reflector | **Yes, on purpose** |
| **Visit** | Go to one head and wait. | `head` 1 (1-8, must be configured); `dwell_ms` 500; `face`; speed 10 deg/s (not on page) | **Yes**, and it then **stays on that head** (page never sends `then_park`) until Park |
| **Menace** | Slow random wander that avoids every head window. | `seed` 1; `seconds` 60 (page 0-86400, 0 = forever; rig up to 1000000); `face`; **RISKY `allow_hits`**, off. Not on page: speed 8 deg/s, dwell 300-3000 ms, `margin_deg` 1.0 | Off: **no**. Ticked: **yes, may sit on a head** |
| **Profile** | Steps across one head, dwelling at each angle; logs `start`/`end` lines. | `head` 1; `face` mirror; `span_deg` 10 (0-360); `step_deg` 0.5 (page 0.01-360; rig refuses less than one motor step, about 0.088 deg, or over 1000 points); `dwell_ms` 2000 (>=1); `passes` 1 (1-10000) | **Yes, on purpose** |
| **Face** | Says which side (mirror/reflector) faces the heads. Nothing moves. | `face` mirror or reflector | No; refused while the mirror moves |
| **Park** | Mirror to park (0 deg) at half speed, coils off. | none | Crosses any window on the way |
| **STOP** | Releases all lines; mirror slows and holds where it is (not park). | none; page retries once | Presses end; **mirror stays put** |

Exact JSON the page sends (defaults; run through `sandtest.js` `buildCommand`):

```
press   {"cmd":"press","channel":1,"press_ms":120}
play    {"cmd":"play","pattern":"13425678","interval_ms":400,"press_ms":120,"repeat":1}
stress  {"cmd":"stress","seed":1,"seconds":60}
sweep   {"cmd":"sweep","mode":"sweep","from_deg":-30,"to_deg":30,"speed_dps":10,"dwell_ms":500,"cycles":0}
scan    {"cmd":"sweep","mode":"scan","speed_dps":4,"dwell_ms":300,"cycles":1}        (+ "face" if chosen)
visit   {"cmd":"sweep","mode":"visit","head":1,"dwell_ms":500}                        (+ "face")
menace  {"cmd":"sweep","mode":"menace","seed":1,"seconds":60,"allow_hits":false}      (+ "face"; true when ticked)
profile {"cmd":"sweep","mode":"profile","head":1,"face":"mirror","span_deg":10,"step_deg":0.5,"dwell_ms":2000,"passes":1}
face    {"cmd":"face","face":"mirror"}     park  {"cmd":"park"}     stop  {"cmd":"stop"}
```

**Beam on a head.**  The optos only ever pull a line low.  A beam hit is different: the
head's own comparator makes the stroke, which is what the page's "press its trigger line
for real" means.  Only *Menace* with `allow_hits` off keeps out of the windows of **both**
faces (plus the margin); if it starts inside one it first leaves it (about 0.5 s in the
sim).  For a purely electrical test, keep the mirror parked and use only the press controls.
Whether the real head windows match `settings.json` is **unconfirmed**.  The rig also has
`pause`, `resume`, `zero`, `circle`, `goto`; the page has no button for them.

## Timing, exactly (`patterns.py`)

* `interval_ms` is the time from the **start of one stroke to the start of the next**,
  bell after bell, **including across row ends and repeats**.  Not per row, not per bell:
  an 8-bell row takes 8 x `interval_ms`.  The first stroke fires when the rig accepts the command.
* `press_ms`: how long the line is held LOW from the stroke start.  Longer than the interval
  means presses overlap.
* `MIN_RELEASE_MS` 30: the same bell again needs a start-to-start time of at least
  `press_ms` + 30, else the rig refuses (`1` at 120 ms needs `interval_ms` >= 150; 149 fails).
  Only the first two repeats are checked.
* `gap_ms` (not on the page): **extra** time after every `gap_every`-th row (default 2, the
  handstroke gap); start-to-start across it is `interval_ms` + `gap_ms`.  Rows count **across
  repeats**: `rounds` with `repeat` gets a gap after every 2nd repeat.
* `repeat`: the whole row list again, no extra pause.  Run time = (strokes - 1) x interval +
  gaps + `press_ms`.  `MAX_STROKES` 2048 limits only the **written** pattern; `MAX_REPEAT`
  100000 multiplies it.
* Stress `seconds`: new bursts start until the time is up and the burst in progress is
  finished, so a run ends **late** (up to about 3 s; 1.9 s worst in 200 seeds at 60 s).
  Bells are random, not in ringing order.  The idle wait counts from the last release.

| Worked example (press 120 ms) | Result |
| --- | --- |
| `play` `1`, `interval_ms` 5000 | one press per 5.0 s on line 1 = 12/min = 720/h; `repeat` 1440 = 7195 s |
| `13425678`, 400 (page default) | 2.5 strokes/s; each bell once per 3.2 s row |
| `rounds`, 250, `repeat` 3600 (page only, no gap) | 4 strokes/s; each bell every 2.0 s; 28800 strokes in 7199.9 s |
| `rounds`, 250, `gap_ms` 250, `repeat` 3388 | 3.76 strokes/s; rows start at 0, 2.0, 4.25, 6.25 s; each bell every 2.0 / 2.25 s; 27104 strokes in 7199.1 s |
| same, 6 bells (`"bells":6`), `repeat` 4430 | 26580 strokes in 7198.4 s |
| `stress` defaults | about 2.7 strokes/s, 9700/h; in 2 h about 19400 presses (2400 per bell), at most 3 lines low together |

250 ms + 250 ms handstroke gap is my arithmetic for a typical 8-bell peal pace (about 3 h
for 5040 changes), not a figure from the repos.

## Unattended stress run recipe (2 h, up to 8 bells)

One command covers 2 h: `seconds` goes to 86400 (24 h), `repeat` to 100000 (about 55 h of
8-bell rounds at 250 ms).  For longer, send the next command before the old one ends; it
replaces it.  The page has no `gap_ms`, `bells` or burst/interval/idle fields, so send JSON
straight to the rig from the desk Pi (`RIG` = its address, 192.168.0.198 at the last check;
`TOKEN` only if the rig has `http.token`; keep it out of anything shared).  Going through
`/sandtest/cmd` needs a CSRF cookie (scripting that is **unconfirmed**).

```
RIG=192.168.0.198; TOKEN=            # TOKEN empty if the rig has none
send() { curl -fsS --max-time 5 -X POST "http://$RIG/cmd" ${TOKEN:+-H "X-Sandtest-Token: $TOKEN"} -d "$1"; echo; }
mark() { echo "$(date '+%F %T') MARK $1" >> ~/pico-net.log; }
```

1. **Random, 2 h:** `mark stress2h; send '{"cmd":"stress","seed":4242,"seconds":7200}'`
   (add `"bells":6` etc.; burst/interval/idle keys as in the table).
2. **Ringing-like, 2 h:** `send '{"cmd":"play","pattern":"rounds","interval_ms":250,"press_ms":120,"repeat":3388,"gap_ms":250,"gap_every":2}'`
   (page-only: `rounds`, 250, 120, repeat 3600, no gap).
3. **Mixed, 2 h** (15 min ringing, 5 min random, six times; `repeat` 423 = 898.6 s):

```
for i in 1 2 3 4 5 6; do
  mark ring$i;   send '{"cmd":"play","pattern":"rounds","interval_ms":250,"press_ms":120,"repeat":423,"gap_ms":250}'; sleep 900
  mark stress$i; send "{\"cmd\":\"stress\",\"seed\":$i,\"seconds\":300}"; sleep 305
done; send '{"cmd":"stop"}'; mark end
```

**Fast burst (5 min, about 23 strokes/s):**
`send '{"cmd":"stress","seed":7,"seconds":300,"press_ms":40,"burst_min":8,"burst_max":16,"interval_min_ms":20,"interval_max_ms":60,"idle_min_ms":0,"idle_max_ms":100}'`
= 6815 presses in the sim, at most 2 lines low together.  Harder: `press_ms` 20,
`interval_min_ms` 10 (the floor), `interval_max_ms` 50, about 30/s.  Whether sandswing sees a
20-40 ms press is **unconfirmed**; find its shortest with *Press* at 20, 40, 80 ms (README).

**Same seed, same events.**  The generator is the rig's own xorshift32 (`rng.py`), the same
on PC and Pico.  Same `seed` **and** same options give the same strokes at the same offsets
(checked: two runs equal, another seed differs).  Expected count, run in the sandtest repo:
`python3 -c "import sys;sys.path.insert(0,'src');from patterns import Stress;print(sum(e[2]=='down' for e in Stress(seed=4242,seconds=7200).events()))"`
prints 19404.  Compare with the page's *presses sent* before and after (lifetime counter;
`player.run_presses` in `GET /status` is per run).

**Watch-outs.**  Nothing else may send *Press/Play/Stress* during the run.  While a run is
going the rig does not retry Wi-Fi, so if its Wi-Fi drops the run still finishes but you
cannot STOP it (power off, or the USB console).  The open, visible Sandtest page polls the
rig every second; the rig skips a poll only when an edge is under 12 ms away.  Whether that
delays edges is **unconfirmed**; the page's *worst lateness* shows it.  Close the tab for a quiet run.

## How to see what happened (desk Pi)

* `~/pico-serial.log`: everything the **sandswing** Pico prints on USB, with a PC timestamp;
  strokes are `ch N TRIGGER ...` lines.  Link lines:
  `grep -E ' link (send_(backoff|degraded|calmer|ok)|link_dead|wifi_lost)' ~/pico-serial.log`
  * `send_backoff`: a send failed or stalled; the Pico holds off and shrinks the replay
  * `send_degraded`: hold over, still on a reduced level;  `send_calmer`: quiet spell, level down;  `send_ok`: back to normal
  * `wifi_lost`: Wi-Fi link lost;  `link_dead`: Wi-Fi up but nothing heard, radio reset

  Names and meaning are from sandswing's `docs/link-health.md` (`swing-replay` checkout);
  that the Pico's build has them is **unconfirmed**.
* `~/pico-net.log`: the outside watcher: `PING lost` / `PING back after N s`, `HTTP /status
  failing` / `HTTP back`, and `ok http` about every 64 s.  Mark every phase:
  `echo "$(date '+%F %T') MARK <name>" >> ~/pico-net.log`
* `python3 ~/Downloads/net-vs-trigger.py`: a watcher health check first (WARN = do not trust
  the table), then per MARK phase: minutes, strokes, ping drops, seconds down, drops/hour,
  then each drop with the strokes in the 10 s before it.  A phase runs to the next MARK, so
  end with `MARK end`.
* Rig side: the page's *presses sent*, *worst lateness*, *loop max*, or `curl http://$RIG/status`.
  The rig's own edge lines (`12.345 ch 3 PRESS`) are on its USB console, not in `pico-serial.log`.
