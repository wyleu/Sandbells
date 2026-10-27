"""Machine photos: the mapping, the files, the {% machine_photo %} tag and the
farm page with and without a photo."""

import re
from unittest import mock

from django.contrib.staticfiles import finders
from django.template import Context, Template
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from bells import farm_photos, views

MAX_BYTES = 120 * 1024          # a photo on a Pi kiosk should stay small


class FarmPhotoFilesTests(SimpleTestCase):
    def test_every_mapped_file_exists_in_the_static_dir_and_is_a_small_jpeg(self):
        files = farm_photos.all_files()
        self.assertEqual(len(files), 2 * len(set(farm_photos.PHOTOS.values())))
        for rel in files:
            path = finders.find(rel)
            self.assertTrue(path, "missing static file %s" % rel)
            with open(path, "rb") as f:
                data = f.read()
            self.assertEqual(data[:3], b"\xff\xd8\xff", "%s is not a JPEG" % rel)
            self.assertLess(len(data), MAX_BYTES, "%s is %d bytes" % (rel, len(data)))

    def test_jpeg_sizes_are_square_600_and_160(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not installed")
        for stem in set(farm_photos.PHOTOS.values()):
            for suffix, side in (("", 600), ("-thumb", 160)):
                rel = "%s/%s%s.jpg" % (farm_photos.IMG_DIR, stem, suffix)
                with Image.open(finders.find(rel)) as im:
                    self.assertEqual(im.size, (side, side), rel)

    def test_aliases_point_at_real_entries(self):
        for alias, key in farm_photos.ALIASES.items():
            self.assertIn(key, farm_photos.PHOTOS, alias)

    def test_the_known_machines_are_all_mapped(self):
        for name in ("sandtest", "sandswing", "sandsense", "sandgps3", "sandmon",
                     "sandbells", "sandbells2"):
            self.assertIn(name, farm_photos.PHOTOS)


class FarmPhotoMappingTests(SimpleTestCase):
    def test_case_dot_local_and_spaces_are_ignored(self):
        self.assertEqual(farm_photos.photo_key(" SandSwing.LOCAL "), "sandswing")

    def test_alias(self):
        self.assertEqual(farm_photos.photo_key("sandsense-clock"), "sandsense")

    def test_first_key_with_a_photo_wins(self):
        self.assertEqual(farm_photos.photo_key("unknown-id", "sandmon"), "sandmon")
        self.assertEqual(farm_photos.photo_key("sandbells2", "sandbells"), "sandbells2")

    def test_unknown_and_odd_keys_give_none(self):
        for k in ("", "nosuch", None, 5, ["sandmon"]):
            self.assertIsNone(farm_photos.photo_key(k))
        self.assertIsNone(farm_photos.photo_for())
        self.assertIsNone(farm_photos.photo_for("nosuch"))

    def test_photo_for_gives_large_and_thumb_paths(self):
        self.assertEqual(farm_photos.photo_for("sandgps3"),
                         ("img/farm/sandgps3.jpg", "img/farm/sandgps3-thumb.jpg"))


def render(src, **ctx):
    return Template("{% load farm_ui %}" + src).render(Context(ctx))


class MachinePhotoTagTests(SimpleTestCase):
    def test_header_size_uses_the_large_picture_with_all_the_attributes(self):
        html = render('{% machine_photo inst %}', inst={"id": "sandswing", "name": "sandswing"},
                      git_hash="abc123")
        self.assertIn('src="/static/img/farm/sandswing.jpg?v=abc123"', html)
        self.assertIn('width="112" height="112"', html)
        self.assertIn('alt="sandswing"', html)
        self.assertIn('loading="lazy"', html)
        self.assertIn('class="mphoto"', html)

    def test_small_size_uses_the_thumbnail(self):
        html = render('{% machine_photo "sandmon" size=40 %}', git_hash="h")
        self.assertIn("/static/img/farm/sandmon-thumb.jpg?v=h", html)
        self.assertIn('width="40" height="40"', html)

    def test_registry_id_name_host_are_all_tried(self):
        html = render('{% machine_photo inst %}', inst={"id": "x1", "name": "kiosk", "host": "sandbells2.local"})
        self.assertIn("sandbells2.jpg", html)
        self.assertIn('alt="kiosk"', html)

    def test_alt_text_is_escaped(self):
        html = render('{% machine_photo inst %}', inst={"id": "sandmon", "name": 'a"><b>'})
        self.assertNotIn("<b>", html)

    def test_no_photo_draws_nothing_and_never_an_img(self):
        self.assertEqual(render('{% machine_photo inst %}', inst={"id": "nosuch"}).strip(), "")
        self.assertEqual(render('{% machine_photo "nosuch" size=30 %}').strip(), "")
        self.assertEqual(render('{% machine_photo missing %}').strip(), "")

    def test_placeholder_is_a_neutral_square_with_the_initial(self):
        html = render('{% machine_photo inst placeholder=True %}', inst={"id": "nosuch", "name": "mystery"})
        self.assertIn("mphoto-none", html)
        self.assertIn(">M<", html)
        self.assertNotIn("<img", html)

    def test_bad_size_falls_back(self):
        self.assertIn('width="112"', render('{% machine_photo "sandmon" size="big" %}'))

    def test_no_git_hash_in_context_still_versions_the_url(self):
        self.assertIn("?v=dev", render('{% machine_photo "sandmon" %}'))


MIXED = [
    {"id": "sandswing", "name": "sandswing", "family": "sandswing", "kind": "pico",
     "status_url": "http://192.168.0.81/status", "ws_url": "", "poll_hint_sec": 5},
    {"id": "mystery", "name": "mystery", "family": "other", "kind": "host",
     "status_url": "", "ws_url": "", "poll_hint_sec": 5},
]


@mock.patch("bells.views.load_farm_instances", return_value=MIXED)
class FarmPagePhotoTests(TestCase):
    def test_page_with_a_photo(self, _):
        r = self.client.get(reverse("farm_status_index", args=[0]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "/static/img/farm/sandswing.jpg?v=")
        self.assertContains(r, 'alt="sandswing"')
        self.assertContains(r, 'id="farm-ident"')           # ids the page script fills in
        self.assertContains(r, 'id="farm-level"')
        self.assertContains(r, 'id="farm-summary"')
        self.assertContains(r, "FarmStatus.start(")
        self.assertNotContains(r, "class=\"mphoto mphoto-none\"")
        self.assertContains(r, "192.168.0.81")              # host line, from the status url

    def test_page_without_a_photo_has_no_img_and_still_renders(self, _):
        r = self.client.get(reverse("farm_status_index", args=[1]))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "<img")
        self.assertContains(r, "class=\"mphoto mphoto-none\"")
        self.assertContains(r, 'id="farm-ident"')
        self.assertContains(r, "FarmStatus.start(")

    def test_every_page_in_the_farm_renders(self, _):
        for i in range(len(MIXED)):
            self.assertEqual(self.client.get(reverse("farm_status_index", args=[i])).status_code, 200)

    def test_photo_css_is_on_the_farm_page_and_the_events_pages(self, _):
        self.assertContains(self.client.get(reverse("farm_status_index", args=[0])), ".mphoto {")
        self.assertContains(self.client.get(reverse("events:days")), ".mphoto {")

    def test_css_and_js_urls_still_carry_the_version(self, _):
        r = self.client.get(reverse("farm_status_index", args=[0])).content.decode()
        self.assertTrue(re.search(r'farm_status\.css\?v=\S+"', r))
        self.assertTrue(re.search(r'farm_status\.js\?v=\S+"', r))


class HostLabelTests(SimpleTestCase):
    def test_labels(self):
        f = views.farm_host_label
        self.assertEqual(f({"host": "sandsense.local"}), "sandsense.local")
        self.assertEqual(f({"status_url": "http://sandmon.local/status.json"}), "sandmon.local")
        self.assertEqual(f({"kind": "host", "status_url": "http://127.0.0.1/api/system-status/"},
                           "sandbells2"), "sandbells2.local")
        self.assertEqual(f({"kind": "pico", "status_url": ""}, "sandbells2"), "")
        self.assertEqual(f({"status_url": "http://[bad"}), "")
