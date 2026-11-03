"""manage.py ingest_midi -- store the Pico's bell strokes from its USB MIDI.

    python manage.py ingest_midi                       # find the 'Pico 2 W' card, raw, else seq
    python manage.py ingest_midi --device /dev/snd/midiC3D0 -v 2
    python manage.py ingest_midi --card "Pico 2 W" --transport seq

For a concentrator whose Wi-Fi is no use: its USB is plugged into this Pi.
Each NoteOn on MIDI channel MIDI_CHANNEL (sandswing: 1) is one stroke on
the channel MIDI_NOTE_TO_CH gives, stamped with this Pi's clock on arrival,
stored (src "midi") through the same Ingest / EventStore as ingest_udp, so
the Strokes page shows it.  midiingest.py has the details.
SIGTERM / SIGINT stop the loop; the buffer is flushed before exit.

One tmpfs file: MIDI_STATUS_PATH (midi_status.json: port, connected, notes,
last note time, errors; next to ingest_udp's status.json).  The link state
(link.json) is left to ingest_udp / ingest_events: MIDI has no heartbeats.
"""

import os
import threading

from django.core.management.base import BaseCommand

from events import constants as C
from events import midiingest
from events.ingest import Ingest
from events.store import EventStore
from events.management.commands.ingest_events import (
    install_signal_handlers, restore_signal_handlers, setup_logging)


class Command(BaseCommand):
    help = "Store bell strokes from the concentrator's USB MIDI (no Wi-Fi needed)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--card", default=os.environ.get(C.MIDI_CARD_ENV),
            help="ALSA card name substring to look for (default: any of %s; env %s)"
                 % (", ".join(repr(m) for m in C.MIDI_CARD_MATCH), C.MIDI_CARD_ENV))
        parser.add_argument(
            "--device", default=os.environ.get(C.MIDI_DEVICE_ENV),
            help="rawmidi device to read, no search (e.g. /dev/snd/midiC3D0; env %s)"
                 % C.MIDI_DEVICE_ENV)
        parser.add_argument("--transport", choices=C.MIDI_TRANSPORTS,
                            default=C.MIDI_TRANSPORT_AUTO,
                            help="raw device, ALSA seq (aseqdump), or auto: raw, seq if busy")
        parser.add_argument("--channel", type=int, default=C.MIDI_CHANNEL,
                            choices=range(C.MIDI_CHANNEL_ANY, C.MIDI_CHANNELS + 1),
                            help="MIDI channel, 1-16 (0: any; default %d)" % C.MIDI_CHANNEL)
        parser.add_argument("--reconnect", type=float, default=C.MIDI_RECONNECT_S,
                            help="seconds between looks for the port (default %.0f)"
                                 % C.MIDI_RECONNECT_S)
        parser.add_argument("--once", action="store_true",
                            help="stop after the first disconnect (a manual check)")

    def handle(self, *args, **opts):
        log = setup_logging(opts.get("verbosity", 1))
        match = (opts["card"],) if opts.get("card") else C.MIDI_CARD_MATCH
        device = opts.get("device")

        def find():
            return midiingest.find_port(match=match, device=device)

        log.info("ingest midi: %s, channel %s, transport %s",
                 device or "card matching " + " or ".join(repr(m) for m in match),
                 opts["channel"] or "any", opts["transport"])
        stop = threading.Event()
        previous = install_signal_handlers(stop)
        status = midiingest.MidiStatus(midiingest.midi_status_path())
        status.midi["looking_for"] = device or list(match)
        ingest = None
        try:
            ingest = Ingest(EventStore(), status=status)
            status.maybe_write(ingest, force=True)
            midiingest.run(ingest, stop, status, find=find, transport=opts["transport"],
                           maker=midiingest.StrokeMaker(channel=opts["channel"]),
                           reconnect_s=opts["reconnect"], once=opts["once"])
        finally:
            restore_signal_handlers(previous)
            if ingest is not None:
                status.stopped(ingest)
