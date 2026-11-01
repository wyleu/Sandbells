"""Sandswing "Wi-Fi off until reboot" (bells/actions.py SANDSWING); plain unittest."""
import json
import unittest

from bells import actions

HB = {"boot_id": "7091cdab", "body": {"uid": "7091CDAB9DBD5305"}}
PICO = {"id": "concentrator", "family": "sandswing", "status_url": "http://192.168.0.81/status"}


class WifiOff(unittest.TestCase):
    def test_sends_one_datagram_with_uid_boot_and_a_rising_seq(self):
        sent = []
        r = actions._sandswing_wifi_off(PICO, {}, send=lambda d, a: sent.append((d, a)),
                                        heartbeat=lambda: HB, clock=lambda: 1793800000.5)
        self.assertTrue(r["ok"])
        doc = json.loads(sent[0][0])
        self.assertEqual(sent[0][1], ("192.168.0.81", actions.SANDSWING_CMD_PORT))
        self.assertEqual((doc["schema"], doc["cmd"], doc["uid"], doc["boot_id"], doc["seq"]),
                         ("sand.cmd/v1", "wifi_off", "7091CDAB9DBD5305", "7091cdab", 1793800000500))

    def test_no_heartbeat_yet_is_refused_not_guessed(self):
        with self.assertRaises(actions.ActionError) as cm:
            actions._sandswing_wifi_off(PICO, {}, send=lambda d, a: None, heartbeat=lambda: None)
        self.assertEqual(cm.exception.status, 409)

    def test_run_routes_only_wifi_off_for_sandswing(self):
        self.assertIn(("wifi", "off"), actions.SANDSWING)
        with self.assertRaises(actions.ActionError) as cm:     # as before: no action_url
            actions.run({"id": "pico", "family": "sandswing"}, "fan", "nudge_down")
        self.assertEqual(cm.exception.status, 501)


if __name__ == "__main__":
    unittest.main()
