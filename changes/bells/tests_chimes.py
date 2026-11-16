"""Chimes: handbell tune sheets.  The model and its page images (pdftoppm for
PDFs, Pillow for images), the admin, the load command, the pages and the
Chimes button of the shared top line and the home page."""

import io
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from bells import chimes as chime_files
from bells.admin import ChimeTuneForm
from bells.management.commands.chime_load import SAMPLE_FILE, SAMPLE_TITLE
from bells.models import ChimeTune, ChimePage

HAVE_POPPLER = bool(chime_files.pdftoppm_path())
NEEDS_POPPLER = "pdftoppm (poppler-utils) is not installed here"
TALL_IMAGE_HEIGHT = 3 * chime_files.PAGE_HEIGHT_PX
TALL_IMAGE_WIDTH = 2 * chime_files.PAGE_HEIGHT_PX
SMALL_IMAGE_SIDE = 200
TWO_PAGES = 2
PDF_TEXT_AT_PT = 100           # where the test PDF writes its page number
LOADED_ORDER = 5


def png_bytes(width, height):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buf, format="PNG")
    return buf.getvalue()


def two_page_pdf_bytes():
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A4))
    for n in range(1, TWO_PAGES + 1):
        c.drawString(PDF_TEXT_AT_PT, PDF_TEXT_AT_PT, "page %d" % n)
        c.showPage()
    c.save()
    return buf.getvalue()


class ChimesRootMixin:
    """Every test gets its own empty chimes folder."""

    def setUp(self):
        super().setUp()
        self.root = tempfile.mkdtemp(prefix="chimes-test-")
        self.addCleanup(shutil.rmtree, self.root, True)
        patcher = override_settings(SANDBELLS_CHIMES_ROOT=self.root)
        patcher.enable()
        self.addCleanup(patcher.disable)

    def make_tune(self, title, data, name, **kw):
        return ChimeTune.objects.create(
            title=title, source=SimpleUploadedFile(name, data), **kw)


class ChimeStorageTests(ChimesRootMixin, TestCase):
    def test_root_follows_the_setting(self):
        self.assertEqual(chime_files.chimes_root(), Path(self.root))
        self.assertEqual(chime_files.chime_storage.location, str(Path(self.root).resolve()))

    def test_default_root_is_under_base_dir_media(self):
        with override_settings(SANDBELLS_CHIMES_ROOT=None):
            self.assertEqual(chime_files.chimes_root().parts[-2:], chime_files.CHIMES_DEFAULT_SUBDIR)

    def test_source_kind(self):
        self.assertEqual(chime_files.source_kind("a.PDF"), "pdf")
        self.assertEqual(chime_files.source_kind("a.jpeg"), "image")
        self.assertEqual(chime_files.source_kind("a.docx"), "")


class ChimeImageTuneTests(ChimesRootMixin, TestCase):
    def test_a_tall_image_becomes_one_page_at_screen_height(self):
        t = self.make_tune("Tall", png_bytes(TALL_IMAGE_WIDTH, TALL_IMAGE_HEIGHT), "tall.png")
        self.assertEqual(t.page_count, 1)
        page = t.pages.get()
        self.assertEqual(page.height, chime_files.PAGE_HEIGHT_PX)
        self.assertEqual(page.width, round(TALL_IMAGE_WIDTH * chime_files.PAGE_HEIGHT_PX
                                           / TALL_IMAGE_HEIGHT))
        self.assertTrue((Path(self.root) / page.image.name).is_file())
        self.assertEqual(t.render_error, "")

    def test_a_small_image_is_not_enlarged(self):
        t = self.make_tune("Small", png_bytes(SMALL_IMAGE_SIDE, SMALL_IMAGE_SIDE), "s.png")
        self.assertEqual(t.pages.get().height, SMALL_IMAGE_SIDE)

    def test_saving_again_does_not_remake_the_pages(self):
        t = self.make_tune("Same", png_bytes(SMALL_IMAGE_SIDE, SMALL_IMAGE_SIDE), "s.png")
        first = t.rendered
        t.notes = "changed"
        t.save()
        t.refresh_from_db()
        self.assertEqual(t.rendered, first)
        self.assertFalse(t.render_pages())
        self.assertTrue(t.render_pages(force=True))

    def test_slug_is_made_from_the_title_and_kept_unique(self):
        a = self.make_tune("Boar's Head", png_bytes(SMALL_IMAGE_SIDE, SMALL_IMAGE_SIDE), "a.png")
        b = self.make_tune("Boar's Head", png_bytes(SMALL_IMAGE_SIDE, SMALL_IMAGE_SIDE), "b.png")
        self.assertEqual(a.slug, "boars-head")
        self.assertEqual(b.slug, "boars-head-2")

    def test_a_broken_image_fails_clearly_and_keeps_why(self):
        with self.assertRaises(chime_files.ChimeRenderError):
            self.make_tune("Broken", b"not an image", "x.png")
        t = ChimeTune.objects.get(title="Broken")
        self.assertIn("not an image", t.render_error)
        self.assertEqual(t.page_count, 0)

    def test_deleting_a_tune_removes_its_files(self):
        t = self.make_tune("Gone", png_bytes(SMALL_IMAGE_SIDE, SMALL_IMAGE_SIDE), "g.png")
        source, pages_dir = Path(t.source.path), t.pages_dir()
        self.assertTrue(source.is_file() and pages_dir.is_dir())
        ChimeTune.objects.filter(pk=t.pk).delete()      # the admin's bulk delete path
        self.assertFalse(source.exists())
        self.assertFalse(pages_dir.exists())
        self.assertEqual(ChimePage.objects.count(), 0)


