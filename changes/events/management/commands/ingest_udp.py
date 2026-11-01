"""manage.py ingest_udp -- store the concentrator's tier-3 UDP stream.

    python manage.py ingest_udp                 # 0.0.0.0:5055 (events.constants)
    python manage.py ingest_udp --port 5055 -v 2

For a concentrator with settings.json "link": {"ring_send": "udp",
"udp_host": "<this Pi's address>"}.  Same parser, gap tracker and store as
ingest_events; it does not connect to the Pico at all.
SIGTERM / SIGINT stop the loop; the buffer is flushed before exit.
"""

import threading

from django.core.management.base import BaseCommand

from events import constants as C
from events import udpingest
from events.ingest import Ingest
from events.linkstate import LinkState, link_state_path
from events.store import EventStore
from events.management.commands.ingest_events import (
    install_signal_handlers, restore_signal_handlers, setup_logging)


class Command(BaseCommand):
    help = "Store sand.event/v1 datagrams from the concentrator (link.ring_send udp)."

    def add_arguments(self, parser):
        parser.add_argument("--host", default=C.UDP_INGEST_HOST)
        parser.add_argument("--port", type=int, default=C.UDP_INGEST_PORT)

    def handle(self, *args, **opts):
        log = setup_logging(opts.get("verbosity", 1))
        sock = udpingest.open_socket(opts["host"], opts["port"])
        log.info("ingest udp on %s:%d", opts["host"], opts["port"])
        stop = threading.Event()
        previous = install_signal_handlers(stop)
        try:
            ingest = Ingest(EventStore(), link=LinkState(link_state_path()))
            udpingest.serve(sock, ingest, stop)
        finally:
            restore_signal_handlers(previous)
            sock.close()
