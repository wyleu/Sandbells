# Chimes: handbell tune sheets

A **Chimes** button on the shared top line (left group, after Ingest) and in
the home page's left column opens `/chimes/`: the chosen tune's sheet fitted
to the screen on black, with the tune menu on the right in the home menu's
style (red first letter).  Tunes with more than one page get Previous / Next.
Tap the sheet (or press `f` / Enter) for `/chimes/<slug>/<page>/full/`: only
the sheet, whole screen; tap or Escape to come back, arrows turn the page.

## Managing tunes

Admin → Bells → **Chime tunes**: title, order (lowest first), enable, notes,
and the source file: a **PDF** (each page becomes one screen) or a single
**image** (PNG, JPEG, GIF, WebP).  Saving makes the page images; the
"Re-make page images" action redoes them.  Deleting a tune removes its files.

From the shell:

    python manage.py chime_load                     # the sample: The Boars Head Carol
    python manage.py chime_load tune.pdf --title "Tune" --order 10

## How it works

* PDFs are rendered **once, at upload**, by `pdftoppm` (package
  `poppler-utils`) to PNGs 1080 px tall (`bells/chimes.py`,
  `PAGE_HEIGHT_PX`), aspect kept.  Images taller than that are scaled down.
  The browser never renders a PDF.
* Without `pdftoppm` a PDF upload is refused with "sudo apt install
  poppler-utils"; images still work.
* Files live in `changes/media/chimes/` (git-ignored): `sources/` and
  `pages/<tune id>/page-NNN.png`.  An optional `SANDBELLS_CHIMES_ROOT`
  setting moves them; `settings.py` is not changed.
* MEDIA is not configured and nginx does not serve it, so Django sends the
  page images (`/chimes/<slug>/<page>/image.png`) with a week-long cache
  header; the `?v=` in the address changes when the source changes.
* Models: `ChimeTune`, `ChimePage` (migration `bells/0005_chimetune`).
  Rollback: `python manage.py migrate bells 0004` before leaving the branch.
