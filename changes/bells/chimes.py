"""Chimes: handbell tune sheets shown full screen on the kiosk.

Each tune (bells.models.ChimeTune) is an uploaded PDF or image.  PDFs are
turned into PNG pages here, once, with pdftoppm (poppler-utils) at the
screen height, so the Pi 3 browser only ever shows a plain image: no PDF
rendering in Luakit, nothing heavy per view.

The files live in their own folder (CHIMES_ROOT), not MEDIA_ROOT, so the
settings file is not touched.  An optional SANDBELLS_CHIMES_ROOT setting
moves it; tests point it at a temporary directory.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


# ---------------------------------------------------------------------------
# Constants (no magic numbers at the call sites)
# ---------------------------------------------------------------------------

CHIMES_ROOT_SETTING = "SANDBELLS_CHIMES_ROOT"
CHIMES_DEFAULT_SUBDIR = ("media", "chimes")      # under BASE_DIR (changes/)

SCREEN_WIDTH_PX = 1920                           # the tower kiosk screen
SCREEN_HEIGHT_PX = 1080
PAGE_HEIGHT_PX = SCREEN_HEIGHT_PX                # every page is rendered this tall

SOURCES_DIR = "sources"                          # uploaded PDFs / images
PAGES_DIR = "pages"                              # generated PNGs, one folder per tune
MIDI_DIR = "midi"                                # optional MIDI per tune (Play)
NOTEMAP_DIR = "notemaps"                         # optional note map per tune (the dot)
MIDI_EXTENSIONS = (".mid", ".midi")
NOTEMAP_EXTENSIONS = (".json",)
PAGE_IMAGE_FORMAT = "png"
PAGE_FILE_TEMPLATE = "page-{number:03d}.png"

PDF_EXTENSIONS = (".pdf",)
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp")
ALLOWED_EXTENSIONS = PDF_EXTENSIONS + IMAGE_EXTENSIONS

PDFTOPPM = "pdftoppm"
POPPLER_PACKAGE = "poppler-utils"
PDFTOPPM_TIMEOUT_S = 120                         # a long tune on a Pi 3 is a few seconds
PDFTOPPM_KEEP_ASPECT = "-1"                      # pdftoppm: -1 keeps the aspect ratio

HASH_CHUNK_BYTES = 64 * 1024
IMAGE_CACHE_SECONDS = 7 * 24 * 60 * 60           # pages change only on re-upload (?v=hash)

MISSING_POPPLER_MESSAGE = (
    "pdftoppm was not found, so this PDF cannot be turned into page images. "
    "Install it on the Pi with: sudo apt install %s" % POPPLER_PACKAGE
)


class ChimeRenderError(Exception):
    """The source could not be turned into page images.  The message says why."""


def chimes_root() -> Path:
    """The folder holding the sources and the generated pages (read each call,
    so override_settings in tests works)."""
    configured = getattr(settings, CHIMES_ROOT_SETTING, None)
    if configured:
        return Path(configured)
    return Path(settings.BASE_DIR).joinpath(*CHIMES_DEFAULT_SUBDIR)


@deconstructible
class ChimeStorage(FileSystemStorage):
    """FileSystemStorage rooted at chimes_root(), resolved at use time.  No URL:
    the pages are sent by bells.chimes_views (MEDIA is not configured)."""

    def __init__(self):
        super().__init__(location=None, base_url=None)

    @property
    def base_location(self):
        return str(chimes_root())

    @property
    def location(self):
        return str(Path(self.base_location).resolve())

    def deconstruct(self):
        return ("bells.chimes.ChimeStorage", (), {})


chime_storage = ChimeStorage()


def source_kind(name: str) -> str:
    """'pdf', 'image', or '' for anything else."""
    ext = Path(name or "").suffix.lower()
    if ext in PDF_EXTENSIONS:
        return "pdf"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    return ""


def pdftoppm_path() -> str | None:
    return shutil.which(PDFTOPPM)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(HASH_CHUNK_BYTES), b""):
            h.update(chunk)
    return h.hexdigest()


def _page_number(path: Path) -> int:
    """pdftoppm names pages prefix-1.png or prefix-01.png (padded to the page
    count's width).  The trailing number is the page."""
    m = re.search(r"-(\d+)\.%s$" % PAGE_IMAGE_FORMAT, path.name)
    return int(m.group(1)) if m else 0


def render_pdf(source: Path, out_dir: Path, height: int = PAGE_HEIGHT_PX) -> list[Path]:
    """Render every page of source to out_dir/page-NNN.png, height pixels tall,
    aspect kept.  Returns the files in page order.  Raises ChimeRenderError."""
    exe = pdftoppm_path()
    if not exe:
        raise ChimeRenderError(MISSING_POPPLER_MESSAGE)
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out_dir.parent) as tmp:
        prefix = Path(tmp) / "page"
        cmd = [exe, "-" + PAGE_IMAGE_FORMAT,
               "-scale-to-y", str(height), "-scale-to-x", PDFTOPPM_KEEP_ASPECT,
               str(source), str(prefix)]
        try:
            done = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=PDFTOPPM_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            raise ChimeRenderError("pdftoppm took longer than %d s on %s"
                                   % (PDFTOPPM_TIMEOUT_S, source.name))
        if done.returncode != 0:
            raise ChimeRenderError("pdftoppm failed on %s: %s"
                                   % (source.name, (done.stderr or "").strip()))
        made = sorted(Path(tmp).glob("page-*.%s" % PAGE_IMAGE_FORMAT), key=_page_number)
        if not made:
            raise ChimeRenderError("pdftoppm made no pages from %s" % source.name)
        for old in out_dir.glob("page-*.%s" % PAGE_IMAGE_FORMAT):
            old.unlink()
        result = []
        for number, f in enumerate(made, start=1):
            dest = out_dir / PAGE_FILE_TEMPLATE.format(number=number)
            shutil.move(str(f), dest)
            result.append(dest)
    return result


def render_image(source: Path, out_dir: Path, height: int = PAGE_HEIGHT_PX) -> list[Path]:
    """A plain image upload is one page: saved as PNG, scaled down (never up)
    to height pixels tall.  Raises ChimeRenderError."""
    from PIL import Image, UnidentifiedImageError

    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(source) as im:
            im.load()
            if im.height > height:
                width = max(1, round(im.width * height / im.height))
                im = im.resize((width, height), Image.LANCZOS)
            if im.mode not in ("RGB", "RGBA", "L", "LA"):
                im = im.convert("RGBA")
            for old in out_dir.glob("page-*.%s" % PAGE_IMAGE_FORMAT):
                old.unlink()
            dest = out_dir / PAGE_FILE_TEMPLATE.format(number=1)
            im.save(dest, format=PAGE_IMAGE_FORMAT.upper())
    except (UnidentifiedImageError, OSError) as e:
        raise ChimeRenderError("%s is not an image this Pi can read: %s" % (source.name, e))
    return [dest]


def render_source(source: Path, out_dir: Path) -> list[Path]:
    kind = source_kind(source.name)
    if kind == "pdf":
        return render_pdf(source, out_dir)
    if kind == "image":
        return render_image(source, out_dir)
    raise ChimeRenderError("%s: use a PDF or an image (%s)"
                           % (source.name, ", ".join(ALLOWED_EXTENSIONS)))
