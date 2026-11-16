"""manage.py chime_load [FILE] [--title T] [--order N] [--disable]

Add (or update, by title) a handbell tune for the Chimes page from a PDF or
an image, and make its page images.  With no FILE it loads the sample tune
kept in the repo (The Boars Head Carol).  Running it again with the same
file changes nothing.

FILE may also be a chime-build bundle (tools/chimes/chime-build): its folder
or its .chime.zip.  The bundle's score.pdf becomes the sheet, and its MIDI
and note map make Play and the dot work."""

import json
import subprocess
import tempfile
import zipfile
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
BUNDLE_META = "tune.json"
BUNDLE_FORMAT = "sandbells-chime-bundle"
BUNDLE_ZIP_SUFFIX = ".zip"


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
        if path.is_dir() or path.suffix.lower() == BUNDLE_ZIP_SUFFIX:
            return self.load_bundle(path, opts)
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

    def load_bundle(self, path, opts):
        if path.is_dir():
            return self._load_bundle_dir(path, opts)
        if not path.is_file():
            raise CommandError("no such file: %s" % path)
        try:
            with tempfile.TemporaryDirectory(prefix="chime-bundle-") as tmp:
                with zipfile.ZipFile(path) as z:
                    root = Path(tmp).resolve()
                    for name in z.namelist():           # nothing outside the folder
                        if not (root / name).resolve().is_relative_to(root):
                            raise CommandError("unsafe path in %s: %s" % (path.name, name))
                    z.extractall(root)
                metas = sorted(root.rglob(BUNDLE_META))
                if not metas:
                    raise CommandError("%s has no %s: not a chime-build bundle"
                                       % (path.name, BUNDLE_META))
                return self._load_bundle_dir(metas[0].parent, opts)
        except zipfile.BadZipFile as e:
            raise CommandError("%s: %s" % (path.name, e))

    def _load_bundle_dir(self, folder, opts):
        meta_path = folder / BUNDLE_META
        try:
            meta = json.loads(meta_path.read_text())
        except (OSError, ValueError) as e:
            raise CommandError("%s: %s" % (meta_path, e))
        if meta.get("format") != BUNDLE_FORMAT:
            raise CommandError("%s is not a chime-build bundle" % meta_path)
        files = {k: folder / meta.get(k, "") for k in ("pdf", "midi", "notemap")}
        for k, f in files.items():
            if not meta.get(k) or not f.is_file():
                raise CommandError("bundle %s lacks its %s file" % (folder.name, k))
        if not chime_files.pdftoppm_path():
            raise CommandError(chime_files.MISSING_POPPLER_MESSAGE)
        title = opts["title"] or meta.get("title") or folder.name
        tune = ChimeTune.objects.filter(title=title).first()
        created = tune is None
        if created:
            tune = ChimeTune(title=title)
        tune.order = opts["order"]
        tune.enable = not opts["disable"]
        slug = meta.get("slug") or ""
        for field, f in (("source", files["pdf"]), ("midi", files["midi"]),
                         ("notemap", files["notemap"])):
            with open(f, "rb") as fh:
                getattr(tune, field).save("%s-%s" % (slug, f.name) if slug else f.name,
                                          File(fh), save=False)
        try:
            tune.save()
        except chime_files.ChimeRenderError as e:
            raise CommandError(str(e))
        self.stdout.write("%s %s from bundle: %d page(s), MIDI and note map, /chimes/%s/"
                          % ("added" if created else "updated", tune.title,
                             tune.page_count, tune.slug))
        if tune.bell_problems:
            lines = tune.bell_problems.splitlines()
            self.stdout.write("WARNING: %d note(s) are not on the 8 bells, e.g. %s"
                              % (len(lines), lines[0]))
