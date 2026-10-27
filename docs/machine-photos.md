# Machine photos

Every machine on the farm has a photo, shown the same way on every page about
that machine, so the picture you see on its status page is the picture you see
on its control pages.

## Where things are

| What | Where |
|------|-------|
| the pictures | `changes/bells/static/img/farm/<name>.jpg` (600x600) and `<name>-thumb.jpg` (160x160) |
| machine -> picture | `changes/bells/farm_photos.py`: `PHOTOS` (key -> file name) and `ALIASES` |
| the one piece of markup | `{% machine_photo %}` in `changes/bells/templatetags/farm_ui.py` |
| its look (rounded square, warm frame) | `changes/bells/templates/bells/machine_photo_style.html` |

`static/img/farm/` is the first `img` directory the repo has (it follows the
`css/`, `js/`, `icons/` layout under `bells/static`); `collectstatic` copies it
to `/var/www/sandbells/static/img/farm/` like everything else.

## Using it in a page

```django
{% load farm_ui %}
{% machine_photo inst %}                            {# 112 px, the registry entry #}
{% machine_photo inst size=64 %}                    {# smaller #}
{% machine_photo "sandtest" size=40 %}              {# 40 px, a plain key, uses the thumbnail #}
{% machine_photo inst size=112 placeholder=True %}  {# neutral square with the initial when there is no photo #}
```

* The first argument is a farm registry entry (`id`, then `name`, then `host`
  are tried) or a plain key such as `"sandswing"`. Keys are case-insensitive and
  a trailing `.local` is ignored.
* Sizes up to 80 px use the 160 px thumbnail, bigger ones the 600 px picture.
* The tag writes `width`/`height` (no layout shift), `alt` = the machine name,
  `loading="lazy"`, and `?v=<git hash>` from the page's `git_hash` context
  (nginx caches `/static` for 7 days, so the url must change with the code).
* No photo for that machine: nothing is drawn (or the placeholder with
  `placeholder=True`). If a file is not collected yet, the `<img>` hides itself
  and the neutral square stays. Never a broken-image icon.
* The css: pages that use `{% include "events/menu_style.html" %}` (the shared
  top line) already have it. A page without that line adds
  `{% include "bells/machine_photo_style.html" %}` in `<head>`.
* A page can shrink the picture for small screens with
  `#my-header .mphoto { --s: 52px !important; }` (the farm page does this
  under 640 px of height, for the kiosk screens).

## Adding a machine

1. Put `<key>.jpg` (600x600) and `<key>-thumb.jpg` (160x160) in `static/img/farm/`
   (about 30-80 KB each).
2. Add `"<key>": "<key>",` to `PHOTOS` in `farm_photos.py`
   (and an `ALIASES` line if the registry id differs from the host name, like
   `sandsense-clock`).
3. `python manage.py test bells.tests_photos` checks that every mapped file
   exists, is a JPEG, is square at the right size and stays small.

## Pages that use it

| Page | Where |
|------|-------|
| farm status page of every machine (`/farm/status/<n>/`) | the identity line under the top line (112 px, 52 px on small screens), `bells/farm_status.html` |
| sandheads tab (`/farm/heads/`, once `/farm/align/`) | the same identity line, with the `sandswing` photo (112 px, 52 px on small screens), `bells/align.html`; its look comes with `events/menu_style.html` |

## Pages on other branches (not in this branch; add the one line when they merge)

These pages are not on `menu-days`, so this branch does not touch them. Each
needs the tag loaded and one line:

* **Sandtest page** (branch `sandtest`, `changes/sandtest/templates/sandtest/page.html`):
  `{% load static events_live farm_ui %}` and, in `<header id="st-header">`
  after `{% top_menu current="sandtest" %}`, add `{% machine_photo "sandtest" size=48 %}`.
  The `sandtest` key is already in `PHOTOS`. The page already includes
  `events/menu_style.html`, so the css comes with it.
* **Power controls** (branch `power`, `bells/power_controls.html`) sit on the
  farm status page, which already shows the photo, so nothing extra is needed.
  Already merged: on the `farm-photos-power` branch (this branch on top of
  `power`) the one line `{% include "bells/power_controls.html" %}` is in
  `farm_status.html` inside `<div id="farm-id">`, right after
  `<span id="farm-summary">`, and `bells/tests_power.py` checks that the photo
  and the Reboot / Shut down buttons render together. If you merge `power` and
  `farm-photos` by hand instead, keep that line there (git reports a small
  conflict in that file: the new header wins, with the include added to it).
