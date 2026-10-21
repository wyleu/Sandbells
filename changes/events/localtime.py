"""localtime.py -- UTC ms <-> UK local time for display (pure).

The DB is UTC (utc_ms).  Pages show Europe/London, BST included; a local
day can be 23, 24 or 25 hours long.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import constants as C

UTC = timezone.utc
UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
ONE_MS = timedelta(milliseconds=1)
ONE_DAY = timedelta(days=1)
_TZ = None


def display_tz():
    global _TZ
    if _TZ is None:
        _TZ = ZoneInfo(C.DISPLAY_TZ_NAME)
    return _TZ


def ms_to_local(ms):
    return (UNIX_EPOCH + timedelta(milliseconds=ms)).astimezone(display_tz())


def dt_to_ms(dt):
    return (dt - UNIX_EPOCH) // ONE_MS


def local_date(ms):
    return ms_to_local(ms).date()


def day_bounds_ms(day):
    """Local day -> (start_ms, end_ms), end exclusive.  DST-correct."""
    tz = display_tz()
    start = datetime(day.year, day.month, day.day, tzinfo=tz)
    nxt = day + ONE_DAY
    end = datetime(nxt.year, nxt.month, nxt.day, tzinfo=tz)
    return dt_to_ms(start), dt_to_ms(end)


def parse_day(text):
    return datetime.strptime(text, C.DATE_FORMAT).date()


def local_iso(ms):
    """'2026-10-25T01:30:00.250+01:00' or None."""
    return None if ms is None else ms_to_local(ms).isoformat(timespec="milliseconds")


def local_hms(ms):
    return None if ms is None else ms_to_local(ms).strftime("%H:%M:%S")


def local_hms_ms(ms):
    """'16:30:35.250' or None."""
    if ms is None:
        return None
    t = ms_to_local(ms)
    return "%s.%03d" % (t.strftime("%H:%M:%S"), t.microsecond // 1000)


def day_label(day):
    return day.strftime(C.DAY_LABEL_FORMAT)


def format_duration(seconds):
    """34:29 or 1:02:05 (h:mm:ss when an hour or more)."""
    total = int(round(seconds))
    h, rest = divmod(total, C.SECONDS_PER_HOUR)
    m, s = divmod(rest, C.SECONDS_PER_MINUTE)
    return "%d:%02d:%02d" % (h, m, s) if h else "%d:%02d" % (m, s)