@mock.patch("bells.chimes.pdftoppm_path", return_value=None)
class ChimeNoPopplerTests(ChimesRootMixin, TestCase):
    def test_render_says_install_poppler(self, _which):
        with self.assertRaises(chime_files.ChimeRenderError) as cm:
            self.make_tune("Carol", SAMPLE_FILE.read_bytes(), "carol.pdf")
        self.assertIn(chime_files.POPPLER_PACKAGE, str(cm.exception))
        self.assertIn(chime_files.POPPLER_PACKAGE, ChimeTune.objects.get().render_error)

    def test_admin_form_refuses_a_pdf(self, _which):
        form = ChimeTuneForm(
            data={"title": "Carol", "order": 1, "enable": "on"},
            files={"source": SimpleUploadedFile("carol.pdf", SAMPLE_FILE.read_bytes())})
        self.assertFalse(form.is_valid())
        self.assertIn(chime_files.POPPLER_PACKAGE, str(form.errors["source"]))

    def test_admin_form_still_takes_an_image(self, _which):
        form = ChimeTuneForm(
            data={"title": "Pic", "order": 1, "enable": "on"},
            files={"source": SimpleUploadedFile(
                "p.png", png_bytes(SMALL_IMAGE_SIDE, SMALL_IMAGE_SIDE))})
        self.assertTrue(form.is_valid(), form.errors)

    def test_load_command_fails_clearly(self, _which):
        with self.assertRaises(CommandError) as cm:
            call_command("chime_load", stdout=io.StringIO())
        self.assertIn(chime_files.POPPLER_PACKAGE, str(cm.exception))


class ChimeAdminFormTests(ChimesRootMixin, TestCase):
    def test_other_files_are_refused(self):
        form = ChimeTuneForm(data={"title": "Doc", "order": 1},
                             files={"source": SimpleUploadedFile("tune.docx", b"x")})
        self.assertFalse(form.is_valid())
        self.assertIn("source", form.errors)


needs_poppler = unittest.skipUnless(HAVE_POPPLER, NEEDS_POPPLER)


@needs_poppler
class ChimePdfTuneTests(ChimesRootMixin, TestCase):
    def test_the_sample_pdf_is_one_page_at_screen_height(self):
        t = self.make_tune("Carol", SAMPLE_FILE.read_bytes(), "carol.pdf")
        self.assertEqual(t.page_count, 1)
        page = t.pages.get()
        self.assertEqual(page.height, chime_files.PAGE_HEIGHT_PX)
        self.assertGreater(page.width, page.height)          # A4 landscape
        with Image.open(Path(self.root) / page.image.name) as im:
            self.assertEqual(im.format, chime_files.PAGE_IMAGE_FORMAT.upper())

    def test_a_two_page_pdf_makes_two_pages_in_order(self):
        t = self.make_tune("Two", two_page_pdf_bytes(), "two.pdf")
        self.assertEqual(t.page_count, TWO_PAGES)
        self.assertEqual(list(t.pages.values_list("number", flat=True)), [1, 2])
        names = [Path(p.image.name).name for p in t.pages.all()]
        self.assertEqual(names, [chime_files.PAGE_FILE_TEMPLATE.format(number=n)
                                 for n in (1, 2)])

    def test_replacing_the_source_remakes_the_pages_and_drops_the_old_file(self):
        t = self.make_tune("Swap", two_page_pdf_bytes(), "two.pdf")
        old = Path(t.source.path)
        t.source = SimpleUploadedFile("one.png", png_bytes(SMALL_IMAGE_SIDE, SMALL_IMAGE_SIDE))
        t.save()
        self.assertEqual(t.page_count, 1)
        self.assertEqual(t.pages.count(), 1)
        self.assertFalse(old.exists())
        self.assertEqual(len(list(t.pages_dir().glob("page-*.png"))), 1)

    def test_load_command_loads_the_sample_once(self):
        out = io.StringIO()
        call_command("chime_load", stdout=out)
        call_command("chime_load", stdout=out)
        t = ChimeTune.objects.get()
        self.assertEqual(t.title, SAMPLE_TITLE)
        self.assertEqual(t.page_count, 1)
        self.assertIn("added", out.getvalue())
        self.assertIn("updated", out.getvalue())
        self.assertEqual(len(list((Path(self.root) / chime_files.SOURCES_DIR).iterdir())), 1)

    def test_load_command_takes_a_title_from_the_pdf(self):
        path = Path(self.root) / "carol-copy.pdf"
        path.write_bytes(SAMPLE_FILE.read_bytes())
        call_command("chime_load", str(path), "--order", str(LOADED_ORDER), stdout=io.StringIO())
        t = ChimeTune.objects.get()
        self.assertEqual(t.title, SAMPLE_TITLE)          # the PDF's own Title
        self.assertEqual(t.order, LOADED_ORDER)


