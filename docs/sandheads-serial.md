# Sandheads page over USB (no Wi-Fi)

`/farm/heads/` works with the concentrator's USB plugged into this Pi
(`link.ring_send` "off").  It picks USB when `sandbells-ingest-serial` has
the Pico's data port open (or `?via=serial` / `?via=ws`).

* **Commands, page -> Pico:** POST `/farm/heads/serial/cmd/` (CSRF) ->
  checked (`events/serialheads.check_command`: only `{"cmd":"align"}`
  with ch 1-16 and a ±1 step, `thr_mid`, `scope` or `info`) -> unix
  datagram `/run/sandbells-ingest/serial_cmd.sock` -> `ingest_serial`
  (still the one owner of `/dev/ttyACM1`) checks again and writes the line.
  503: ingest_serial is not listening.
* **Readings and acks, Pico -> page:** MIDI Control Change on the USB MIDI
  out, channel 16 (map: sandswing `docs/align-scope.md` "MIDI CC map";
  numbers mirrored in `events/constants.py` `HEADS_CC_*`).  `ingest_midi`
  decodes them (`events/headscc.py`) into the same `align` / `align_ack`
  docs as /ws and keeps the newest in `/run/sandbells-ingest/midi_heads.json`.
  CCs are never strokes.  Only sent while the page keeps the scope alive.
* **Poll:** GET `/farm/heads/serial/?after=N&midi_after=M` every 400 ms:
  the newer docs, plus the head kinds and tower from the serial heartbeat.
* **Mid button:** threshold to the middle of its limits (`thr_mid`, 32768
  with the default limits).  Live only, like ±; not saved.
* While strokes are in progress the Pico sends only the PT level (marked
  busy); adjustments are refused until the tower is quiet.
* The trace over MIDI is one sample per report (every 500 ms; low if the
  beam broke since the last one): enough to see a break, not its shape.

## PT level log

`ingest_serial` stores the heartbeat's PT level (`pt`: channel, volts,
spread) with the threshold target/readback as `HeadLevel` rows, at most one
per head every 5 min (`PT_LOG_EVERY_S`).  CSV: `/farm/heads/pt-log.csv?days=7`
(linked from the page; days 1-366).  Needs `manage.py migrate` (0003).

## Line-up: "Find best brightness" (head with the PT wire)

A new head goes in channel 1 (the Orange/White PT wire).  On its panel:
type the number written on the head, keep the tower quiet, press **Find
best brightness**.  The Pico steps the laser drive from full down to the
floor (sandswing `sweep.py`); each point (drive, PT level, laser mA) comes
back as an `align_sweep` doc (CC_SWEEP report) and the curve fills in.
**Stop**, a stroke, a beam break or the timeout ends it and the Pico puts
the drive back.  At the end the page suggests the lowest drive whose PT is
within `plateau_frac` of the full-drive PT, plus `margin_frac`, and a
threshold in the same proportion to the PT as now; under `min_range_v` of
PT change it suggests nothing.  Defaults `HEADS_SWEEP_DEFAULTS`; override
in settings.json `"sandheads": {"sweep": {...}}` (read only).

* **Use this** sets the suggestion live (`use`), nothing kept.
* **Save for channel N** keeps the head's live drive and threshold with its
  number in the Pico's NVM for channel N (`save`); used at every start in
  place of the defaults.  The saved list (`align_slot` docs, asked with
  `saved` when the page connects) has a **Forget** (two presses) per channel.
* Every finished or stopped sweep is logged (`HeadSweep`, POST
  `/farm/heads/sweep-log/`); CSV `/farm/heads/sweep-log.csv?days=30`.
  Needs `manage.py migrate` (0004).

## Stuck heads and PT polarity (sw-stuck-unlock)

- If the tower is awake only because a head is stuck (held or flickering, no
  clear gap for the Pico's `tune.stuck_after_s`), the reports carry `stuck`
  and the threshold / drive buttons work again; the pill says so.  Sweep and
  Save still wait for a quiet tower.
- `lit_low` (the Pico's `heads.pt_light`, default "lowers"): more light pulls
  the PT down and the comparator low.  The trace shows light green and no
  light purple, and the suggestion is worked out from the light side.

## Chatter test (sw-chatter)

Does a laser drive below 100 % (the laser chopped by its PWM) make the
comparator chatter?  Each head's panel has a **Chatter test**: pick a drive %
and a PWM speed, then **Start**; **Run the set** does 100 %, 52 % and 25 % at
today's speed (1 kHz) and then the last one at `fast_pwm_hz` (20 kHz).
**Stop** stops sandtest (`{"cmd":"stop"}`), keeps what was counted, and puts
the drive and PWM speed back.  Nothing is kept on the Pico: drive and PWM
speed are live only, and both go back at the end of every run.

Per run the page sends, in order (the align command path; each waits for
its ack, "tower not quiet" / "too fast" asked again every 1.5 s for a minute):

1. `{"cmd":"align","ch":N,"use":[drive,null]}` and, if different from
   now, `{"cmd":"align","ch":N,"pwm_hz":HZ}` (all lasers: they share PWM
   slices);
2. sandtest (`/sandtest/cmd`), only when a sandtest position is picked:
   `{"cmd":"sweep","mode":"sweep","from_deg":S-pad,"to_deg":S,"speed_dps":v,"cycles":1}`
   to wait just outside the window, polling `/sandtest/status` until it has
   moved and stopped;
3. `{"cmd":"align","ch":N,"chatter":"start"}`;
4. sandtest `{"cmd":"sweep","mode":"sweep","from_deg":S,"to_deg":E,"speed_dps":v,"cycles":passes}`,
   polled until done (S/E = the head's angle + the face's offset from
   sandtest's status, -/+ half its window + `pad_deg`);
5. half a second later `{"cmd":"align","ch":N,"chatter":"stop"}`: the Pico
   sends the counts (`align_chatter`) and the page logs the run.

With "Vane by hand" (no sandtest) a run counts until **Stop**.

The counts (CC report, channel 16): CC 117 state (1 counting, 0 stopped),
then 14-bit pairs 26/58 transitions, 27/59 clean (one edge), 28/60 most
edges in one transition, 29/61 mean edges x10 (16383: none), 30/62 longest
burst ms, 31/63 spurious edges (an even burst: no change of state).  Every
ack now carries the lasers' PWM speed: CC 14/46, in units of 10 Hz.

Results: the table under the buttons (newest first), green when every
transition was clean.  Kept in `HeadChatter` (POST/GET
`/farm/heads/chatter-log/`); CSV `/farm/heads/chatter-log.csv?days=30`.
Needs `manage.py migrate events` (0005).  The expected transitions are
4 per pass (the vane crosses the beam twice per round trip).

Settings (read only), settings.json `"sandheads": {"chatter": {...}}`,
defaults `HEADS_CHATTER_DEFAULTS`: `passes` 10, `speed_dps` 4.0, `pad_deg`
2.0, `face` "reflector", `fast_pwm_hz` 20000, `drives_pct` [100, 52, 25].
