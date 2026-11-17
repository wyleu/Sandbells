"""The chatter test: headscc decoding of the Pico's counts and the PWM
speed, the command check, the log (rows, CSV), its views and settings.

python manage.py test events.tests_chatter
"""
import json
import os
import shutil
import tempfile
from datetime import timedelta

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from . import chatterlog, serialheads
from . import constants as C
from .tests_heads import decode

# bytes from sandswing heads_cc.CcOut (sw-chatter):
# chatter(1, off, (40 transitions, 38 clean, max 5 edges, mean 1.1, 7 ms, 2 spurious))
REPORT = bytes.fromhex("bf6601bf7500bf1a00bf3a28bf1b00bf3b26bf1c00bf3c05bf1d00bf3d0b"
                       "bf1e00bf3e07bf1f00bf3f02bf6a01")
# chatter(2, on, (0, 0, 0, None, 0, 0)): just started, no mean yet
STARTED = bytes.fromhex("bf6602bf7501bf1a00bf3a00bf1b00bf3b00bf1c00bf3c00bf1d7fbf3d7f"
                        "bf1e00bf3e00bf1f00bf3f00bf6a01")
# ack(1, "pwm", ok, thr 20000, drv 34078, pwm_hz 20000)
ACK_PWM = bytes.fromhex("bf6601bf6700bf680cbf6900bf1427bf3407bf1642bf3647bf0e0fbf2e50bf6a01")
# ack(1, "pwm", "pwm out of range", ..., pwm_hz 990)
ACK_PWM_BAD = bytes.fromhex("bf6601bf6700bf680cbf6915bf1427bf3407bf1642bf3647bf0e00bf2e63bf6a01")

RUN = {"ch": 1, "label": "H5", "drv": 34078, "pwm_hz": 1000, "passes": 10, "trans": 40,
       "clean": 38, "max_edges": 5, "mean_x10": 11, "max_burst_ms": 7, "spurious": 2, "end": None}


class Decode(SimpleTestCase):
    def test_report(self):
        _, docs = decode(REPORT, STARTED)
        self.assertEqual([d["type"] for d in docs], ["align_chatter", "align_chatter"])
        b = docs[0]["body"]
        self.assertEqual({k: b[k] for k in ("ch", "on", "trans", "clean", "max_edges", "mean_x10",
                                            "max_burst_ms", "spurious")},
                         {"ch": 1, "on": False, "trans": 40, "clean": 38, "max_edges": 5,
                          "mean_x10": 11, "max_burst_ms": 7, "spurious": 2})
        s = docs[1]["body"]
        self.assertEqual((s["ch"], s["on"], s["trans"], s["mean_x10"]), (2, True, 0, None))

    def test_pwm_acks(self):
        _, docs = decode(ACK_PWM, ACK_PWM_BAD)
        ok, bad = docs[0]["body"], docs[1]["body"]
        self.assertEqual((ok["what"], ok["ok"], ok["pwm_hz"]), ("pwm", True, 20000))
        self.assertEqual((bad["what"], bad["ok"], bad["why"], bad["pwm_hz"]),
                         ("pwm", False, "PWM speed out of range", 990))

    def test_older_acks_have_no_pwm(self):
        from .tests_lineup import ACK_END
        _, docs = decode(ACK_END)
        self.assertIsNone(docs[0]["body"].get("pwm_hz"))

    def test_codes_match_sandswing(self):
        self.assertEqual((C.HEADS_WHAT[12], C.HEADS_WHAT[13]), ("pwm", "chatter"))
        self.assertEqual(C.HEADS_WHY[21], "PWM speed out of range")
        self.assertEqual(C.HEADS_WHY[23], "no chatter test running")
        self.assertEqual((C.HEADS_CC_CHATTER, C.HEADS_CC_PWM), (117, 14))
        self.assertEqual([cc for _, cc in C.HEADS_CC_CHATTER_14], [26, 27, 28, 29, 30, 31])
        self.assertIn("align_chatter", C.SERIAL_HEADS_TYPES)


class Commands(SimpleTestCase):
    def line(self, doc):
        return json.loads(serialheads.check_command(doc))

    def test_pwm_and_chatter(self):
        self.assertEqual(self.line({"cmd": "align", "ch": 1, "pwm_hz": 20000}),
                         {"cmd": "align", "ch": 1, "pwm_hz": 20000})
        self.assertEqual(self.line({"cmd": "align", "ch": 1, "chatter": "start", "gap_ms": 30}),
                         {"cmd": "align", "ch": 1, "chatter": "start", "gap_ms": 30})
        for op in C.HEADS_CHATTER_OPS:
            self.assertEqual(self.line({"cmd": "align", "ch": 1, "chatter": op})["chatter"], op)
        for bad in ({"cmd": "align", "ch": 1, "pwm_hz": C.HEADS_PWM_HZ_MIN - 1},
                    {"cmd": "align", "ch": 1, "pwm_hz": C.HEADS_PWM_HZ_MAX + 1},
                    {"cmd": "align", "ch": 1, "pwm_hz": "1000"},
                    {"cmd": "align", "ch": 1, "pwm_hz": True},
                    {"cmd": "align", "ch": 1, "chatter": "go"},
                    {"cmd": "align", "ch": 1, "chatter": "stop", "gap_ms": 20},
                    {"cmd": "align", "ch": 1, "gap_ms": 20},
                    {"cmd": "align", "ch": 1, "chatter": "start", "gap_ms": C.HEADS_CHATTER_GAP_MAX_MS + 1},
                    {"cmd": "align", "ch": 1, "chatter": "start", "gap_ms": 0}):
            with self.assertRaises(ValueError, msg=bad):
                serialheads.check_command(bad)


