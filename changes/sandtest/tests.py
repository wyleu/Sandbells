"""Sandtest page and proxy: a fake Pico (a tiny local HTTP server) stands in for
the rig, so the proxy is tested for real over a socket, the error paths
included.  The rig itself is not needed and is never contacted."""

import json
import logging
import os
import re
import shutil
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock, skipUnless

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from . import config, proxy, views

def setUpModule():
    # the 502/504 replies these tests provoke are logged as errors by Django
    logging.getLogger("django.request").setLevel(logging.CRITICAL)


def tearDownModule():
    logging.getLogger("django.request").setLevel(logging.NOTSET)


STATUS = {"ok": True, "now_ms": 123456, "version": "0.9.1", "device": "pico2w", "mem_free_kb": 212,
          "loop_max_ms": 7,
          "player": {"state": "idle", "presses_sent": 3, "pressed": [], "max_late_ms": 2},
          "sweep": {"mode": "idle", "angle_deg": 12.5, "beam_deg": 25.0, "face": "mirror",
                    "faces": {"mirror": 0, "reflector": 180}, "in_window": [3], "hit": True,
                    "window_face": "mirror", "limits_deg": [-60, 60],
                    "heads": {"1": {"angle_deg": -20, "width_deg": 4},
                              "3": {"angle_deg": 12, "width_deg": 4}}}}


class FakePico:
    """GET /status and POST /cmd on 127.0.0.1:<port>; records every request."""

    def __init__(self, token=None):
        self.requests = []           # (method, path, headers dict, body bytes)
        self.token = token
        self.status_body = json.dumps(STATUS).encode()
        self.cmd_status = 200
        self.cmd_body = None         # None: {"ok": true, "cmd": <cmd>}
        self.raw_reply = None        # (status, bytes) to send instead of JSON
        self.delay = 0.0
        self.truncate_cmds = 0       # refuse this many POST /cmd as the rig does when the body is late
        pico = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _reply(self, status, body):
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _go(self, body):
                pico.requests.append((self.command, self.path, dict(self.headers), body))
                if pico.delay:
                    time.sleep(pico.delay)
                if pico.token is not None and self.headers.get("X-Sandtest-Token") != pico.token:
                    return self._reply(401, b'{"ok":false,"error":"bad token"}')
                if pico.raw_reply:
                    return self._reply(*pico.raw_reply)
                if self.command == "GET" and self.path == "/status":
                    return self._reply(200, pico.status_body)
                if self.command == "POST" and self.path == "/cmd":
                    if pico.truncate_cmds > 0:
                        pico.truncate_cmds -= 1
                        return self._reply(400, b'{"ok":false,"error":"bad JSON: syntax error in JSON"}')
                    if pico.cmd_body is not None:
                        return self._reply(pico.cmd_status, pico.cmd_body)
                    return self._reply(200, json.dumps({"ok": True, "cmd": json.loads(body)["cmd"]}).encode())
                self._reply(404, b'{"ok":false,"error":"not found"}')

            def do_GET(self):
                self._go(b"")

            def do_POST(self):
                self._go(self.rfile.read(int(self.headers.get("Content-Length") or 0)))

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        self.thread.start()

    @property
    def host(self):
        return "127.0.0.1:%d" % self.port

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


NO_FILE = mock.patch("sandtest.config._file_section", return_value={})


