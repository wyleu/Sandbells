"""headlog.py -- the PT level log (HeadLevel rows) from the serial heartbeat.

sandswing's heartbeat body carries "pt": [ch, volts, spread] (pt_level.brief:
the Orange/White wire on GP27, only while that channel is an active head)
and "thr": {"target": [...], "readback": [...]}.  ingest_serial hands every
good heartbeat to PtLogger.heartbeat(); one HeadLevel row per wired head is
stored at most every PT_LOG_EVERY_S, so a day is ~300 rows: small enough to
keep, enough to see the light change from day to night.  rows_csv() is the
review side (/farm/heads/pt-log.csv?days=N).
"""

import csv
import io
import logging
import time
from datetime import timedelta

from django.utils import timezone

from . import constants as C

log = logging.getLogger(C.LOGGER_NAME + ".serial")

CSV_FIELDS = ("at_utc", "uid", "ch", "pt_v", "pt_span", "thr", "thr_rb", "tower")


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _at(lst, i):
    return _num(lst[i]) if isinstance(lst, list) and 0 <= i < len(lst) else None


def reading(hb):
    """A heartbeat doc -> HeadLevel field dict, or None (no PT reading)."""
    b = hb.get("body") if isinstance(hb, dict) else None
    if not isinstance(b, dict):
        return None
    pt = b.get("pt")
    if not (isinstance(pt, list) and len(pt) >= 2 and _num(pt[0]) is not None
            and _num(pt[1]) is not None):
        return None
    ch = int(pt[0])
    if not 1 <= ch <= C.SERIAL_CMD_MAX_CH:
        return None
    thr = b.get("thr") if isinstance(b.get("thr"), dict) else {}
    return {"uid": str(b.get("uid") or "")[:C.PT_LOG_UID_MAX_LEN], "ch": ch,
            "pt_v": float(pt[1]), "pt_span": _num(pt[2]) if len(pt) > 2 else None,
            "thr": _at(thr.get("target"), ch - 1), "thr_rb": _at(thr.get("readback"), ch - 1),
            "tower": str(b.get("tower") or "")[:C.PT_LOG_TOWER_MAX_LEN]}


class PtLogger:
    """heartbeat(doc, now_ms): store a reading if PT_LOG_EVERY_S has passed
    for that channel.  Never raises (a failed write is logged once)."""

    def __init__(self, every_s=C.PT_LOG_EVERY_S, clock=time.monotonic, save=None):
        self.every_s = every_s
        self.clock = clock
        self.save = save or _save
        self.last = {}            # ch -> clock() of the last row
        self.rows = 0
        self.failed = 0

    def heartbeat(self, doc, now_ms=None):
        r = reading(doc)
        if r is None:
            return False
        now = self.clock()
        t = self.last.get(r["ch"])
        if t is not None and now - t < self.every_s:
            return False
        try:
            self.save(r)
        except Exception as e:
            self.failed += 1
            if self.failed == 1:
                log.warning("PT level log: %s", e)
            return False
        self.last[r["ch"]] = now
        self.rows += 1
        return True


def _save(r):
    from .models import HeadLevel
    HeadLevel.objects.create(**r)


def rows_csv(days=C.PT_LOG_DAYS_DEFAULT, now=None):
    """The last days of HeadLevel as CSV text (UTC ISO times)."""
    from .models import HeadLevel
    since = (now or timezone.now()) - timedelta(days=days)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(CSV_FIELDS)
    for h in HeadLevel.objects.filter(at__gte=since).order_by("at"):
        w.writerow([h.at.isoformat(), h.uid, h.ch, h.pt_v, h.pt_span, h.thr, h.thr_rb, h.tower])
    return out.getvalue()
