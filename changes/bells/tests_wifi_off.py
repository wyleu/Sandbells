"""Sandswing "Wi-Fi off until reboot" (bells/actions.py SANDSWING); plain unittest."""
import json
import unittest

from bells import actions
from events.linkstate import LinkState

UID = "7091CDAB9DBD5305"
HB = {"type": "heartbeat", "boot_id": "7091cdab", "body": {"uid": UID}}
# the farm entry exactly as it is: no new field
PICO = {"id": "sandswing", "name": "sandswing", "kind": "pico", "family": "sandswing",
        "status_url": "http://192.168.0.81/status", "ws_url": "ws://192.168.0.81/ws",
        "alt_status_urls": ["http://10.42.0.81/status"], "alt_ws_urls": ["ws://10.42.0.81/ws"]}


def state_after(peer):
    """The link state the UDP ingest leaves after one heartbeat from peer."""
    st = LinkState(None, wall=lambda: 1793800000.0)
    st.heartbeat(HB, peer)
    return st.doc


def press(state, fail=()):
    sent = []

    def send(d, a):
        if a[0] in fail:
            raise OSError("unreachable")
        sent.append((json.loads(d), a))
    r = actions._sandswing_wifi_off(PICO, {}, send=send, link=lambda: state,
                                    clock=lambda: 1793800000.5)
    return r, sent


class WifiOff(unittest.TestCase):
    def test_goes_to_the_last_udp_heartbeat_source_at_the_tower(self):
        r, sent = press(state_after("10.42.0.81"))
        self.assertTrue(r["ok"])
        self.assertEqual([a for _, a in sent], [("10.42.0.81", actions.SANDSWING_CMD_PORT)])
        doc = sent[0][0]
        self.assertEqual((doc["schema"], doc["cmd"], doc["uid"], doc["boot_id"], doc["seq"]),
                         ("sand.cmd/v1", "wifi_off", UID, "7091cdab", 1793800000500))

    def test_and_at_home(self):
        _r, sent = press(state_after("192.168.0.81"))
        self.assertEqual([a[0] for _, a in sent], ["192.168.0.81"])

    def test_no_heartbeat_source_falls_back_to_status_then_alt_urls(self):
        st = state_after(None)                     # e.g. a heartbeat over the WebSocket
        r, sent = press(st)
        self.assertEqual([a[0] for _, a in sent], ["192.168.0.81", "10.42.0.81"])
        self.assertEqual(len({d["seq"] for d, _ in sent}), 1)   # one seq: the Pico takes one
        r, sent = press(st, fail=("192.168.0.81",))             # one unreachable is fine
        self.assertEqual(r["sent_to"], ["10.42.0.81"])

    def test_peer_of_another_uid_is_not_used(self):
        st = state_after("10.42.0.99")
        st["pico_peers"] = {"OTHER": st["pico_peers"][UID]}
        _r, sent = press(st)
        self.assertEqual([a[0] for _, a in sent], ["192.168.0.81", "10.42.0.81"])

    def test_no_heartbeat_yet_is_refused_not_guessed(self):
        with self.assertRaises(actions.ActionError) as cm:
            actions._sandswing_wifi_off(PICO, {}, send=lambda d, a: None, link=lambda: {})
        self.assertEqual(cm.exception.status, 409)

    def test_all_sends_failing_is_504(self):
        with self.assertRaises(actions.ActionError) as cm:
            press(state_after(None), fail=("192.168.0.81", "10.42.0.81"))
        self.assertEqual(cm.exception.status, 504)

    def test_ingest_keeps_the_udp_source_of_a_real_heartbeat_frame(self):
        from events.ingest import Ingest
        ing = Ingest(store=None, last_stored=lambda *a: None)
        frame = json.dumps(dict(HB, schema="sand.panel/v1", src="concentrator", seq=1))
        ing.handle_frame(frame, peer="10.42.0.81")
        self.assertEqual(ing.link.doc["pico_peers"][UID]["ip"], "10.42.0.81")
        ing.handle_frame(frame)                     # WebSocket path: no peer, kept as it was
        self.assertEqual(ing.link.doc["pico_peers"][UID]["ip"], "10.42.0.81")

    def test_run_routes_only_wifi_off_for_sandswing(self):
        self.assertIn(("wifi", "off"), actions.SANDSWING)
        with self.assertRaises(actions.ActionError) as cm:     # as before: no action_url
            actions.run({"id": "pico", "family": "sandswing"}, "fan", "nudge_down")
        self.assertEqual(cm.exception.status, 501)


if __name__ == "__main__":
    unittest.main()
