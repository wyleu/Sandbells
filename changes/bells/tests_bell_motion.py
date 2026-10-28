"""The main bell page (home, kiosk_bells.js + #bell-circle) moves a few px diagonally when a
stroke or trigger event arrives (static/js/bell_motion.js + css/bell_motion.css).  The event
rule and the restart are tested in js_tests/bell_motion.test.js (run by AlignJsTests /
PowerJsTests with the rest of js_tests); here: the page loads both files cache-busted, the
script before kiosk_bells.js, and the CSS keeps to the cheap kind of animation."""
import re
from pathlib import Path

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

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
        self.assertEqual(src.count("BellMotion.create(el)"), 1)


class BellMotionCssTests(SimpleTestCase):
    def test_small_short_transform_only_and_reduced_motion_respected(self):
        css = CSS.read_text()
        self.assertEqual(re.findall(r"(\d+)ms ease-out", css), ["350", "350"])
        self.assertEqual(set(re.findall(r"translate\(([\dpx]+), ([\dpx]+)\)", css)), {("0", "0"), ("4px", "4px")})
        self.assertRegex(css, r"prefers-reduced-motion: reduce\)\s*\{[^}]*animation: none")
        for bad in ("filter", "blur", "box-shadow", "opacity", "width", "height", "left", "top",
                    "margin", "will-change", "infinite"):
            self.assertNotRegex(css.split("*/", 1)[1], r"\b%s\b" % bad, bad)
