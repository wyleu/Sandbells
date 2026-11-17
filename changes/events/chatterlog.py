"""chatterlog.py -- the chatter-test log (HeadChatter rows).

The sandheads page's "Chatter test" panel runs a head at a laser drive and
PWM speed while sandtest turns the vane through the beam, then reads the
Pico's counts (sandswing chatter.py, decoded by headscc.py).  It POSTs each
run to /farm/heads/chatter-log/, checked here.  rows() is what the page's
results table shows (newest first); rows_csv() the download
(/farm/heads/chatter-log.csv?days=N).
"""

import csv
import io
from datetime import timedelta

from django.utils import timezone

from . import constants as C
from .serialheads import check_label

CSV_FIELDS = ("at_utc", "ch", "label", "drive_pct", "pwm_hz", "passes", "expected",
              "transitions", "clean", "clean_pct", "max_edges", "mean_edges",
              "max_burst_ms", "spurious", "end")
COUNT_KEYS = ("trans", "clean", "max_edges", "mean_x10", "max_burst_ms", "spurious")
PCT = 100
PCT_DP = 1
MEAN_SCALE = 10                 # mean_x10


def _count(v):
    """A count from the Pico (14-bit) or None."""
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= C.HEADS_CHATTER_COUNT_MAX:
        raise ValueError("bad count")
    return v


def check(doc):
    """The page's POST (parsed JSON) -> HeadChatter field dict.  ValueError."""
    if not isinstance(doc, dict):
        raise ValueError("not a chatter run")
    ch = doc.get("ch")
    if not isinstance(ch, int) or isinstance(ch, bool) or not 1 <= ch <= C.SERIAL_CMD_MAX_CH:
        raise ValueError("bad channel")
    drv = doc.get("drv")
    if not isinstance(drv, int) or isinstance(drv, bool) or not 0 <= drv <= C.HEADS_DUTY_FULL:
        raise ValueError("bad drive")
    hz = doc.get("pwm_hz")
    if hz is not None and (not isinstance(hz, int) or isinstance(hz, bool)
                           or not 0 < hz <= C.HEADS_PWM_HZ_MAX * 2):
        raise ValueError("bad pwm")
    passes = doc.get("passes")
    if passes is not None and (not isinstance(passes, int) or isinstance(passes, bool)
                               or not 1 <= passes <= C.HEADS_CHATTER_PASSES_MAX):
        raise ValueError("bad passes")
    out = {"ch": ch, "label": check_label(doc.get("label")), "drv": drv, "pwm_hz": hz,
           "passes": passes,
           "expected": None if passes is None else passes * C.HEADS_CHATTER_TRANS_PER_PASS}
    for k in COUNT_KEYS:
        out[k] = _count(doc.get(k))
    end = doc.get("end")
    out["end"] = "" if end is None else str(end)[:C.HEADS_CHATTER_END_MAX_LEN]
    return out


def save(doc):
    from .models import HeadChatter
    return HeadChatter.objects.create(**check(doc))


def _pct(d):
    return None if d is None else round(d * PCT / C.HEADS_DUTY_FULL, PCT_DP)


def clean_pct(r):
    if not r.trans:
        return None
    return round((r.clean or 0) * PCT / r.trans, PCT_DP)


def as_dict(r):
    return {"id": r.id, "at": r.at.isoformat(), "ch": r.ch, "label": r.label,
            "drv": r.drv, "drive_pct": _pct(r.drv), "pwm_hz": r.pwm_hz, "passes": r.passes,
            "expected": r.expected, "trans": r.trans, "clean": r.clean,
            "clean_pct": clean_pct(r), "max_edges": r.max_edges, "mean_x10": r.mean_x10,
            "max_burst_ms": r.max_burst_ms, "spurious": r.spurious, "end": r.end}


def rows(limit=C.HEADS_CHATTER_LIST_MAX):
    from .models import HeadChatter
    return [as_dict(r) for r in HeadChatter.objects.order_by("-at", "-id")[:limit]]


def _e(v):
    return "" if v is None else v


def rows_csv(days=C.PT_LOG_DAYS_DEFAULT, now=None):
    from .models import HeadChatter
    since = (now or timezone.now()) - timedelta(days=days)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(CSV_FIELDS)
    for r in HeadChatter.objects.filter(at__gte=since).order_by("at", "id"):
        mean = None if r.mean_x10 is None else r.mean_x10 / MEAN_SCALE
        w.writerow([r.at.isoformat(), r.ch, r.label, _e(_pct(r.drv)), _e(r.pwm_hz),
                    _e(r.passes), _e(r.expected), _e(r.trans), _e(r.clean),
                    _e(clean_pct(r)), _e(r.max_edges), _e(mean), _e(r.max_burst_ms),
                    _e(r.spurious), r.end])
    return out.getvalue()