class Log(TestCase):
    def test_check(self):
        out = chatterlog.check(RUN)
        self.assertEqual(out["expected"], 10 * C.HEADS_CHATTER_TRANS_PER_PASS)
        self.assertEqual(out["end"], "")
        self.assertIsNone(chatterlog.check(dict(RUN, passes=None))["expected"])     # by hand
        for bad in (dict(RUN, ch=0), dict(RUN, drv=-1), dict(RUN, drv=True), dict(RUN, trans=-1),
                    dict(RUN, trans=C.HEADS_CHATTER_COUNT_MAX + 1), dict(RUN, passes=0),
                    dict(RUN, pwm_hz="x"), dict(RUN, label='a"b'), [], None):
            with self.assertRaises(ValueError, msg=bad):
                chatterlog.check(bad)
        long = chatterlog.check(dict(RUN, end="x" * 100))["end"]
        self.assertEqual(len(long), C.HEADS_CHATTER_END_MAX_LEN)

    def test_view_rows_and_csv(self):
        url = reverse("farm_heads_chatter_log")
        r = self.client.post(url, json.dumps(RUN), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        row = r.json()["row"]
        self.assertEqual((row["clean_pct"], row["drive_pct"], row["expected"]), (95.0, 52.0, 40))
        r = self.client.post(url, json.dumps(dict(RUN, drv=70000)), content_type="application/json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post(url, "x" * (C.HEADS_CHATTER_LOG_MAX_B + 1), content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.client.post(url, json.dumps(dict(RUN, pwm_hz=20000, clean=40, spurious=0)),
                         content_type="application/json")
        rows = self.client.get(url).json()["rows"]
        self.assertEqual([x["pwm_hz"] for x in rows], [20000, 1000])              # newest first
        self.assertEqual(self.client.delete(url).status_code, 405)
        r = self.client.get(reverse("farm_heads_chatter_csv") + "?days=1")
        self.assertIn("attachment", r["Content-Disposition"])
        lines = r.content.decode().strip().splitlines()
        self.assertEqual(lines[0].split(","), list(chatterlog.CSV_FIELDS))
        self.assertEqual(len(lines), 3)
        first = dict(zip(chatterlog.CSV_FIELDS, lines[1].split(",")))
        self.assertEqual((first["drive_pct"], first["pwm_hz"], first["transitions"], first["clean_pct"],
                          first["mean_edges"], first["max_burst_ms"], first["spurious"]),
                         ("52.0", "1000", "40", "95.0", "1.1", "7", "2"))
        from .models import HeadChatter
        HeadChatter.objects.update(at=timezone.now() - timedelta(days=3))
        lines = self.client.get(reverse("farm_heads_chatter_csv") + "?days=1").content.decode().strip()
        self.assertEqual(len(lines.splitlines()), 1)                                # header only
        self.assertEqual(self.client.get(reverse("farm_heads_chatter_csv") + "?days=x").status_code, 400)


class Settings(SimpleTestCase):
    def test_chatter_settings(self):
        from bells import align
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        p = os.path.join(tmp, "settings.json")
        s = align.chatter_settings(p)                                              # no file
        for k, v in C.HEADS_CHATTER_DEFAULTS.items():
            self.assertEqual(s[k], v if not isinstance(v, (list, tuple)) else list(v))
        self.assertEqual((s["pwmMin"], s["pwmMax"], s["pwmNow"]),
                         (C.HEADS_PWM_HZ_MIN, C.HEADS_PWM_HZ_MAX, C.HEADS_PWM_HZ_NOW))
        with open(p, "w") as f:
            json.dump({"sandheads": {"chatter": {"passes": 20, "fast_pwm_hz": 50000,
                                                 "drives_pct": [100, 30], "speed_dps": "fast",
                                                 "face": "mirror"}}}, f)
        s = align.chatter_settings(p)
        self.assertEqual((s["passes"], s["fast_pwm_hz"], s["drives_pct"], s["face"]),
                         (20, 50000, [100, 30], "mirror"))
        self.assertEqual(s["speed_dps"], C.HEADS_CHATTER_DEFAULTS["speed_dps"])
        with open(p, "w") as f:
            json.dump({"sandheads": {"chatter": {"passes": 0, "fast_pwm_hz": 10 ** 6,
                                                 "drives_pct": [0, 101]}}}, f)
        s = align.chatter_settings(p)
        self.assertEqual((s["passes"], s["fast_pwm_hz"]),
                         (C.HEADS_CHATTER_DEFAULTS["passes"], C.HEADS_CHATTER_DEFAULTS["fast_pwm_hz"]))
        cfg = align.page_config({"id": "c"}, chatter=s)
        self.assertEqual(cfg["chatter"]["passes"], s["passes"])

    def test_page_has_the_panel(self):
        src = open(os.path.join(os.path.dirname(__file__), "..", "bells", "templates", "bells",
                                "align.html")).read()
        self.assertLess(src.index("js/chatter.js"), src.index("js/align.js"))
        self.assertIn("chatterCsvUrl", src)
