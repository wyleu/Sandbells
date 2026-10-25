"""The Alignment button in the shared top line (events/templatetags/events_live.py
top_menu, events/templates/events/top_menu.html) and the page using that line."""
from unittest import mock

from django.test import TestCase
from django.urls import reverse

FARM = [{"id": "sandbells", "name": "sandbells", "family": "sandbells", "kind": "host",
         "status_url": "", "ws_url": "", "poll_hint_sec": 5},
        {"id": "sandswing", "name": "sandswing", "family": "sandswing", "kind": "pico",
         "status_url": "http://192.168.0.81/status", "ws_url": "ws://192.168.0.81/ws",
         "poll_hint_sec": 5}]


@mock.patch("bells.views.load_farm_instances", return_value=FARM)
class AlignmentMenuButtonTests(TestCase):
    def test_every_top_line_has_the_alignment_button(self, _):
        want = 'class="navbtn align" href="%s">Alignment</a>' % reverse("farm_align_index", args=[1])
        for url in (reverse("farm_status_index", args=[0]), reverse("farm_status_index", args=[1]),
                    reverse("events:days")):
            r = self.client.get(url)
            self.assertContains(r, want, msg_prefix=url)
            self.assertNotContains(r, "{#")
        self.assertNotContains(self.client.get(reverse("events:days")), "with-live")

    def test_button_is_in_the_same_style_and_does_not_steal_where_you_are(self, _):
        r = self.client.get(reverse("farm_status_index", args=[1]))
        self.assertContains(r, 'class="navbtn on"', count=1)          # still just the device
        self.assertContains(r, "a.navbtn {")                          # one shared button style

    def test_alignment_page_uses_the_top_line_and_marks_itself(self, _):
        r = self.client.get(reverse("farm_align"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'class="navbtn align on"', count=1)
        self.assertNotContains(r, 'class="navbtn on"')                # no device page is "current"
        self.assertContains(r, 'class="navbtn days"')
        for j in range(len(FARM)):
            self.assertContains(r, 'href="%s"' % reverse("farm_status_index", args=[j]))
        self.assertContains(r, 'id="mini-clock"')
        self.assertContains(r, 'id="align-note"')
        self.assertNotContains(r, "{#")
        self.assertNotContains(r, "with-live")

    def test_no_concentrator_no_button(self, _):
        with mock.patch("bells.views.load_farm_instances", return_value=FARM[:1]):
            r = self.client.get(reverse("farm_status_index", args=[0]))
            self.assertNotContains(r, "Alignment</a>")
