"""udpingest.serve with a fake socket and a fake Ingest (no DB, no network)."""
import socket
import threading
import unittest

from events import udpingest


class FakeSock:
    def __init__(self, items, stop):
        self.items, self.stop = list(items), stop

    def recvfrom(self, n):
        if not self.items:
            self.stop.set()
            raise socket.timeout()
        item = self.items.pop(0)
        if item is None:
            raise socket.timeout()
        return item, ("10.42.0.81", 1)


class FakeIngest:
    def __init__(self):
        self.frames, self.bad, self.idles, self.flushed, self.new = [], 0, 0, 0, 0
        self.peers = []

    def new_connection(self):
        self.new += 1

    def handle_frame(self, text, peer=None):
        self.frames.append(text)
        self.peers.append(peer)

    def bad_frame(self, data, why=None, peer=None):
        self.bad += 1

    def idle(self):
        self.idles += 1

    def maybe_summary(self):
        pass

    def flush(self):
        self.flushed += 1


class ServeTests(unittest.TestCase):
    def test_each_datagram_is_one_frame_quiet_is_idle_and_it_flushes(self):
        stop = threading.Event()
        ing = FakeIngest()
        sock = FakeSock([b'{"seq": 1}', None, b'{"seq": 3}', b"\xff\xfe"], stop)
        n = udpingest.serve(sock, ing, stop)
        self.assertEqual(n, 3)
        self.assertEqual(ing.frames, ['{"seq": 1}', '{"seq": 3}'])   # seq 2 lost: a gap, no wait
        self.assertEqual(ing.bad, 1)
        self.assertGreaterEqual(ing.idles, 1)
        self.assertEqual(ing.flushed, 1)
        self.assertEqual(ing.peers, ["10.42.0.81", "10.42.0.81"])     # each frame's source IP

    def test_real_socket_round_trip(self):
        s = udpingest.open_socket("127.0.0.1", 0, 0.05)
        port = s.getsockname()[1]
        c = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        c.sendto(b'{"seq": 7}', ("127.0.0.1", port))
        stop = threading.Event()
        ing = FakeIngest()
        orig = ing.idle
        ing.idle = lambda: (orig(), stop.set())
        udpingest.serve(s, ing, stop)
        s.close()
        c.close()
        self.assertEqual(ing.frames, ['{"seq": 7}'])


if __name__ == "__main__":
    unittest.main()
