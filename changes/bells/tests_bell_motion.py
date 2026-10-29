"""The main bell page (home, kiosk_bells.js + #bell-circle) moves the ONE bell that struck a few
px diagonally when a stroke or trigger event with a bell number arrives (static/js/bell_motion.js
+ css/bell_motion.css); the rest of the circle stays still.  The event rule, the choice of bell
and the restart are tested in js_tests/bell_motion.test.js (run by AlignJsTests / PowerJsTests
with the rest of js_tests); here: the page loads both files cache-busted, the script before
kiosk_bells.js, the length and distance come from events.constants only, and the CSS keeps to
the cheap kind of animation."""
import re
from pathlib import Path

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from events import constants as C

HERE = Path(__file__).resolve().parent
CSS = HERE / "static" / "css" / "bell_motion.css"
JS = HERE / "static" / "js"


def positions(body, path):
    return [m.start() for m in re.finditer(r'%s\?v=[0-9a-z]+"' % re.escape(path), body)]


class BellMotionPageTests(TestCase):
    def test_home_loads_style_and_script_cache_busted_before_kiosk_bells(self):
        body = self.client.get(reverse("home")).content.decode()
        self.assertEqual(len(positions(body, "css/bell_motion.css")), 1)
        script = positions(body, "js/bell_motion.js")
        kiosk = positions(body, "js/kiosk_bells.js")
        self.assertEqual((len(script), len(kiosk)), (1, 1))
        self.assertLess(script[0], kiosk[0])
        self.assertIn('id="bell-circle"', body)

    def test_kiosk_script_builds_the_movement_once_for_the_event_feed(self):
        # the movement is driven by bell_feed.js (see tests_bell_feed.py), not by a WebSocket frame
        src = (JS / "kiosk_bells.js").read_text()
        self.assertEqual(src.count("BellMotion.create(el, look)"), 1)
        self.assertNotIn("BellMotion.create(el)", src)


class BellMotionCssTests(SimpleTestCase):
    def test_small_short_transform_only_and_reduced_motion_respected(self):
        css = CSS.read_text()
        self.assertEqual(re.findall(r"animation: bell-motion-[01] (\S+) ease-out 1;", css),
                         ["var(--bell-motion-ms)"] * 2)
        self.assertEqual(set(re.findall(r"translate\(([^,]+), ([^)]+\)?)\)", css)),
                         {("0", "0"), ("var(--bell-motion-px)", "var(--bell-motion-px)")})
        self.assertNotRegex(css.split("*/", 1)[1], r"\d+(ms|px)", "length and distance are not written here")
        self.assertEqual((C.BELL_QUIVER_MS, C.BELL_QUIVER_PX), (350, 4), "the same small, short movement")
        self.assertRegex(css, r"prefers-reduced-motion: reduce\)\s*\{[^}]*animation: none")
        for bad in ("filter", "blur", "box-shadow", "opacity", "width", "height", "left", "top",
                    "margin", "will-change", "infinite"):
            self.assertNotRegex(css.split("*/", 1)[1], r"\b%s\b" % bad, bad)


class BellQuiverTargetTests(SimpleTestCase):
    def test_only_the_struck_bells_group_moves_never_the_circle(self):
        src = (JS / "bell_motion.js").read_text()
        code = src.split("*/", 1)[1]
        self.assertIn(""".bell-pad[data-bell="' + bell + '"] .bell-quiver""", code)
        self.assertNotIn("host.classList", code)
        band = (JS / "bell_band.js").read_text()
        self.assertEqual(band.count('"bell-quiver"'), 1)
        css = CSS.read_text()
        self.assertNotIn("#bell-circle", css.split("*/", 1)[1])