@needs_poppler
class ChimePageViewTests(ChimesRootMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.two = self.make_tune("Two", two_page_pdf_bytes(), "two.pdf", order=2)
        self.one = self.make_tune("Carol", SAMPLE_FILE.read_bytes(), "carol.pdf", order=1)
        self.hidden = self.make_tune("Hidden", png_bytes(SMALL_IMAGE_SIDE, SMALL_IMAGE_SIDE),
                                     "h.png", enable=False)

    def test_chimes_shows_the_menu_in_order_and_the_first_tune(self):
        r = self.client.get(reverse("chimes"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual([t.title for t in r.context["tunes"]], ["Carol", "Two"])
        self.assertEqual(r.context["tune"], self.one)
        self.assertContains(r, reverse("chime_image", args=[self.one.slug, 1]))
        self.assertNotContains(r, "Hidden")
        self.assertContains(r, 'class="navbtn chimes on"')

    def test_page_two_has_previous_and_no_next(self):
        r = self.client.get(reverse("chime_page", args=[self.two.slug, 2]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["prev_url"], reverse("chime_page", args=[self.two.slug, 1]))
        self.assertEqual(r.context["next_url"], "")
        self.assertContains(r, 'id="chimes-prev"')
        self.assertContains(r, "2 / 2")

    def test_page_one_has_next(self):
        r = self.client.get(reverse("chime_tune", args=[self.two.slug]))
        self.assertEqual(r.context["next_url"], reverse("chime_page", args=[self.two.slug, 2]))
        self.assertEqual(r.context["prev_url"], "")

    def test_one_page_tune_has_no_pager(self):
        r = self.client.get(reverse("chime_tune", args=[self.one.slug]))
        self.assertNotContains(r, 'id="chimes-pager"')

    def test_full_screen_page(self):
        r = self.client.get(reverse("chime_full", args=[self.two.slug, 1]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'id="chime-full-image"')
        self.assertContains(r, reverse("chime_full", args=[self.two.slug, 2]))
        self.assertContains(r, reverse("chime_page", args=[self.two.slug, 1]))

    def test_image_is_a_cacheable_png(self):
        r = self.client.get(reverse("chime_image", args=[self.one.slug, 1]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "image/png")
        self.assertIn("max-age=%d" % chime_files.IMAGE_CACHE_SECONDS, r["Cache-Control"])
        self.assertEqual(b"".join(r.streaming_content)[:4], b"\x89PNG")

    def test_unknown_or_hidden_tune_or_page_is_404(self):
        self.assertEqual(self.client.get(reverse("chime_tune", args=["nope"])).status_code, 404)
        self.assertEqual(self.client.get(
            reverse("chime_tune", args=[self.hidden.slug])).status_code, 404)
        self.assertEqual(self.client.get(
            reverse("chime_page", args=[self.one.slug, 2])).status_code, 404)

    def test_missing_image_file_is_404(self):
        page = self.one.pages.get()
        (Path(self.root) / page.image.name).unlink()
        r = self.client.get(reverse("chime_image", args=[self.one.slug, 1]))
        self.assertEqual(r.status_code, 404)

    def test_admin_lists_and_edits_tunes(self):
        User.objects.create_superuser("admin", "a@example.invalid", "pw-for-tests-only")
        self.client.login(username="admin", password="pw-for-tests-only")
        r = self.client.get(reverse("admin:bells_chimetune_changelist"))
        self.assertContains(r, "Carol")
        r = self.client.get(reverse("admin:bells_chimetune_change", args=[self.two.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, reverse("chime_page", args=[self.two.slug, 2]))


class ChimeEmptyAndMenuTests(ChimesRootMixin, TestCase):
    def test_no_tunes_says_how_to_add_one(self):
        r = self.client.get(reverse("chimes"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'id="chimes-empty"')

    def test_shared_top_line_has_chimes(self):
        r = self.client.get(reverse("events:days"))
        self.assertContains(r, 'href="%s">Chimes</a>' % reverse("chimes"))
        self.assertNotContains(r, 'class="navbtn chimes on"')

    def test_home_left_column_links_to_chimes(self):
        r = self.client.get(reverse("home"))
        self.assertContains(r, 'id="home-chimes"')
        self.assertContains(r, 'href="%s"' % reverse("chimes"))
