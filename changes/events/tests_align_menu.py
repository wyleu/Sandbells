"""The sandheads button in the shared top line (events/templatetags/events_live.py
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
class SandheadsMenuButtonTests(TestCase):
    def test_every_top_line_has_the_sandheads_button(self, _):
        want = 'class="navbtn heads" href="%s">sandheads</a>' % reverse("farm_heads_index", args=[1])
        for url in (reverse("farm_status_index", args=[0]), reverse("farm_status_index", args=[1]),
                    reverse("events:days")):
            r = self.client.get(url)
            self.assertContains(r, want, msg_prefix=url)
            self.assertNotContains(r, "{#")
        self.assertNotContains(self.client.get(reverse("events:days")), "with-live")

    def test_button_sits_with_the_device_buttons_before_rings_by_day(self, _):
        body = self.client.get(reverse("farm_status_index", args=[0])).content.decode()
        self.assertLess(body.index(">sandswing</a>"), body.index(">sandheads</a>"))
        self.assertLess(body.index(">sandheads</a>"), body.index(">Rings by day</a>"))
        self.assertNotIn(">Alignment</a>", body)

    def test_button_is_in_the_same_style_and_does_not_steal_where_you_are(self, _):
        r = self.client.get(reverse("farm_status_index", args=[1]))
        self.assertContains(r, 'class="navbtn on"', count=1)          # still just the device
        self.assertContains(r, "a.navbtn {")                          # one shared button style

    def test_sandheads_page_uses_the_top_line_and_marks_itself_gold(self, _):
        r = self.client.get(reverse("farm_heads"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'class="navbtn heads on"', count=1)
        self.assertContains(r, "a.navbtn.on {")                       # the gold "you are here" rule
        self.assertNotContains(r, 'class="navbtn on"')                # no device page is "current"
        self.assertContains(r, 'class="navbtn days"')
        for j in range(len(FARM)):
            self.assertContains(r, 'href="%s"' % reverse("farm_status_index", args=[j]))
        self.assertContains(r, 'id="mini-clock"')
        self.assertContains(r, 'id="align-note"')
        self.assertNotContains(r, "{#")
        self.assertNotContains(r, "with-live")

    def test_old_alignment_address_still_gets_you_there(self, _):
        r = self.client.get("/farm/align/", follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'class="navbtn heads on"', count=1)

    def test_no_concentrator_no_button(self, _):
        with mock.patch("bells.views.load_farm_instances", return_value=FARM[:1]):
            r = self.client.get(reverse("farm_status_index", args=[0]))
            self.assertNotContains(r, "sandheads</a>")
