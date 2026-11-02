"""udpingest.py -- the concentrator's tier-3 stream: one sand.event/v1 (or
sand.panel/v1 heartbeat) per UDP datagram, handed to the same Ingest as the
WebSocket path (parse, gap tracking, store).  No Django import here.

Nothing is resent: the Pico never waits for the network (CircuitPython's
TCP send can sit 10 s in lwIP's ERR_MEM loop; its UDP send fails at once).
A lost datagram shows as a seq gap.  Back chat: each heartbeat is answered
with one sand.ack/v1 datagram ({"schema", "boot_id", "seq"}, < 100 B) to
its source (ip, port) on this socket, at most one per sender per
UDP_ACK_MIN_S; a failed sendto is counted, never retried.  The Pico reads
it without waiting (link LED green; rejoin when acks stop).
"""

import json
import logging
import socket
import time

from events import constants as C

log = logging.getLogger("events.udpingest")


def open_socket(host=C.UDP_INGEST_HOST, port=C.UDP_INGEST_PORT, idle_s=C.UDP_IDLE_S):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, port))
    s.settimeout(idle_s)
    return s


def ack_bytes(boot_id, seq):
    return json.dumps({"schema": C.SCHEMA_ACK_V1, "boot_id": boot_id, "seq": seq},
                      separators=(",", ":")).encode("utf-8")


class Acker:
    """One ack per heartbeat, at most one per sender IP per min_s."""
    def __init__(self, clock=time.monotonic, min_s=C.UDP_ACK_MIN_S):
        self.clock, self.min_s = clock, float(min_s)
        self.last = {}                        # ip -> when the last ack went

    def __call__(self, sock, ingest, peer):
        take = getattr(ingest, "take_ack", None)
        a = take() if take is not None else None
        if a is None or not isinstance(peer, tuple):
            return False
        now = self.clock()
        ip = peer[0]
        if ip in self.last and now - self.last[ip] < self.min_s:
            ingest.acks_limited += 1
            return False
        self.last[ip] = now
        try:
            sock.sendto(ack_bytes(*a), peer)
        except OSError as e:                  # incl. socket.timeout: counted, never retried
            ingest.ack_errors += 1
            if ingest.ack_errors == 1 or ingest.ack_errors % C.UDP_ACK_LOG_EVERY == 0:
                log.warning("ack to %s:%s failed: %s (%d this run)", ip, peer[1], e,
                            ingest.ack_errors)
            return False
        ingest.acks_sent += 1
        return True


def serve(sock, ingest, stop, max_b=C.UDP_MAX_B, acker=None):
    """Until stop is set: each datagram -> ingest.handle_frame(text, peer=its
    source IP: a heartbeat's is where the Pico is now); a quiet
    second -> ingest.idle(); a heartbeat -> one ack to its (ip, port).
    Flushes on the way out.  Returns datagrams seen."""
    n = 0
    acker = acker or Acker()
    ingest.new_connection()
    try:
        while not stop.is_set():
            try:
                data, peer = sock.recvfrom(max_b + 1)
            except socket.timeout:
                ingest.idle()
                continue
            n += 1
            ip = peer[0] if isinstance(peer, tuple) else peer
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                ingest.bad_frame(data, C.R_NOT_UTF8, peer=ip)
                continue
            ingest.handle_frame(text, peer=ip)
            acker(sock, ingest, peer)              # a heartbeat: one ack back, never waits
            ingest.maybe_summary()
    finally:
        ingest.flush()
    return n
