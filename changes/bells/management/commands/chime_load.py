"""manage.py chime_load [FILE] [--title T] [--order N] [--disable]

Add (or update, by title) a handbell tune for the Chimes page from a PDF or
an image, and make its page images.  With no FILE it loads the sample tune
kept in the repo (The Boars Head Carol).  Running it again with the same
file changes nothing."""

import subprocess
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from bells import chimes as chime_files
from bells.models import ChimeTune, CHIME_ORDER_DEFAULT

SAMPLE_FILE = Path(__file__).resolve().parents[2] / "chimes_samples" / "boars-head-carol.pdf"
SAMPLE_TITLE = "The Boars Head Carol"
PDFINFO = "pdfinfo"
PDFINFO_TIMEOUT_S = 30
PDFINFO_TITLE_KEY = "Title:"


def pdf_title(path: Path) -> str:
    """The PDF's own Title, or '' (pdfinfo comes with pdftoppm in poppler-utils)."""
    try:
        out = subprocess.run([PDFINFO, str(path)], capture_output=True, text=True,
                             timeout=PDFINFO_TIMEOUT_S).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""
    for line in out.splitlines():
        if line.startswith(PDFINFO_TITLE_KEY):
            return line[len(PDFINFO_TITLE_KEY):].strip()
    return ""


class Command(BaseCommand):
    help = "Add or update a Chimes tune from a PDF or image (no FILE: the bundled sample)."

    def add_arguments(self, parser):
        parser.add_argument("file", nargs="?", help="PDF or image; default: the sample tune")
        parser.add_argument("--title", help="menu title (default: the PDF's title, else the file name)")
        parser.add_argument("--order", type=int, default=CHIME_ORDER_DEFAULT,
                            help="menu position, lowest first (default %(default)s)")
        parser.add_argument("--disable", action="store_true", help="load it hidden from the menu")

    def handle(self, *args, **opts):
        path = Path(opts["file"]) if opts["file"] else SAMPLE_FILE
        if not path.is_file():
            raise CommandError("no such file: %s" % path)
        kind = chime_files.source_kind(path.name)
        if not kind:
            raise CommandError("%s: use a PDF or an image (%s)"
                               % (path.name, ", ".join(chime_files.ALLOWED_EXTENSIONS)))
        if kind == "pdf" and not chime_files.pdftoppm_path():
            raise CommandError(chime_files.MISSING_POPPLER_MESSAGE)

        title = opts["title"] or (SAMPLE_TITLE if path == SAMPLE_FILE else "")
        if not title and kind == "pdf":
            title = pdf_title(path)
        title = title or path.stem.replace("-", " ").replace("_", " ")

        tune = ChimeTune.objects.filter(title=title).first()
        created = tune is None
        if created:
            tune = ChimeTune(title=title)
        tune.order = opts["order"]
        tune.enable = not opts["disable"]

        sha = chime_files.file_sha256(path)
        try:
            if created or sha != tune.source_sha256:
                with open(path, "rb") as f:
                    tune.source.save(path.name, File(f), save=False)
            tune.save()
        except chime_files.ChimeRenderError as e:
            raise CommandError(str(e))

        self.stdout.write("%s %s: %d page(s), /chimes/%s/"
                          % ("added" if created else "updated", tune.title,
                             tune.page_count, tune.slug))
