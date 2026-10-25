

from django.test import SimpleTestCase  # noqa: E402


class FarmAltAddressTests(SimpleTestCase):
    """A registry entry with alt_status_urls: any of its addresses is accepted,
    and the one that answers is used (home or tower, no rejigging)."""
    HOME, TOWER = "http://192.168.0.81/status", "http://10.42.0.81/status"

    def entry(self):
        return {"id": "sandswing", "family": "sandswing", "status_url": self.HOME,
                "alt_status_urls": [self.TOWER, self.HOME]}

    def test_device_urls_main_first_without_repeats(self):
        from bells import views
        self.assertEqual(views.device_urls(self.entry(), "status"), [self.HOME, self.TOWER])
        self.assertEqual(views.device_urls({"ws_url": ""}, "ws"), [])

    def test_either_address_is_accepted_and_falls_back(self):
        import io
        from unittest import mock
        from django.test import RequestFactory
        from bells import views

        calls = []

        def fake_open(url, timeout=0):
            calls.append(url)
            if url == self.HOME:
                raise OSError("home not here")
            return io.BytesIO(b'{"ok": true}')

        views._LAST_GOOD.clear()
        with mock.patch.object(views, "load_farm_instances", return_value=[self.entry()]), \
                mock.patch.object(views, "urlopen", side_effect=fake_open), \
                mock.patch.object(views, "wrap_document", side_effect=lambda d: d):
            r = views.farm_device_status(RequestFactory().get("/", {"url": self.HOME}))
            self.assertEqual(r.status_code, 200)
            self.assertEqual(calls, [self.HOME, self.TOWER])
            del calls[:]
            r = views.farm_device_status(RequestFactory().get("/", {"url": self.HOME}))
            self.assertEqual(calls, [self.TOWER])          # the one that worked goes first
            r = views.farm_device_status(RequestFactory().get("/", {"url": self.TOWER}))
            self.assertEqual(r.status_code, 200)
            r = views.farm_device_status(RequestFactory().get("/", {"url": "http://1.2.3.4/status"}))
            self.assertEqual(r.status_code, 400)
