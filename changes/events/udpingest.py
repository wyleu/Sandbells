"""udpingest.py -- the concentrator's tier-3 stream: one sand.event/v1 (or
sand.panel/v1 heartbeat) per UDP datagram, handed to the same Ingest as the
WebSocket path (parse, gap tracking, store).  No Django import here.

Nothing is acknowledged or resent: the Pico never waits for the network
(CircuitPython's TCP send can sit 10 s in lwIP's ERR_MEM loop; its UDP send
fails at once).  A lost datagram shows as a seq gap.
"""

import logging
import socket

from events import constants as C

log = logging.getLogger("events.udpingest")


def open_socket(host=C.UDP_INGEST_HOST, port=C.UDP_INGEST_PORT, idle_s=C.UDP_IDLE_S):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, port))
    s.settimeout(idle_s)
    return s


def serve(sock, ingest, stop, max_b=C.UDP_MAX_B):
    """Until stop is set: each datagram -> ingest.handle_frame(text); a quiet
    second -> ingest.idle().  Flushes on the way out.  Returns datagrams seen."""
    n = 0
    ingest.new_connection()
    try:
        while not stop.is_set():
            try:
                data, peer = sock.recvfrom(max_b + 1)
            except socket.timeout:
                ingest.idle()
                continue
            n += 1
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                ingest.bad_frame(data)
                continue
            ingest.handle_frame(text)
            ingest.maybe_summary()
    finally:
        ingest.flush()
    return n