class ProxyBase(SimpleTestCase):
    def setUp(self):
        proxy.forget_address()
        self.pico = FakePico()
        self.addCleanup(self.pico.close)
        self.env = mock.patch.dict(os.environ, {"SANDTEST_HOST": self.pico.host}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        os.environ.pop("SANDTEST_TOKEN", None)
        f = NO_FILE.start()
        self.addCleanup(NO_FILE.stop)

    def post(self, body):
        data = body if isinstance(body, (bytes, str)) else json.dumps(body)
        return self.client.post(reverse("sandtest:cmd"), data=data, content_type="application/json")


class ConfigTests(SimpleTestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("SANDTEST_HOST", None)
        os.environ.pop("SANDTEST_TOKEN", None)

    def test_default_host_is_sandtest_local(self):
        with NO_FILE:
            c = config.load()
        self.assertEqual((c.host, c.source, c.token, c.error), ("sandtest.local", "default", "", ""))
        self.assertEqual((c.hostname, c.port), ("sandtest.local", 80))

    def test_settings_json_then_env_wins(self):
        with mock.patch("sandtest.config._file_section", return_value={"host": "192.168.0.198", "token": "t1"}):
            c = config.load()
            self.assertEqual((c.host, c.source, c.token), ("192.168.0.198", "settings.json", "t1"))
            os.environ["SANDTEST_HOST"] = "rig.example:8080"
            os.environ["SANDTEST_TOKEN"] = "t2"
            c = config.load()
        self.assertEqual((c.host, c.source, c.token, c.hostname, c.port),
                         ("rig.example:8080", "env", "t2", "rig.example", 8080))
        self.assertTrue(c.token_set)

    def test_host_cleaning(self):
        self.assertEqual(config.clean_host(" http://192.168.0.198/ "), ("192.168.0.198", ""))
        self.assertEqual(config.clean_host("sandtest.local:81"), ("sandtest.local:81", ""))
        for bad in ("", "a b", "x/y", "http://h/path", "h:0", "h:99999", "-h", "h;rm", "[::1]"):
            host, err = config.clean_host(bad)
            self.assertEqual(host, "", bad)
            self.assertTrue(err, bad)

    def test_unreadable_settings_file_is_not_fatal(self):
        with mock.patch("bells.app_settings._load", side_effect=ValueError("bad json")):
            self.assertEqual(config.load().host, "sandtest.local")


class StatusProxyTests(ProxyBase):
    def test_status_is_passed_through_with_host(self):
        r = self.client.get(reverse("sandtest:status"))
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertTrue(j["ok"] and j["reachable"])
        self.assertEqual(j["host"], self.pico.host)
        self.assertEqual(j["rig"], STATUS)
        (method, path, headers, _), = self.pico.requests
        self.assertEqual((method, path), ("GET", "/status"))
        self.assertEqual(headers["Host"], self.pico.host)
        self.assertNotIn("X-Sandtest-Token", headers)

    def test_not_cached(self):
        r = self.client.get(reverse("sandtest:status"))
        self.assertIn("no-store", r["Cache-Control"])

    def test_token_header_sent_and_never_shown(self):
        self.pico.token = "s3cret"
        os.environ["SANDTEST_TOKEN"] = "s3cret"
        r = self.client.get(reverse("sandtest:status"))
        self.assertTrue(r.json()["ok"])
        self.assertEqual(self.pico.requests[-1][2]["X-Sandtest-Token"], "s3cret")
        self.assertNotContains(r, "s3cret")
        page = self.client.get(reverse("sandtest:page"))
        self.assertNotContains(page, "s3cret")
        self.assertContains(page, "token set")

    def test_missing_token_is_a_clear_error(self):
        self.pico.token = "s3cret"
        r = self.client.get(reverse("sandtest:status"))
        j = r.json()
        self.assertEqual(r.status_code, 502)
        self.assertFalse(j["ok"])
        self.assertTrue(j["reachable"])
        self.assertIn("SANDTEST_TOKEN", j["error"])

    def test_only_get(self):
        self.assertEqual(self.client.post(reverse("sandtest:status")).status_code, 405)
        self.assertEqual(self.pico.requests, [])

    def test_the_page_itself_never_calls_the_rig(self):
        self.assertEqual(self.client.get(reverse("sandtest:page")).status_code, 200)
        self.assertEqual(self.pico.requests, [])


class CmdProxyTests(ProxyBase):
    def test_command_is_forwarded_as_json(self):
        cmd = {"cmd": "play", "pattern": "13425678", "interval_ms": 400, "press_ms": 120, "repeat": 3}
        r = self.post(cmd)
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertTrue(j["ok"] and j["reachable"])
        self.assertEqual(j["rig"], {"ok": True, "cmd": "play"})
        method, path, headers, body = self.pico.requests[-1]
        self.assertEqual((method, path), ("POST", "/cmd"))
        self.assertEqual(json.loads(body), cmd)
        self.assertEqual(headers["Content-Type"], "application/json")

    def test_a_cut_short_body_is_sent_again_once(self):
        self.pico.truncate_cmds = 1
        r = self.post({"cmd": "press", "channel": 1, "press_ms": 120})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])
        self.assertEqual(len(self.pico.requests), 2)

    def test_a_body_cut_short_twice_is_reported(self):
        self.pico.truncate_cmds = 2
        r = self.post({"cmd": "press", "channel": 1})
        self.assertEqual(r.status_code, 400)
        self.assertIn("bad JSON", r.json()["error"])
        self.assertEqual(len(self.pico.requests), 2)

    def test_a_real_refusal_is_not_sent_again(self):
        self.pico.cmd_status = 400
        self.pico.cmd_body = b'{"ok":false,"error":"bell 9 has no opto pin"}'
        self.post({"cmd": "press", "channel": 9})
        self.assertEqual(len(self.pico.requests), 1)

    def test_every_page_command_is_accepted(self):
        for cmd in ({"cmd": "stop"}, {"cmd": "press", "channel": 1}, {"cmd": "stress", "seed": 1},
                    {"cmd": "sweep", "mode": "menace", "allow_hits": True}, {"cmd": "face", "face": "reflector"},
                    {"cmd": "park"}):
            self.assertEqual(self.post(cmd).status_code, 200, cmd)

    def test_rig_refusal_is_passed_on_as_400(self):
        self.pico.cmd_status = 400
        self.pico.cmd_body = b'{"ok":false,"error":"bell 9 has no opto pin"}'
        r = self.post({"cmd": "press", "channel": 9})
        j = r.json()
        self.assertEqual(r.status_code, 400)
        self.assertFalse(j["ok"])
        self.assertTrue(j["reachable"])
        self.assertEqual(j["error"], "bell 9 has no opto pin")

    def test_bad_requests_never_reach_the_rig(self):
        cases = [("not json", 400), ("[1,2]", 400), ('{"cmd": "format_flash"}', 400), ("{}", 400),
                 (b"\xff\xfe", 400), (json.dumps({"cmd": "stop", "pad": "x" * 3000}), 413)]
        for body, code in cases:
            r = self.post(body)
            self.assertEqual(r.status_code, code, body)
            self.assertFalse(r.json()["ok"])
            self.assertTrue(r.json()["error"])
        self.assertEqual(self.pico.requests, [])

    def test_only_post(self):
        self.assertEqual(self.client.get(reverse("sandtest:cmd")).status_code, 405)


