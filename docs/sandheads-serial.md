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
