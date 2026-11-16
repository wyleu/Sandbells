"""Chimes pages: a side menu of handbell tunes and the chosen tune's sheet,
fitted to the screen.  The page images are made once at upload
(bells/chimes.py); these views only pick and send them."""

import json

from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.cache import patch_cache_control
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from bells import chime_player
from bells import chimes as chime_files
from bells.controls import client_ip, is_local
from bells.models import ChimeTune, ChimePage

FIRST_PAGE = 1
PAGE_PLACEHOLDER = 999999          # replaced by the page number in chime_player.js
STATE_POLL_MS = 1000               # how often the page asks whether the player runs
BELL_PROBLEMS_SHOWN = 20          # in the warning's tooltip; the admin lists more
DOT_TICK_MS = 50                   # how often the dot moves (from the clock, not the poll)


def _menu():
    return ChimeTune.objects.filter(enable=True).order_by("order", "title")


def _page_context(tune, number):
    page = get_object_or_404(ChimePage, tune=tune, number=number)
    prev_n = number - 1 if number > FIRST_PAGE else None
    next_n = number + 1 if number < tune.page_count else None
    return {
        "tune": tune,
        "page": page,
        "image_url": "%s?v=%s" % (reverse("chime_image", args=[tune.slug, number]),
                                  tune.source_sha256[:12]),
        "prev_url": reverse("chime_page", args=[tune.slug, prev_n]) if prev_n else "",
        "next_url": reverse("chime_page", args=[tune.slug, next_n]) if next_n else "",
        "full_url": reverse("chime_full", args=[tune.slug, number]),
        "prev_full_url": reverse("chime_full", args=[tune.slug, prev_n]) if prev_n else "",
        "next_full_url": reverse("chime_full", args=[tune.slug, next_n]) if next_n else "",
        "back_url": reverse("chime_page", args=[tune.slug, number]),
        "screen_w": chime_files.SCREEN_WIDTH_PX,
        "screen_h": chime_files.SCREEN_HEIGHT_PX,
        "player": _player_context(tune),
    }


def _player_context(tune):
    """What the Play / Stop / tempo bar and the dot need (None: no MIDI)."""
    if not tune.midi:
        return None
    problems = tune.bell_problems.splitlines()
    return {
        "state_url": reverse("chime_player_state"),
        "play_url": reverse("chime_player_play"),
        "stop_url": reverse("chime_player_stop"),
        "outputs_url": reverse("chime_player_outputs"),
        "ports_url": reverse("chime_player_ports"),
        "outputs": chime_player.outputs().as_dict(),
        "notemap_url": ("%s?v=%s" % (reverse("chime_notemap", args=[tune.slug]),
                                     tune.pub_date.strftime("%Y%m%d%H%M%S"))
                        if tune.notemap else ""),
        "page_url": reverse("chime_page", args=[tune.slug, PAGE_PLACEHOLDER]),
        "full_url": reverse("chime_full", args=[tune.slug, PAGE_PLACEHOLDER]),
        "page_placeholder": PAGE_PLACEHOLDER,
        "tempo_min": chime_player.TEMPO_PERCENT_MIN,
        "tempo_max": chime_player.TEMPO_PERCENT_MAX,
        "tempo_step": chime_player.TEMPO_PERCENT_STEP,
        "tempo_default": chime_player.TEMPO_PERCENT_DEFAULT,
        "state_poll_ms": STATE_POLL_MS,
        "dot_tick_ms": DOT_TICK_MS,
        "bell_problem_count": len(problems),
        "bell_problems": problems[:BELL_PROBLEMS_SHOWN],
    }


def chimes(request):
    """/chimes/ -- the menu, showing the first tune (or a note when there are none)."""
    tunes = _menu()
    first = next((t for t in tunes if t.page_count), None)
    context = {"tunes": tunes, "tune": None}
    if first:
        context.update(_page_context(first, FIRST_PAGE))
    return render(request, "bells/chimes.html", context)


def chime_page(request, slug, page=FIRST_PAGE):
    """/chimes/<slug>/[<page>/] -- the menu and that page of the tune."""
    tune = get_object_or_404(ChimeTune, slug=slug, enable=True)
    context = {"tunes": _menu()}
    context.update(_page_context(tune, page))
    return render(request, "bells/chimes.html", context)