class UnreachableTests(ProxyBase):
    def check_down(self, r, code, word):
        j = r.json()
        self.assertEqual(r.status_code, code)
        self.assertFalse(j["ok"])
        self.assertFalse(j["reachable"])
        self.assertIn(word, j["error"])
        self.assertTrue(j["host"])

    def test_connection_refused(self):
        os.environ["SANDTEST_HOST"] = "127.0.0.1:%d" % free_port()
        t0 = time.monotonic()
        self.check_down(self.client.get(reverse("sandtest:status")), 502, "refused")
        self.assertLess(time.monotonic() - t0, proxy.TIMEOUT_S)
        self.check_down(self.post({"cmd": "stop"}), 502, "refused")

    def test_unknown_name(self):
        os.environ["SANDTEST_HOST"] = "no-such-rig.invalid"
        with mock.patch.object(proxy, "_resolve", side_effect=socket.gaierror(-2, "Name or service not known")):
            self.check_down(self.client.get(reverse("sandtest:status")), 502, "name not found")

    def test_slow_rig_times_out_within_the_limit(self):
        self.pico.delay = 2.0
        with mock.patch.object(proxy, "TIMEOUT_S", 0.4):
            t0 = time.monotonic()
            r = self.client.get(reverse("sandtest:status"))
            took = time.monotonic() - t0
        self.check_down(r, 504, "no answer")
        self.assertLess(took, 1.0)

    def test_slow_name_lookup_cannot_block_past_the_limit(self):
        with mock.patch.object(proxy, "TIMEOUT_S", 0.3), \
                mock.patch.object(proxy, "_resolve", side_effect=lambda h: time.sleep(2) or "127.0.0.1"):
            t0 = time.monotonic()
            r = self.client.get(reverse("sandtest:status"))
            took = time.monotonic() - t0
        self.check_down(r, 504, "no answer")
        self.assertLess(took, 1.0)

    def test_busy_rig_is_not_piled_on(self):
        with mock.patch.object(proxy, "MAX_INFLIGHT", 0):
            self.check_down(self.client.get(reverse("sandtest:status")), 503, "not answering")
        self.assertEqual(self.pico.requests, [])
        self.assertEqual(proxy.inflight(), 0)

    def test_inflight_count_returns_to_zero(self):
        self.client.get(reverse("sandtest:status"))
        self.client.get(reverse("sandtest:status"))
        self.assertEqual(proxy.inflight(), 0)

    def test_rubbish_reply(self):
        self.pico.raw_reply = (200, b"<html>hello</html>")
        self.check_down(self.client.get(reverse("sandtest:status")), 502, "not with JSON")

    def test_huge_reply_is_cut_off(self):
        self.pico.raw_reply = (200, b'{"x":"' + b"a" * (proxy.MAX_REPLY_BYTES + 10) + b'"}')
        self.check_down(self.client.get(reverse("sandtest:status")), 502, "too long")

    def test_bad_host_setting(self):
        os.environ["SANDTEST_HOST"] = "not a host!"
        self.check_down(self.client.get(reverse("sandtest:status")), 503, "not a host name")
        self.check_down(self.post({"cmd": "stop"}), 503, "not a host name")
        r = self.client.get(reverse("sandtest:page"))
        self.assertContains(r, 'id="st-config-error"')

    def test_comes_back_after_an_outage(self):
        os.environ["SANDTEST_HOST"] = "127.0.0.1:%d" % free_port()
        self.assertEqual(self.client.get(reverse("sandtest:status")).status_code, 502)
        os.environ["SANDTEST_HOST"] = self.pico.host
        self.assertEqual(self.client.get(reverse("sandtest:status")).status_code, 200)


