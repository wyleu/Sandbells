"""sweeplog.py -- the line-up sweep log (HeadSweep rows).

The sandheads page has every point of a sweep (sandswing sweep.py, decoded
by headscc.py) and the label typed for the head; when a sweep ends it POSTs
them to /farm/heads/sweep-log/, checked here.  rows_csv() is the review side
(/farm/heads/sweep-log.csv?days=N): one row per sweep, the points as
"drive%:PT V:mA" separated by spaces, for day / night comparison.
"""

import csv
import io
from datetime import timedelta

from django.utils import timezone

from . import constants as C
from .serialheads import check_label

CSV_FIELDS = ("at_utc", "ch", "label", "end", "drv_before_pct", "thr_before",
              "suggested_drv_pct", "suggested_thr", "points")
PCT = 100
PCT_DP = 1
V_DP = 3
MA_DP = 2
POINT_LEN = 4                   # drive, mA, PT volts, PT spread


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _duty(v):
    return v if isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= C.HEADS_DUTY_FULL else None


def check(doc):
    """The page's POST (parsed JSON) -> HeadSweep field dict.  ValueError."""
    if not isinstance(doc, dict):
        raise ValueError("not a sweep")
    ch = doc.get("ch")
    if not isinstance(ch, int) or isinstance(ch, bool) or not 1 <= ch <= C.SERIAL_CMD_MAX_CH:
        raise ValueError("bad channel")
    pts = doc.get("points")
    if not isinstance(pts, list) or not pts or len(pts) > C.HEADS_SWEEP_POINTS_MAX:
        raise ValueError("bad points")
    out_pts = []
    for p in pts:
        if not isinstance(p, list) or len(p) != POINT_LEN or _duty(p[0]) is None:
            raise ValueError("bad point")
        out_pts.append([p[0], _num(p[1]), _num(p[2]), _num(p[3])])
    end = doc.get("end")
    end = "" if end is None else str(end)[:C.HEADS_SWEEP_END_MAX_LEN]
    return {"ch": ch, "label": check_label(doc.get("label")), "end": end, "points": out_pts,
            "drv_before": _duty(doc.get("drv_before")), "thr_before": _duty(doc.get("thr_before")),
            "suggested_drv": _duty(doc.get("suggested_drv")),
            "suggested_thr": _duty(doc.get("suggested_thr"))}


def save(doc):
    from .models import HeadSweep
    return HeadSweep.objects.create(**check(doc))


def _pct(d):
    return "" if d is None else round(d * PCT / C.HEADS_DUTY_FULL, PCT_DP)


def _f(v, dp):
    return "" if v is None else str(round(v, dp))


def rows_csv(days=C.PT_LOG_DAYS_DEFAULT, now=None):
    from .models import HeadSweep
    since = (now or timezone.now()) - timedelta(days=days)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(CSV_FIELDS)
    for s in HeadSweep.objects.filter(at__gte=since).order_by("at"):
        pts = " ".join("%s:%s:%s" % (_pct(p[0]), _f(p[2], V_DP), _f(p[1], MA_DP))
                       for p in s.points or [])
        w.writerow([s.at.isoformat(), s.ch, s.label, s.end, _pct(s.drv_before), s.thr_before,
                    _pct(s.suggested_drv), s.suggested_thr, pts])
    return out.getvalue()
