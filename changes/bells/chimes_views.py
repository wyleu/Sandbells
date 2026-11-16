"""Chimes pages: a side menu of handbell tunes and the chosen tune's sheet,
fitted to the screen.  The page images are made once at upload
(bells/chimes.py); these views only pick and send them."""

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.cache import patch_cache_control

from bells import chimes as chime_files
from bells.models import ChimeTune, ChimePage

FIRST_PAGE = 1


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