class PageTests(TestCase):
    def setUp(self):
        proxy.forget_address()
        env = mock.patch.dict(os.environ, {"SANDTEST_HOST": "192.168.0.198"}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("SANDTEST_TOKEN", None)
        NO_FILE.start()
        self.addCleanup(NO_FILE.stop)

    def test_page_renders_with_host_and_urls(self):
        r = self.client.get(reverse("sandtest:page"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(reverse("sandtest:page"), "/sandtest/")
        self.assertEqual(reverse("sandtest:status"), "/sandtest/status")
        self.assertEqual(reverse("sandtest:cmd"), "/sandtest/cmd")
        self.assertContains(r, '<strong id="st-host-name">192.168.0.198</strong>', html=False)
        self.assertContains(r, 'data-status-url="/sandtest/status"')
        self.assertContains(r, 'data-cmd-url="/sandtest/cmd"')
        self.assertContains(r, 'data-poll-ms="1000"')
        self.assertNotContains(r, "token set")
        self.assertIn("csrftoken", r.cookies)

    def test_every_control_is_there(self):
        body = self.client.get(reverse("sandtest:page")).content.decode()
        for kind in ("press", "play", "stress", "sweep", "scan", "visit", "menace", "profile"):
            self.assertIn('data-cmd="%s"' % kind, body)
        for el in ('id="st-stop"', 'id="st-park"', 'data-face="mirror"', 'data-face="reflector"',
                   'name="allow_hits"', "RISKY", 'id="st-heads"', 'id="st-conn"', 'id="st-mem"',
                   'id="st-loop"', 'id="st-presses"', 'id="st-beam"', 'id="st-window"'):
            self.assertIn(el, body)
        self.assertEqual(body.count('name="channel"'), 1)
        for name in ("press_ms", "interval_ms", "repeat", "seed", "seconds", "from_deg", "to_deg", "speed_dps",
                     "dwell_ms", "cycles", "head", "span_deg", "step_deg", "passes", "pattern"):
            self.assertIn('name="%s"' % name, body)

    def test_static_files_are_cache_busted_with_the_git_hash(self):
        r = self.client.get(reverse("sandtest:page"))
        body = r.content.decode()
        self.assertTrue(re.search(r'/static/css/sandtest\.css\?v=[0-9a-z]+"', body), body)
        self.assertTrue(re.search(r'/static/js/sandtest\.js\?v=[0-9a-z]+"', body), body)
        self.assertNotIn("?v=\"", body)

    def test_stop_and_status_are_not_hidden_in_the_page(self):
        body = self.client.get(reverse("sandtest:page")).content.decode()
        self.assertLess(body.index('id="st-stop"'), body.index('id="sandtest-root"'))

    def test_menu_entry_on_the_page_and_on_other_pages(self):
        r = self.client.get(reverse("sandtest:page"))
        self.assertContains(r, '<a class="navbtn sandtest on" href="/sandtest/">Sandtest</a>', html=True)
        for url in (reverse("events:days"),):
            r = self.client.get(url)
            self.assertContains(r, '<a class="navbtn sandtest" href="/sandtest/">Sandtest</a>', html=True)

    def test_menu_entry_on_a_farm_page(self):
        farm = [{"id": "s", "name": "sandbells", "kind": "host", "family": "sandbells", "role": "",
                 "status_url": "http://127.0.0.1/api/system-status/", "ws_url": "", "poll_hint_sec": 5}]
        with mock.patch("bells.views.load_farm_instances", return_value=farm):
            r = self.client.get(reverse("farm_status_index", args=[0]))
        self.assertContains(r, 'href="/sandtest/">Sandtest</a>')

    def test_no_red_in_the_css(self):
        """Red is kept for 'not coming': the page uses none, STOP included."""
        css = (Path(__file__).parent / "static" / "css" / "sandtest.css").read_text()
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)             # comments may say "red"
        self.assertNotRegex(css, r"(?i)\bred\b")
        for h in re.findall(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b", css):
            if len(h) == 3:
                h = "".join(c * 2 for c in h)
            r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
            self.assertFalse(r > 150 and g < 0.5 * r and b < 0.5 * r, "reddish colour #" + h)


NODE = shutil.which("node")
JS_TESTS = Path(__file__).resolve().parent / "js_tests"


@skipUnless(NODE, "node not installed")
class SandtestJsTests(SimpleTestCase):
    def test_node_unit_tests(self):
        p = subprocess.run([NODE, "--test", str(JS_TESTS)], capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
