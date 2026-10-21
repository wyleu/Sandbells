"""{% live_panel %} -- the live stroke list panel for the sandswing farm page."""

from django import template
from django.urls import reverse

from events import constants as C

register = template.Library()


@register.inclusion_tag("events/live_panel.html")
def live_panel():
    return {
        "since_url": reverse("events:api_since"),
        "type": C.TYPE_STROKE,
        "first_load": C.LIVE_FIRST_LOAD,
        "batch": C.LIVE_LIMIT_DEFAULT,
        "dom_rows": C.LIVE_DOM_ROWS,
        "poll_ms": C.LIVE_POLL_MS,
        "retry_max_ms": C.LIVE_RETRY_MAX_MS,
        "fails_warn": C.LIVE_FAILS_WARN,
        "idle_ms": C.LIVE_IDLE_NOTE_MS,
        "ring_gap_ms": C.RING_GAP_MS,
        "timeout_ms": C.LIVE_FETCH_TIMEOUT_MS,
        "tz": C.DISPLAY_TZ_NAME,
    }
