# Strokes over USB MIDI (`manage.py ingest_midi`)

When the concentrator's Wi-Fi is no use, plug the Pico 2 W's USB into
sandbells2.  sandswing already sends one USB MIDI NoteOn per bell stroke
(`src/ring.py`; a trigger plug press too, since sandswing 0cfd112).
`ingest_midi` reads those notes and stores each as a `stroke` in the same
Event table the Strokes page reads, so the display works with no network.

## What is read

| sandswing channel (body `ch`) | 1  | 2  | 3  | 4  | 5  | 6  | 7  | 8  |
|-------------------------------|----|----|----|----|----|----|----|----|
| MIDI note (`ring.NOTES`)      | 65 | 64 | 62 | 60 | 58 | 57 | 55 | 53 |

* MIDI channel **1** (`ring.open_midi`: adafruit `out_channel=0`).
  `--channel N` for another, `--channel 0` for any.
* The table is `events.constants.MIDI_NOTE_TO_CH`; the bell number comes
  from the Channel map (admin), as for UDP strokes: a MIDI stroke uses the
  `sandswing` rows unless there are `midi` rows for that channel.
* NoteOn velocity > 0 = a stroke.  NoteOff, NoteOn velocity 0, other
  channels and notes not in the table are only counted.
* MIDI has no timestamp.  Newer sandswing sends one with each stroke (the
  Pico's keypad stamp, a SysEx right after the NoteOn: "Stroke times from
  the Pico" below).  Without one, a stroke is stamped with this Pi's clock
  when the bytes are read (`utc_ms` = `time.time()`, `tick_ms` =
  `time.monotonic()`).  `acc`/`sync` left empty.
* Stored as sand.event/v1 through the same `Ingest` / `EventStore` as
  `ingest_udp` (batched: 64 events or 1 s).  `src` is **`midi`** (UDP ones
  are `sandswing`), `id` `sandswing-pico`, a new `boot_id` each start, body
  `{"ch", "note", "vel", "via": "midi", "stamped", ...}`.  A connect / unplug is also an
  `ingest` event (src `sandbells`).

## Stroke times from the Pico

USB MIDI arrival times jitter: on sandbells2 (2026-11-03) a ring whose
Pico keypad stamps were ±3 ms apart showed gaps of 3170-3244 ms by arrival.
So sandswing (src/midi_stamp.py, its docs/midi-stamp.md) sends right after
each stroke NoteOn one SysEx with that stroke's own stamp:

    F0 7D 53 01 sh sl cc t4 t3 t2 t1 t0 F7

`7D` the MIDI non-commercial manufacturer ID (any synth, e.g. Zynthian,
ignores it), `53` 'S', `01` the layout version, seq 14 bits (stroke stamps
1..16383 then 1; 0 = none yet), `cc` the bell channel 1-8 (`00` = a clock
message: the Pico's ms now, sent every 10 s when no stroke went), `t` the
Pico's tick ms, 35 bits, 7 per byte, most significant first.  Any other
SysEx (another ID, another version, another length) is skipped as before.
Read the same way over `seq` (aseqdump's "System exclusive" line).

* **Pairing.**  A NoteOn stroke is held until the stamp for its bell
  channel arrives, at most `MIDI_STAMP_WAIT_MS` (50 ms).  No stamp in time
  (older firmware, `midi.stamp_sysex` off, a lost SysEx): stored at its
  arrival, `stamped: false`, as before.  A stamp with no NoteOn waiting is
  counted (`orphans`).  An unplug or stop stores held strokes unstamped.
* **Offset.**  offset = min over the window (last 64 stamps, none older
  than 5 min) of (arrival `time.monotonic()` ms - Pico ms): the least
  delayed message.  Clock messages keep it fed between rings.
  `tick_ms` = Pico ms + offset (so the Strokes page's gaps, which use
  `tick_ms`, are the Pico's), `utc_ms` = that + (wall - monotonic now).
* **Body** of a stamped stroke: `{"ch", "note", "vel", "via": "midi",
  "pico_ms", "seq", "stamped": true, "offset_ms"}` (`offset_ms` = `utc_ms -
  pico_ms`).
* **Pico restart** (the window starts again, `reboots` + 1): a clock with
  seq 0 or a stroke stamp seq 1 after strokes (a soft reload: same ms
  scale, new seq), or a stamp more than 1 s before the last one where that
  cannot happen (a clock; a stroke stamp whose seq does not follow on).  A
  reconnect empties the window too (`window_resets`).
* **Lost stamps**: a stroke stamp's seq should be the last + 1, a clock's
  the last: `seq_gaps` / `seq_missing` in `midi.stamp` (not the Ingest's
  `seq_gaps`, which count this ingest's own event seq).

`midi_status.json` `midi.stamp`: `stamped`, `unstamped`, `clocks`,
`orphans`, `offset_ms` (wall ms - Pico ms), `offset_tick_ms`,
`offset_spread` (max - min of the window: the host jitter),
`offset_samples`, `reboots`, `window_resets`, `seq_gaps`, `seq_missing`,
`seq_odd`, `last_seq`, `last_pico_ms`, `wait_ms`, `held`.

Not proven on hardware yet: the offset's drift.  A min-filter assumes the
two clocks run at the same rate; a Pico crystal 30 ppm off moves the true
offset ~9 ms in the 5-min window (the min then lags it).  During a ring the
64-sample bound keeps the window to tens of seconds.

## Finding the Pico

The first card in `/proc/asound/cards` (or its `/proc/asound/cardN/midiD`
files) containing `Pico 2 W` or `CircuitPython`
(`MIDI_CARD_MATCH`); it reads `/dev/snd/midiC<card>D<first midi device>`.

    $ cat /proc/asound/cards
     3 [W              ]: USB-Audio - Pico 2 W
                          Raspberry Pi Pico 2 W at usb-xhci-hcd.1-1, full speed
    $ aconnect -l
    client 28: 'Pico 2 W' [type=kernel,card=3]
        0 'Pico 2 W CircuitPython usb_midi'

Overrides: `--card "<substring>"` / `SANDBELLS_MIDI_CARD`, or
`--device /dev/snd/midiC3D0` / `SANDBELLS_MIDI_DEVICE`.  Not there, or
unplugged: it looks again every 3 s (`--reconnect`), no busy loop.

## Raw device, or the ALSA sequencer (PipeWire)

`--transport auto` (default) opens the rawmidi device with plain Python
`os.read` (no package needed) and parses the bytes itself (running status,
NoteOn velocity 0 = off, real-time bytes skipped, SysEx skipped unless it
is the Pico's stamp).

A rawmidi **input is exclusive**.  If PipeWire (or anything else) is
subscribed to the Pico's sequencer port, the kernel holds the rawmidi
input open and `open()` fails with `EBUSY`.  `auto` then reads through the
ALSA sequencer instead: `aseqdump -p "Pico 2 W"` (package `alsa-utils`),
which is one more subscriber and shares the port with PipeWire.  The
journal says `... busy (PipeWire / an ALSA seq subscriber has it): reading
through the ALSA sequencer instead`, and `midi_status.json` has
`"transport": "seq"`.  Force either with `--transport raw|seq`.

To keep PipeWire off the MIDI ports altogether (then raw works), for the
user PipeWire runs as (e.g. the kiosk user):

    mkdir -p ~/.config/wireplumber/wireplumber.conf.d
    printf 'wireplumber.profiles = {\n  main = {\n    monitor.alsa-midi = disabled\n  }\n}\n' \
      > ~/.config/wireplumber/wireplumber.conf.d/90-no-midi.conf
    systemctl --user restart wireplumber pipewire

(WirePlumber 0.5; on 0.4 set `alsa.seq` off in its alsa-midi config, or
`systemctl --user mask pipewire pipewire.socket wireplumber` if nothing on
that Pi needs audio.)

## Status file

`/run/sandbells-ingest/midi_status.json` (`SANDBELLS_MIDI_STATUS`), next to
ingest_udp's `status.json`, rewritten every 5 s and on a change (at most
once a second): ingest_udp's counters plus a `midi` section:
`looking_for`, `port`, `transport`, `connected`, `since_ms`,
`notes_received`, `note_ons`, `note_offs`, `strokes`, `other_channel`,
`unmapped`, `last_note_ms`, `last_note`, `connects`, `disconnects`,
`errors`, `recent_errors`, `parser_skipped`, `sysex_skipped` (SysEx that
were not stamps), and `stamp` (below).

`link.json` is not written: MIDI has no heartbeats, so the Strokes page's
link widget still judges the Wi-Fi link (it shows LOST with Wi-Fi off; the
strokes still appear).

## Install on sandbells2

    sudo install -m 0644 ~/Code/Sandbells/systemd/sandbells-ingest-midi.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now sandbells-ingest-midi

(or `./sandbells_sync_units.sh`, then the `enable --now`).  Check:

    systemctl status sandbells-ingest-midi
    journalctl -u sandbells-ingest-midi -f
    cat /run/sandbells-ingest/midi_status.json

It can run beside `sandbells-ingest-udp`; with both links working a stroke
is stored twice (src `sandswing` and src `midi`).  Stopping
`sandbells-ingest-udp` removes `/run/sandbells-ingest` (its
RuntimeDirectory); restart `sandbells-ingest-midi` after that so its status
file comes back.  By hand: `python manage.py ingest_midi -v 2 --once`
reads until the Pico is unplugged.
