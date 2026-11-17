"""Head line-up (sandswing sweep.py / head_store.py) on the Sandbells side:
the sweep point and saved-values CC reports (headscc), the page's new
commands (serialheads.check_command), the sweep log (sweeplog, HeadSweep,
/farm/heads/sweep-log/) and the suggestion settings (bells.align)."""

import json
import os
import shutil
import tempfile
from datetime import timedelta

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from . import constants as C
from . import serialheads, sweeplog
from .tests_heads import decode

# bytes from sandswing heads_cc.CcOut at the sw-laser-sweep commit:
# point(1, CLEAR|QUIET, 3, drive 9000, 4.12 mA, 2.031 V, 0.012 V)
POINT = bytes.fromhex("bf6601bf6709bf6b03bf1611bf364abf1703bf371cbf180fbf386fbf1900bf390cbf6a01")
# slot(3, (9000, 19000, "H5")), slot(4, None)
SLOT = bytes.fromhex("bf6603bf6c01bf1611bf364abf1425bf340dbf6d48bf6e35bf6f00bf7000bf7100bf7200"
                     "bf7300bf7400bf6a02")
EMPTY = bytes.fromhex("bf6604bf6c00bf167fbf367fbf147fbf347fbf6d00bf6e00bf6f00bf7000bf7100bf7200"
                      "bf7300bf7400bf6a03")
# ack(None, "forget", ok), ack(1, "sweep_end", "beam broken", 20000, 65535, QUIET)
ACK_FORGET = bytes.fromhex("bf6600bf6708bf680abf6900bf147fbf347fbf167fbf367fbf6a04")
ACK_END = bytes.fromhex("bf6601bf6708bf6807bf690ebf1427bf3407bf167fbf367ebf6a05")


class Decode(SimpleTestCase):
    def test_point(self):
        _, docs = decode(POINT)
        self.assertEqual(docs[0]["type"], "align_sweep")
        b = docs[0]["body"]
        self.assertEqual((b["ch"], b["i"], b["drv"], b["ma"], b["pt"], b["pt_span"], b["tower"]),
                         (1, 3, 9001, 4.12, 2.031, 0.012, C.HEADS_TOWER_QUIET))

    def test_slots(self):
        _, docs = decode(SLOT, EMPTY)
        self.assertEqual([d["type"] for d in docs], ["align_slot", "align_slot"])
        self.assertEqual(docs[0]["body"], {"ch": 3, "saved": True, "drv": 9001, "thr": 18998,
                                           "label": "H5", "via": "midi"})
        self.assertEqual(docs[1]["body"]["saved"], False)
        self.assertIsNone(docs[1]["body"]["drv"])

    def test_lineup_acks(self):
        _, docs = decode(ACK_FORGET, ACK_END)
        f, e = docs[0]["body"], docs[1]["body"]
        self.assertEqual((f["what"], f["ok"], f["ch"]), ("forget", True, None))
        self.assertEqual((e["what"], e["ok"], e["why"], e["ch"]), ("sweep_end", False, "beam broken", 1))

    def test_codes_match_sandswing(self):
        self.assertEqual(C.HEADS_WHY[20], "near threshold")
        self.assertEqual(C.HEADS_WHAT[7], "sweep_end")
        self.assertLess(C.HEADS_CC_LABEL + C.HEADS_LABEL_MAX - 1, 120)   # below the mode messages


