"""{% live_panel %} -- the live stroke list panel of the Strokes page (/events/strokes/)."""

from django import template
from django.urls import reverse

from events import constants as C

register = template.Library()


@register.inclusion_tag("events/live_panel.html")
def live_panel():
    return {
        "since_url": reverse("events:api_since"),
        "link_url": reverse("events:api_link"),
        "link_poll_ms": C.LINK_POLL_MS,
        "type": "",                     # every stored event: strokes + link/ingest
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


@register.inclusion_tag("events/top_menu.html")
def top_menu(current=None):
    """{% top_menu current=<farm index> %} -- the shared left side of every top
    line: Sandbells, one button per farm device, sandheads and Strokes (when the farm has a
    concentrator), Rings by day.  current is the farm page index, or "heads", "strokes", or
    "days" on those pages."""
    from bells.views import load_farm_instances      # here: bells imports events
    instances = load_farm_instances()
    devices = [{"index": i, "name": d["name"], "on": current == i}
               for i, d in enumerate(instances)]
    conc = next((i for i, d in enumerate(instances)
                 if d.get("family") == C.CONCENTRATOR_FAMILY), None)
    return {"devices": devices, "days_on": current == "days",
            "days_url": reverse("events:days"),
            # the sandheads tab, for the first concentrator (none: no button)
            "heads_url": "" if conc is None else reverse("farm_heads_index", args=[conc]),
            "heads_on": current == "heads",
            # the Strokes page: the live stroke list, full width (none: no button)
            "strokes_url": "" if conc is None else reverse("events:strokes"),
            "strokes_on": current == "strokes"}
