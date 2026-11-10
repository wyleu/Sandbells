# Concentrator status over USB serial (manage.py ingest_serial)

No Wi-Fi needed.  The Pico's USB cable into this Pi carries its REPL
console (`/dev/ttyACM0`), its usb_cdc data port (`/dev/ttyACM1`) and USB
MIDI.  sandswing (`serial_status.py`, settings `serial_status.period_s`,
default 10 s) writes its slim heartbeat as one JSON line on the data port.

`sandbells-ingest-serial` (`manage.py ingest_serial`, `events/serialingest.py`)
finds the data port (the Pico's CDC interface named "CircuitPython CDC2
control", else interface 2, else `/dev/serial/by-id/...-if02`), never the
REPL (interface 0, refused even with `--device`), never the MIDI device,
and keeps the newest good line in `/run/sandbells-ingest/serial_status.json`
(same file style as `midi_status.json`).  Nothing goes in the DB.
Unplugged: it looks again every 3 s.

Shown on:

* the sandswing status page (`/farm/status/<n>/`): a serial line younger
  than 3 periods + 5 s (35 s) is shown and the Pico's `/status` is not
  asked over Wi-Fi at all; an older one only when Wi-Fi does not answer
  either, marked STALE.  A registry entry with a `"uid"` only takes lines
  from that Pico.
* the Ingest page (`/events/ingest/`): port, connected, lines, last heartbeat.

Install (once):

    sudo install -m 0644 ~/Code/Sandbells/systemd/sandbells-ingest-serial.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now sandbells-ingest-serial

Check:

    journalctl -u sandbells-ingest-serial -n 5 --no-pager
    python3 -m json.tool /run/sandbells-ingest/serial_status.json | head -30

Overrides in the unit: `Environment=SANDBELLS_SERIAL_DEVICE=/dev/ttyACM1`
or `Environment=SANDBELLS_SERIAL_MATCH=<USB product substring>`.