class Commands(SimpleTestCase):
    def line(self, doc):
        return json.loads(serialheads.check_command(doc))

    def test_new_commands(self):
        self.assertEqual(self.line({"cmd": "align", "ch": 1, "sweep": True}),
                         {"cmd": "align", "ch": 1, "sweep": True})
        self.assertEqual(self.line({"cmd": "align", "ch": 1, "use": [9000, None]})["use"], [9000, None])
        self.assertEqual(self.line({"cmd": "align", "ch": 1, "save": 3, "label": " H5"}),
                         {"cmd": "align", "ch": 1, "save": 3, "label": "H5"})
        self.assertEqual(self.line({"cmd": "align", "forget": 8}), {"cmd": "align", "forget": 8})
        self.assertEqual(self.line({"cmd": "align", "saved": True}), {"cmd": "align", "saved": True})
        for bad in ({"cmd": "align", "ch": 1, "sweep": 1}, {"cmd": "align", "ch": 1, "use": [1]},
                    {"cmd": "align", "ch": 1, "use": [70000, 1]}, {"cmd": "align", "ch": 1, "save": 9},
                    {"cmd": "align", "ch": 1, "save": 1, "label": "123456789"},
                    {"cmd": "align", "ch": 1, "save": 1, "label": 'a"b'},
                    {"cmd": "align", "ch": 1, "label": "x"}, {"cmd": "align", "forget": 0},
                    {"cmd": "align", "ch": 1, "use": [True, 1]}):
            with self.assertRaises(ValueError, msg=bad):
                serialheads.check_command(bad)


DOC = {"ch": 1, "label": "H5", "end": None, "drv_before": 65535, "thr_before": 20000,
       "suggested_drv": 9000, "suggested_thr": 19000,
       "points": [[65535, 29.6, 2.1, 0.01], [9000, 4.1, 2.03, 0.01], [1310, 0.6, 1.2, None]]}


class Log(TestCase):
    def test_check(self):
        r = sweeplog.check(DOC)
        self.assertEqual((r["ch"], r["label"], r["end"], len(r["points"])), (1, "H5", "", 3))
        for bad in (dict(DOC, ch=0), dict(DOC, points=[]), dict(DOC, points=[[1, 2]]),
                    dict(DOC, label="x" * 9), dict(DOC, points=[[70000, 1, 1, 1]]),
                    dict(DOC, points=[[1, 1, 1, 1]] * (C.HEADS_SWEEP_POINTS_MAX + 1))):
            with self.assertRaises(ValueError):
                sweeplog.check(bad)

    def test_view_and_csv(self):
        url = reverse("farm_heads_sweep_log")
        r = self.client.post(url, json.dumps(DOC), content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["ok"])
        r = self.client.post(url, json.dumps(dict(DOC, ch="x")), content_type="application/json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post(url, "x" * (C.HEADS_SWEEP_LOG_MAX_B + 1), content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.get(url).status_code, 405)
        csv = self.client.get(reverse("farm_heads_sweep_csv") + "?days=1").content.decode()
        lines = csv.strip().splitlines()
        self.assertEqual(lines[0].split(","), list(sweeplog.CSV_FIELDS))
        self.assertIn("H5", lines[1])
        self.assertIn("100.0:2.1:29.6", lines[1])
        from .models import HeadSweep
        HeadSweep.objects.update(at=timezone.now() - timedelta(days=3))
        csv = self.client.get(reverse("farm_heads_sweep_csv") + "?days=1").content.decode()
        self.assertEqual(len(csv.strip().splitlines()), 1)


class Settings(SimpleTestCase):
    def test_sweep_settings(self):
        from bells import align
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        p = os.path.join(tmp, "settings.json")
        self.assertEqual(align.sweep_settings(p), C.HEADS_SWEEP_DEFAULTS)    # no file
        with open(p, "w") as f:
            json.dump({"sandheads": {"sweep": {"plateau_frac": 0.1, "margin_frac": 3,
                                               "min_range_v": "x"}}}, f)
        s = align.sweep_settings(p)
        self.assertEqual(s["plateau_frac"], 0.1)
        self.assertEqual(s["margin_frac"], C.HEADS_SWEEP_DEFAULTS["margin_frac"])
        self.assertEqual(s["min_range_v"], C.HEADS_SWEEP_DEFAULTS["min_range_v"])
        cfg = align.page_config({"id": "c"}, sweep=s)
        self.assertEqual(cfg["lineup"]["plateau_frac"], 0.1)
        self.assertEqual(cfg["lineup"]["slots"], C.HEADS_LINEUP_SLOTS)

    def test_page_has_the_lineup(self):
        src = open(os.path.join(os.path.dirname(__file__), "..", "bells", "templates", "bells",
                                "align.html")).read()
        self.assertLess(src.index("js/lineup.js"), src.index("js/align.js"))
