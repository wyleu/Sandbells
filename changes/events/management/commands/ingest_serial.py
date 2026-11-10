"""manage.py ingest_serial -- the concentrator's status over its USB data port.

    python manage.py ingest_serial                      # find the Pico's data port (ttyACM1)
    python manage.py ingest_serial --device /dev/ttyACM1 -v 2

For a concentrator whose Wi-Fi is no use: its USB is plugged into this Pi.
sandswing (serial_status.py) writes its heartbeat as one JSON line every
serial_status.period_s on usb_cdc.data, the second CDC interface; the REPL
console (the first, ttyACM0) is never opened and MIDI is not touched.
serialingest.py has the details.  SIGTERM / SIGINT stop the loop.

One tmpfs file: SERIAL_STATUS_PATH (serial_status.json: port, connected,
line counters, errors, and the newest heartbeat), next to ingest_udp's
status.json and ingest_midi's midi_status.json.  Nothing goes in the DB;
the sandswing status page and the Ingest page read the file.
"""

import os
import threading

from django.core.management.base import BaseCommand

from events import constants as C
from events import serialingest
from events.management.commands.ingest_events import (
    install_signal_handlers, restore_signal_handlers, setup_logging)


class Command(BaseCommand):
    help = "Keep the concentrator's newest status line from its USB data port (no Wi-Fi needed)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--match", default=os.environ.get(C.SERIAL_MATCH_ENV),
            help="USB product substring to look for (default: any of %s; env %s)"
                 % (", ".join(repr(m) for m in C.SERIAL_PRODUCT_MATCH), C.SERIAL_MATCH_ENV))
        parser.add_argument(
            "--device", default=os.environ.get(C.SERIAL_DEVICE_ENV),
            help="tty to read, no search (e.g. /dev/ttyACM1; never the REPL; env %s)"
                 % C.SERIAL_DEVICE_ENV)
        parser.add_argument("--reconnect", type=float, default=C.SERIAL_RECONNECT_S,
                            help="seconds between looks for the port (default %.0f)"
                                 % C.SERIAL_RECONNECT_S)
        parser.add_argument("--once", action="store_true",
                            help="stop after the first disconnect (a manual check)")

    def handle(self, *args, **opts):
        log = setup_logging(opts.get("verbosity", 1))
        match = (opts["match"],) if opts.get("match") else C.SERIAL_PRODUCT_MATCH
        device = opts.get("device")

        def find():
            return serialingest.find_port(match=match, device=device)

        log.info("ingest serial: %s", device or "data port of USB device matching "
                 + " or ".join(repr(m) for m in match))
        stop = threading.Event()
        previous = install_signal_handlers(stop)
        status = serialingest.SerialStatus(serialingest.serial_status_path())
        status.serial["looking_for"] = device or list(match)
        try:
            status.maybe_write(None, force=True)
            serialingest.run(stop, status, find=find, reconnect_s=opts["reconnect"],
                             once=opts["once"])
        finally:
            restore_signal_handlers(previous)
            status.stopped(None)
