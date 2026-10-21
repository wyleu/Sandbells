"""manage.py ingest_events -- store the concentrator's sand.event/v1 stream.

    python manage.py ingest_events                     # URL from settings / default
    python manage.py ingest_events --url ws://192.168.0.81/ws -v 2

SIGTERM / SIGINT stop the loop; the buffer is flushed before exit.
Exits with EXIT_CONFIG_ERROR (no restart loop under systemd) if the
websocket-client library is missing.
"""

import logging
import signal
import sys
import threading

from django.core.management.base import BaseCommand, CommandError

from events import constants as C
from events import wsclient
from events.config import resolve_url
from events.ingest import Ingest
from events.store import EventStore

STOP_SIGNALS = (signal.SIGTERM, signal.SIGINT)
VERBOSITY_DEBUG = 2              # manage.py -v 2


def make_stop_handler(stop):
    def handler(signum, frame):
        logging.getLogger(C.LOGGER_NAME).info(
            "signal %s: flushing and stopping", signal.Signals(signum).name)
        stop.set()
    return handler


def install_signal_handlers(stop):
    """-> previous handlers, for restore_signal_handlers()."""
    handler = make_stop_handler(stop)
    previous = {s: signal.getsignal(s) for s in STOP_SIGNALS}
    for s in STOP_SIGNALS:
        signal.signal(s, handler)
    return previous


def restore_signal_handlers(previous):
    for s, h in previous.items():
        signal.signal(s, h)


def setup_logging(verbosity):
    logger = logging.getLogger(C.LOGGER_NAME)
    if not logger.handlers:
        h = logging.StreamHandler(sys.stderr)        # journald adds the time
        h.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        logger.addHandler(h)
        logger.propagate = False
    logger.setLevel(logging.DEBUG if verbosity >= VERBOSITY_DEBUG
                    else logging.INFO)
    return logger


class Command(BaseCommand):
    help = "Read sand.event/v1 from the concentrator WebSocket into the DB."

    def add_arguments(self, parser):
        parser.add_argument(
            "--url", default=None,
            help="WebSocket URL (default: status.devices[] family '%s' ws_url "
                 "in settings.json, else %s)"
                 % (C.CONCENTRATOR_FAMILY, C.WS_DEFAULT_URL))

    def handle(self, *args, **opts):
        if not wsclient.library_available():
            raise CommandError(
                "Python package websocket-client is not installed (module "
                "'%s'). Install it in this venv:  pip install %s"
                % (C.WS_LIBRARY_MODULE, C.WS_LIBRARY_PIP),
                returncode=C.EXIT_CONFIG_ERROR)
        log = setup_logging(opts.get("verbosity", 1))
        url, source = resolve_url(opts.get("url"))
        log.info("ingest from %s (%s)", url, source)
        stop = threading.Event()
        previous = install_signal_handlers(stop)
        try:
            ingest = Ingest(EventStore())
            wsclient.run(url, ingest, stop)
        finally:
            restore_signal_handlers(previous)
