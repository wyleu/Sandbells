"""The main bell page (home, kiosk_bells.js + #bell-circle): a stroke or trigger event with a
bell number swings THAT bell's coloured clapper with the same movement as pressing its pad
(BellBand.settleDemo, through kiosk_bells.js strike()); the bell, the other bells and the circle
stay still.  The event rule, the choice of bell and the press movement are tested in
js_tests/bell_motion.test.js (run by AlignJsTests / PowerJsTests with the rest of js_tests);
here: the page loads the script cache-busted before kiosk_bells.js, the feed and the pad press
share one path that only draws, and the old whole-bell movement (bell_motion.css) is gone."""
import re
from pathlib import Path

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

HERE = Path(__file__).resolve().parent
JS = HERE / "static" / "js"


def positions(body, path):
    return [m.start() for m in re.finditer(r'%s\?v=[0-9a-z]+"' % re.escape(path), body)]


def code(name):
    return (JS / name).read_text().split("*/", 1)[-1]


class BellMotionPageTests(TestCase):
    def test_home_loads_the_script_cache_busted_before_kiosk_bells_and_no_motion_css(self):
        body = self.client.get(reverse("home")).content.decode()
        script = positions(body, "js/bell_motion.js")
        kiosk = positions(body, "js/kiosk_bells.js")
        self.assertEqual((len(script), len(kiosk)), (1, 1))
        self.assertLess(script[0], kiosk[0])
        self.assertIn('id="bell-circle"', body)
        self.assertNotIn("bell_motion.css", body)
        self.assertFalse((HERE / "static" / "css" / "bell_motion.css").exists())

    def test_the_feed_and_the_pad_press_use_one_strike_and_it_only_draws(self):
        src = (JS / "kiosk_bells.js").read_text()
        self.assertEqual(src.count("BellBand.settleDemo("), 1)          # only inside strike()
        strike = src.split("function strike(el, bell) {", 1)[1].split("}", 1)[0]
        self.assertEqual(strike.strip(), "BellBand.settleDemo(el, bell);")
        self.assertIn("window.BellMotion.create(el, function (bell) { strike(el, bell); })", src)
        self.assertRegex(src, r"onPadClick: function \(bell\) \{\s*strike\(el, bell\);\s*\}")
        # the press movement draws and nothing else: no socket, request, sound or message
        band = (JS / "bell_band.js").read_text()
        settle = band.split("function settleDemo", 1)[1].split("global.BellBand", 1)[0]
        for bad in ("send(", "fetch(", "XMLHttpRequest", "Howl", "postMessage", "WebSocket", ".play("):
            self.assertNotIn(bad, settle, bad)


class BellStrikeTargetTests(SimpleTestCase):
    def test_only_the_struck_bells_clapper_moves_never_the_circle_or_the_whole_bell(self):
        motion = code("bell_motion.js")
        self.assertIn("strike(bell);", motion)
        for gone in ("classList", "bell-quiver", "bell-motion-", "style"):
            self.assertNotIn(gone, motion, gone)
        band = (JS / "bell_band.js").read_text()
        self.assertNotIn("bell-quiver", band)
        settle = band.split("function settleDemo", 1)[1].split("global.BellBand", 1)[0]
        self.assertIn("setTape(host, bell,", settle)                    # the clapper group only