def chime_full(request, slug, page=FIRST_PAGE):
    """/chimes/<slug>/<page>/full/ -- just the sheet, whole screen, black around it."""
    tune = get_object_or_404(ChimeTune, slug=slug, enable=True)
    return render(request, "bells/chime_full.html", _page_context(tune, page))


def chime_image(request, slug, page):
    """The PNG itself.  MEDIA is not served by nginx, so Django sends it; the
    ?v= in the address changes on re-upload, so it can be cached for long."""
    tune = get_object_or_404(ChimeTune, slug=slug)
    p = get_object_or_404(ChimePage, tune=tune, number=page)
    if not p.image or not p.image.storage.exists(p.image.name):
        raise Http404("page image missing; re-make it in the admin")
    response = FileResponse(p.image.open("rb"), content_type="image/png")
    patch_cache_control(response, public=True, max_age=chime_files.IMAGE_CACHE_SECONDS)
    return response


# ---------------------------------------------------------------------------
# Player: Play / Stop / state, and the note map the dot follows
# ---------------------------------------------------------------------------

NOTEMAP_CACHE_SECONDS = chime_files.IMAGE_CACHE_SECONDS   # ?v= changes with the file
HTTP_BAD_REQUEST = 400
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_UNAVAILABLE = 503


def _compact_events(data):
    """[sec, page, fx, fy] per event: all the page needs to move the dot."""
    return [[ev["sec"], ev.get("page"), ev.get("fx"), ev.get("fy")]
            for ev in data.get("events", [])]


def chime_notemap_json(request, slug):
    tune = get_object_or_404(ChimeTune, slug=slug)
    data = tune.notemap_data()
    if data is None:
        raise Http404("no note map")
    response = JsonResponse({"slug": tune.slug, "bpm": data.get("bpm"),
                             "pages": tune.page_count, "events": _compact_events(data)})
    patch_cache_control(response, public=True, max_age=NOTEMAP_CACHE_SECONDS)
    return response


def _body(request):
    try:
        return json.loads(request.body or b"{}")
    except ValueError:
        return {}


def _local_only(request):
    if not is_local(client_ip(request)):
        return JsonResponse({"ok": False, "error": "only from this Pi or the LAN"},
                            status=HTTP_FORBIDDEN)
    return None


@require_POST
def chime_player_play(request):
    refused = _local_only(request)
    if refused:
        return refused
    body = _body(request)
    tune = ChimeTune.objects.filter(slug=body.get("slug", ""), enable=True).first()
    if tune is None:
        return JsonResponse({"ok": False, "error": "no such tune"}, status=HTTP_NOT_FOUND)
    try:
        state = chime_player.play(tune, body.get("tempo", chime_player.TEMPO_PERCENT_DEFAULT),
                                  body.get("from_sec", 0.0))
    except chime_player.PlayerError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=HTTP_UNAVAILABLE)
    return JsonResponse(dict(state, ok=True))


@require_POST
def chime_player_stop(request):
    refused = _local_only(request)
    if refused:
        return refused
    chime_player.stop()
    return JsonResponse({"ok": True, "playing": False})


@require_POST
def chime_player_outputs(request):
    """The MIDI out / HDMI audio switches (and the MIDI port), kept in the DB."""
    refused = _local_only(request)
    if refused:
        return refused
    body = _body(request)

    def flag(key):
        return bool(body[key]) if key in body else None

    try:
        outs = chime_player.set_outputs(midi_out=flag("midi_out"),
                                        hdmi_audio=flag("hdmi_audio"),
                                        midi_port=body.get("midi_port"))
    except chime_player.PlayerError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=HTTP_BAD_REQUEST)
    return JsonResponse({"ok": True, "outputs": outs})


@require_GET
@never_cache
def chime_player_ports(request):
    """ALSA sequencer ports MIDI out can play to (aplaymidi -l), the Pico left out."""
    listing = chime_player.list_ports()
    return JsonResponse({"ports": listing["ports"], "left_out": len(listing["left_out"]),
                         "error": listing["error"],
                         "outputs": chime_player.outputs().as_dict()})


@require_GET
@never_cache
def chime_player_state(request):
    state = chime_player.status()
    events = None
    if state["playing"] and state["slug"]:
        tune = ChimeTune.objects.filter(slug=state["slug"]).first()
        data = tune.notemap_data() if tune else None
        events = data.get("events") if data else None
        state = chime_player.status(events, now=state["now"])
    return JsonResponse(state)
