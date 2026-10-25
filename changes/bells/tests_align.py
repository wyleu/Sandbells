"""Tests for the Alignment page (bells/align.py, the farm_align view,
static/js/align.js and css/align.css)."""
import re
import shutil
import subprocess
from pathlib import Path
from unittest import mock, skipUnless

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from bells import align

HOME, TOWER = "ws://192.168.0.81/ws", "ws://10.42.0.81/ws"
FARM = [{"id": "sandbells", "name": "sandbells", "family": "sandbells", "kind": "host",
         "status_url": "", "ws_url": "", "poll_hint_sec": 5},
        {"id": "sandswing", "name": "sandswing", "family": "sandswing", "kind": "pico",
         "status_url": "http://192.168.0.81/status", "ws_url": HOME,
         "alt_ws_urls": [TOWER, HOME], "poll_hint_sec": 5}]
NO_CONCENTRATOR = FARM[:1]
HERE = Path(__file__).resolve().parent
CSS = HERE / "static" / "css" / "align.css"
NODE = shutil.which("node")


class AlignHelperTests(SimpleTestCase):
    def test_ws_urls_main_first_then_alts_without_repeats(self):
        self.assertEqual(align.ws_urls(FARM[1]), [HOME, TOWER])
        self.assertEqual(align.ws_urls({"ws_url": ""}), [])
        self.assertEqual(align.ws_urls({"ws_url": TOWER, "alt_ws_urls": None}), [TOWER])

    def test_pick_first_concentrator_or_the_named_one(self):
        self.assertEqual(align.pick(FARM), (1, FARM[1]))
        self.assertEqual(align.pick(FARM, 1), (1, FARM[1]))
        self.assertEqual(align.pick(FARM, 0), (None, None))      # a host, not a concentrator
        self.assertEqual(align.pick(FARM, 7), (None, None))
        self.assertEqual(align.pick(NO_CONCENTRATOR), (None, None))

    def test_active_kinds_match_the_pico(self):
        # sandswing src/align_scope.py ACTIVE_KINDS: a laser AND a sensor fitted
        self.assertEqual(align.ACTIVE_KINDS, ("head_new", "head_old"))
        for kind in ("empty", "trigger", "loopback", "fault", "unknown"):
            self.assertNotIn(kind, align.ACTIVE_KINDS)

    def test_page_config_carries_every_address(self):
        cfg = align.page_config(FARM[1])
        self.assertEqual(cfg["wsUrls"], [HOME, TOWER])
        self.assertEqual(cfg["id"], "sandswing")
        self.assertLess(cfg["keepAliveMs"], 10000)                # the Pico stops after 10 s


@mock.patch("bells.views.load_farm_instances", return_value=FARM)
class AlignPageTests(TestCase):
    def test_page_renders_for_the_concentrator(self, _):
        r = self.client.get(reverse("farm_align"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'id="align-main"')
        self.assertContains(r, 'id="align-cfg"')                  # json_script
        self.assertContains(r, HOME)
        self.assertContains(r, "Align.start(")
        self.assertContains(r, "sandswing")
        self.assertEqual(r.context["inst"]["id"], "sandswing")

    def test_both_addresses_reach_the_page(self, _):
        body = self.client.get(reverse("farm_align")).content.decode()
        self.assertIn("192.168.0.81", body)
        self.assertIn("10.42.0.81", body)

    def test_by_index_and_other_devices_are_404(self, _):
        self.assertEqual(self.client.get(reverse("farm_align_index", args=[1])).status_code, 200)
        self.assertEqual(self.client.get(reverse("farm_align_index", args=[0])).status_code, 404)
        self.assertEqual(self.client.get(reverse("farm_align_index", args=[9])).status_code, 404)

    def test_live_only_note_is_on_the_page(self, _):
        r = self.client.get(reverse("farm_align"))
        self.assertContains(r, 'id="align-note"')
        self.assertContains(r, "not saved")
        self.assertContains(r, "settings.json")
        self.assertContains(r, "reboot")

    def test_scripts_are_cache_busted_like_the_farm_page(self, _):
        body = self.client.get(reverse("farm_align")).content.decode()
        self.assertRegex(body, r'css/align\.css\?v=[0-9a-z]+"')
        self.assertRegex(body, r'js/align\.js\?v=[0-9a-z]+"')

    def test_not_a_live_page_and_no_template_comment_leaks(self, _):
        body = self.client.get(reverse("farm_align")).content.decode()
        self.assertNotIn("with-live", body)
        self.assertNotIn("{#", body)
        self.assertNotIn("live-events", body)

    def test_no_red_on_the_page(self, _):
        body = strip_comments(self.client.get(reverse("farm_align")).content.decode())
        self.assertNotRegex(body, r"(?i)\bred\b")
        self.assertEqual(red_colours(CSS.read_text()), [])
        self.assertEqual(red_colours((HERE / "static" / "js" / "align.js").read_text()), [])


@mock.patch("bells.views.load_farm_instances", return_value=NO_CONCENTRATOR)
class AlignNoConcentratorTests(TestCase):
    def test_page_says_there_is_nothing_to_align(self, _):
        r = self.client.get(reverse("farm_align"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "nothing to align")
        self.assertNotContains(r, "Align.start(")
        self.assertEqual(self.client.get(reverse("farm_align_index", args=[0])).status_code, 404)


def strip_comments(text):
    """Without css/js block comments and html comments (a shared menu style may
    say, in a comment, that the alarm colour is kept for something else)."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def red_colours(text):
    """Hex colours (#rgb / #rrggbb) and rgb() in text that read as red, plus
    the css word red."""
    bad = []
    for h in re.findall(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b", text):
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        if r >= 0xA0 and g <= 0x70 and b <= 0x70:
            bad.append("#" + h)
    for m in re.findall(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", text):
        r, g, b = map(int, m)
        if r >= 0xA0 and g <= 0x70 and b <= 0x70:
            bad.append("rgb%s" % (m,))
    bad += re.findall(r"(?i)(?<![\w-])red(?![\w-])", text)
    return bad


class RedDetectorTests(SimpleTestCase):
    def test_detector_sees_red_and_lets_the_warm_palette_through(self):
        self.assertTrue(red_colours("color: #f66;"))
        self.assertTrue(red_colours("color: #c00;"))
        self.assertTrue(red_colours("background: red"))
        self.assertTrue(red_colours("rgba(220, 40, 40, 0.5)"))
        for ok in ("#ffd978", "#6fdc7f", "#b48cff", "#251f16", "#fc3", "#1b3a22", "#40341a",
                   "rgba(150, 110, 220, 0.28)", "#a58a4a"):
            self.assertEqual(red_colours(ok), [], ok)


@skipUnless(NODE, "node not installed")
class AlignJsTests(SimpleTestCase):
    def test_node_unit_tests(self):
        p = subprocess.run([NODE, "--test", str(HERE / "js_tests")], capture_output=True,
                           text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
