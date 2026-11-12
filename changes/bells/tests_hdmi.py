"""HDMI settings, boot-file apply (temp dirs only — never /boot), and the
status page's requested / actual report."""

from __future__ import annotations

import io
import json
import os
import tempfile
from pathlib import Path
from unittest import mock

from django.test import RequestFactory, SimpleTestCase, override_settings

from bells import hdmi
from bells.app_settings import display_settings
from bells.status_schema import from_sandbells_flat


REPO = Path(__file__).resolve().parents[2]
REAL_BOOT_MARKERS = ("/boot/firmware", "/boot/config.txt", "/boot/cmdline.txt")


def _settings(hdmi_block, extra=None):
    data = {
        "networks": [{"ssid": "TestNet", "psk": "supersecret-psk"}],
        "display": {"random_bells": 6, "hdmi": hdmi_block} if hdmi_block is not None else {"random_bells": 6},
    }
    if extra:
        data.update(extra)
    return data


def _write_json(path: Path, obj) -> Path:
    path.write_text(json.dumps(obj), encoding="utf-8")
    return path


def _boot_tree(config: str, cmdline: str = "console=serial0,115200 root=PARTUUID=abc rootwait quiet\n"):
    root = Path(tempfile.mkdtemp())
    boot = root / "boot"
    boot.mkdir()
    (boot / "config.txt").write_text(config)
    (boot / "cmdline.txt").write_text(cmdline)
    edid_dir = root / "fw" / "edid"
    edid_dir.mkdir(parents=True)
    state = root / "hdmi-applied.json"
    return root, boot, edid_dir, state


KMS_CONFIG = "arm_64bit=1\ndtoverlay=vc4-kms-v3d\nhdmi_blanking=1\n"
FKMS_CONFIG = "arm_64bit=1\ndtoverlay=vc4-fkms-v3d\n"
LEGACY_CONFIG = "# no display overlay\narm_64bit=1\n"
COMMENTED_KMS = "# dtoverlay=vc4-kms-v3d\narm_64bit=1\n"


class ParseHdmiSettingsTests(SimpleTestCase):
    def test_omitted_is_auto(self):
        r = hdmi.parse_hdmi_settings(None)
        self.assertEqual(r.mode, hdmi.HDMI_MODE_AUTO)
        self.assertFalse(r.is_force)
        self.assertEqual(r.requested_label, hdmi.REQUESTED_AUTO_LABEL)
        self.assertIsNone(r.error)

    def test_empty_object_is_auto(self):
        r = hdmi.parse_hdmi_settings({})
        self.assertEqual(r.mode, hdmi.HDMI_MODE_AUTO)

    def test_force_defaults_to_1080p60(self):
        r = hdmi.parse_hdmi_settings({"mode": "force"})
        self.assertTrue(r.is_force)
        self.assertEqual((r.width, r.height, r.refresh), (1920, 1080, 60))
        self.assertEqual(r.connector, "HDMI-A-1")
        self.assertEqual(r.requested_label, "1920x1080@60 (forced)")

    def test_explicit_is_force_alias(self):
        r = hdmi.parse_hdmi_settings({
            "mode": "explicit", "width": 1280, "height": 720, "refresh": 50,
        })
        self.assertTrue(r.is_force)
        self.assertEqual((r.width, r.height, r.refresh), (1280, 720, 50))

    def test_custom_connector(self):
        r = hdmi.parse_hdmi_settings({"mode": "force", "connector": "HDMI-A-2"})
        self.assertEqual(r.connector, "HDMI-A-2")

    def test_bad_mode(self):
        r = hdmi.parse_hdmi_settings({"mode": "please"})
        self.assertTrue(r.error)
        self.assertFalse(r.is_force)
        self.assertIn("mode", r.error)

    def test_bad_width_rejected(self):
        for w in (-1, 0, 16, 99999, "foo", 1920.5, True):
            r = hdmi.parse_hdmi_settings({"mode": "force", "width": w})
            self.assertTrue(r.error, msg=w)
            self.assertFalse(r.is_force)

    def test_bad_refresh_rejected(self):
        for v in (0, 10, 1000, "slow"):
            r = hdmi.parse_hdmi_settings({"mode": "force", "refresh": v})
            self.assertTrue(r.error, msg=v)

    def test_not_an_object(self):
        r = hdmi.parse_hdmi_settings(["force"])
        self.assertTrue(r.error)

    def test_from_settings_obj_reads_display_hdmi(self):
        r = hdmi.hdmi_from_settings_obj(_settings({"mode": "force"}))
        self.assertTrue(r.is_force)
        r = hdmi.hdmi_from_settings_obj({"display": {}})
        self.assertEqual(r.mode, hdmi.HDMI_MODE_AUTO)
        r = hdmi.hdmi_from_settings_obj("nope")
        self.assertEqual(r.mode, hdmi.HDMI_MODE_AUTO)

    def test_unreadable_settings_file(self):
        r = hdmi.load_hdmi_request(Path("/no/such/settings.json"))
        self.assertEqual(r.mode, hdmi.HDMI_MODE_AUTO)
        p = Path(tempfile.mkdtemp()) / "bad.json"
        p.write_text("{not json")
        r = hdmi.load_hdmi_request(p)
        self.assertTrue(r.error)


class EdidTests(SimpleTestCase):
    def test_1080p60_checksum_name_and_refresh(self):
        block = hdmi.build_edid(1920, 1080, 60)
        self.assertEqual(len(block), hdmi.EDID_LENGTH)
        self.assertEqual(block[:8], hdmi.EDID_HEADER)
        self.assertEqual(sum(block) & 0xFF, 0)
        self.assertEqual(hdmi.parse_edid_name(block), hdmi.EDID_MONITOR_NAME)
        self.assertEqual(hdmi.refresh_from_edid(block, 1920, 1080), 60)

    def test_no_edid(self):
        self.assertIsNone(hdmi.parse_edid_name(None))
        self.assertIsNone(hdmi.parse_edid_name(b""))
        self.assertIsNone(hdmi.parse_edid_name(b"\x00" * 128))
        self.assertFalse(hdmi.edid_is_present(None))
        self.assertFalse(hdmi.edid_is_present(b"\x00" * 128))
        self.assertFalse(hdmi.edid_is_present(b"\xff" * 16))

    def test_bad_checksum_not_trusted(self):
        block = bytearray(hdmi.build_edid(1920, 1080, 60))
        block[127] ^= 0xFF
        self.assertIsNone(hdmi.parse_edid_name(bytes(block)))


class DetectDriverTests(SimpleTestCase):
    def test_kms(self):
        self.assertEqual(hdmi.detect_driver(KMS_CONFIG), hdmi.DRIVER_KMS)

    def test_fkms(self):
        self.assertEqual(hdmi.detect_driver(FKMS_CONFIG), hdmi.DRIVER_FKMS)

    def test_legacy(self):
        self.assertEqual(hdmi.detect_driver(LEGACY_CONFIG), hdmi.DRIVER_LEGACY)

    def test_commented_overlay_is_legacy(self):
        self.assertEqual(hdmi.detect_driver(COMMENTED_KMS), hdmi.DRIVER_LEGACY)

    def test_missing_config_with_drm_assumes_kms(self):
        self.assertEqual(hdmi.detect_driver(None, drm_has_hdmi=True), hdmi.DRIVER_KMS)

    def test_kms_overlay_with_params(self):
        self.assertEqual(
            hdmi.detect_driver("dtoverlay=vc4-kms-v3d,noaudio\n"),
            hdmi.DRIVER_KMS,
        )


class ApplyTests(SimpleTestCase):
    def setUp(self):
        self.force = hdmi.parse_hdmi_settings({
            "mode": "force", "width": 1920, "height": 1080, "refresh": 60,
        })
        self.auto = hdmi.parse_hdmi_settings({"mode": "auto"})

    def _apply(self, config, request=None, cmdline=None, dry_run=False):
        root, boot, edid_dir, state = _boot_tree(
            config,
            cmdline if cmdline is not None else "console=serial0,115200 root=PARTUUID=abc rootwait quiet\n",
        )
        self.assertFalse(any(str(boot).startswith(m) for m in ("/boot/", "/boot")))
        result = hdmi.apply_hdmi(
            request or self.force,
            config_txt=boot / "config.txt",
            cmdline_txt=boot / "cmdline.txt",
            edid_dir=edid_dir,
            state_path=state,
            dry_run=dry_run,
        )
        return result, boot, edid_dir, state, root

    def test_kms_writes_video_and_edid_keeps_other_args(self):
        result, boot, edid_dir, state, root = self._apply(KMS_CONFIG)
        self.assertTrue(result.ok)
        self.assertTrue(result.reboot_needed)
        self.assertEqual(result.driver, hdmi.DRIVER_KMS)
        cmd = (boot / "cmdline.txt").read_text()
        self.assertIn("video=HDMI-A-1:1920x1080@60D", cmd)
        self.assertIn("drm.edid_firmware=HDMI-A-1:edid/sandbells-1920x1080-60.bin", cmd)
        self.assertIn("console=serial0,115200", cmd)
        self.assertIn("root=PARTUUID=abc", cmd)
        self.assertTrue(cmd.endswith("\n"))
        self.assertEqual(cmd.count("\n"), 1)
        cfg = (boot / "config.txt").read_text()
        self.assertIn("hdmi_blanking=1", cfg)
        self.assertIn("dtoverlay=vc4-kms-v3d", cfg)
        self.assertNotIn(hdmi.CONFIG_BEGIN, cfg)
        blob = edid_dir / "sandbells-1920x1080-60.bin"
        self.assertTrue(blob.is_file())
        self.assertEqual(hdmi.parse_edid_name(blob.read_bytes()), "Sandbells")
        self.assertTrue(list(boot.glob("cmdline.txt.sandbells-hdmi.bak-*")))
        self.assertTrue((boot / ("cmdline.txt" + hdmi.ORIG_SUFFIX)).is_file())
        self.assertTrue(state.is_file())

    def test_legacy_writes_hdmi_group_mode_16_and_ignore_edid(self):
        result, boot, *_ = self._apply(LEGACY_CONFIG)
        self.assertTrue(result.ok)
        self.assertEqual(result.driver, hdmi.DRIVER_LEGACY)
        cfg = (boot / "config.txt").read_text()
        self.assertIn(hdmi.CONFIG_BEGIN, cfg)
        self.assertIn("hdmi_force_hotplug=1", cfg)
        self.assertIn(f"hdmi_ignore_edid={hdmi.HDMI_IGNORE_EDID_MAGIC}", cfg)
        self.assertIn(f"hdmi_group={hdmi.HDMI_GROUP_CEA}", cfg)
        self.assertIn(f"hdmi_mode={hdmi.CEA_MODES[(1920, 1080, 60)]}", cfg)
        self.assertIn(f"hdmi_drive={hdmi.HDMI_DRIVE_HDMI}", cfg)
        self.assertIn("video=HDMI-A-1:1920x1080@60D", (boot / "cmdline.txt").read_text())

    def test_fkms_uses_legacy_hdmi_options(self):
        result, boot, *_ = self._apply(FKMS_CONFIG)
        self.assertEqual(result.driver, hdmi.DRIVER_FKMS)
        self.assertIn("hdmi_force_hotplug=1", (boot / "config.txt").read_text())

    def test_unknown_mode_uses_cvt(self):
        req = hdmi.parse_hdmi_settings({
            "mode": "force", "width": 1600, "height": 900, "refresh": 60,
        })
        result, boot, *_ = self._apply(LEGACY_CONFIG, request=req)
        self.assertTrue(result.ok)
        cfg = (boot / "config.txt").read_text()
        self.assertIn(f"hdmi_mode={hdmi.HDMI_MODE_CVT_CUSTOM}", cfg)
        self.assertIn("hdmi_cvt=1600 900 60", cfg)

    def test_auto_removes_force_and_keeps_other_args(self):
        result, boot, edid_dir, state, root = self._apply(KMS_CONFIG)
        self.assertIn("video=HDMI-A-1", (boot / "cmdline.txt").read_text())
        result2, *_ = self._apply(
            (boot / "config.txt").read_text(),
            request=self.auto,
            cmdline=(boot / "cmdline.txt").read_text(),
        )
        # re-apply on a new tree: do it on the same files
        result2 = hdmi.apply_hdmi(
            self.auto,
            config_txt=boot / "config.txt",
            cmdline_txt=boot / "cmdline.txt",
            edid_dir=edid_dir,
            state_path=state,
        )
        self.assertTrue(result2.ok)
        self.assertTrue(result2.reboot_needed)
        cmd = (boot / "cmdline.txt").read_text()
        self.assertNotIn("video=", cmd)
        self.assertNotIn("drm.edid_firmware", cmd)
        self.assertIn("console=serial0,115200", cmd)
        self.assertIn("hdmi_blanking=1", (boot / "config.txt").read_text())

    def test_legacy_auto_removes_marked_block_only(self):
        result, boot, edid_dir, state, _ = self._apply(LEGACY_CONFIG)
        self.assertIn(hdmi.CONFIG_BEGIN, (boot / "config.txt").read_text())
        result2 = hdmi.apply_hdmi(
            self.auto,
            config_txt=boot / "config.txt",
            cmdline_txt=boot / "cmdline.txt",
            edid_dir=edid_dir,
            state_path=state,
        )
        self.assertTrue(result2.ok)
        cfg = (boot / "config.txt").read_text()
        self.assertNotIn(hdmi.CONFIG_BEGIN, cfg)
        self.assertNotIn("hdmi_force_hotplug", cfg)
        self.assertIn("arm_64bit=1", cfg)

    def test_idempotent_second_apply_needs_no_reboot(self):
        result, boot, edid_dir, state, _ = self._apply(KMS_CONFIG)
        cmd1 = (boot / "cmdline.txt").read_text()
        backups = list(boot.glob("cmdline.txt.sandbells-hdmi.bak-*"))
        result2 = hdmi.apply_hdmi(
            self.force,
            config_txt=boot / "config.txt",
            cmdline_txt=boot / "cmdline.txt",
            edid_dir=edid_dir,
            state_path=state,
        )
        self.assertTrue(result2.ok)
        self.assertFalse(result2.reboot_needed)
        self.assertFalse(result2.changed)
        self.assertEqual((boot / "cmdline.txt").read_text(), cmd1)
        self.assertEqual(list(boot.glob("cmdline.txt.sandbells-hdmi.bak-*")), backups)

    def test_empty_cmdline_refused(self):
        result, boot, *_ = self._apply(KMS_CONFIG, cmdline="\n")
        self.assertFalse(result.ok)
        self.assertIn("empty", result.error)
        self.assertEqual((boot / "cmdline.txt").read_text(), "\n")

    def test_missing_config_refused(self):
        root = Path(tempfile.mkdtemp())
        result = hdmi.apply_hdmi(
            self.force,
            config_txt=root / "no-config.txt",
            cmdline_txt=root / "no-cmdline.txt",
            edid_dir=root,
            state_path=root / "state.json",
        )
        self.assertFalse(result.ok)
        self.assertIn("not found", result.error)

    def test_invalid_request_refused(self):
        bad = hdmi.parse_hdmi_settings({"mode": "force", "width": -4})
        root, boot, edid_dir, state = _boot_tree(KMS_CONFIG)
        before = (boot / "cmdline.txt").read_text()
        result = hdmi.apply_hdmi(
            bad, config_txt=boot / "config.txt", cmdline_txt=boot / "cmdline.txt",
            edid_dir=edid_dir, state_path=state,
        )
        self.assertFalse(result.ok)
        self.assertEqual((boot / "cmdline.txt").read_text(), before)

    def test_dry_run_writes_nothing(self):
        result, boot, edid_dir, state, _ = self._apply(KMS_CONFIG, dry_run=True)
        self.assertTrue(result.ok)
        self.assertTrue(result.reboot_needed)
        self.assertNotIn("video=", (boot / "cmdline.txt").read_text())
        self.assertFalse(list(edid_dir.iterdir()))

    def test_report_has_no_wifi_secrets(self):
        result, *_ = self._apply(KMS_CONFIG)
        report = result.report()
        self.assertNotIn("supersecret", report)
        self.assertNotIn("psk", report.lower())
        self.assertNotIn("TestNet", report)
        self.assertIn("Reboot needed: yes", report)
        self.assertIn("1920x1080@60", report)

    def test_apply_does_not_touch_real_boot(self):
        # The temp tree is not /boot; this is the contract tests rely on.
        result, boot, *_ = self._apply(KMS_CONFIG)
        self.assertTrue(result.ok)
        self.assertFalse(str(boot).startswith("/boot"))
        self.assertNotEqual(boot, Path("/boot"))
        self.assertNotEqual(boot, Path("/boot/firmware"))

    def test_other_connector_video_is_kept(self):
        cmdline = "console=tty1 video=HDMI-A-2:1280x720@60D rootwait\n"
        result, boot, *_ = self._apply(KMS_CONFIG, cmdline=cmdline)
        cmd = (boot / "cmdline.txt").read_text()
        self.assertIn("video=HDMI-A-2:1280x720@60D", cmd)
        self.assertIn("video=HDMI-A-1:1920x1080@60D", cmd)

    def test_replaces_previous_video_for_same_connector(self):
        cmdline = "console=tty1 video=HDMI-A-1:640x480@60D rootwait\n"
        result, boot, *_ = self._apply(KMS_CONFIG, cmdline=cmdline)
        cmd = (boot / "cmdline.txt").read_text()
        self.assertIn("video=HDMI-A-1:1920x1080@60D", cmd)
        self.assertNotIn("640x480", cmd)


def _fake_drm(root: Path, name="HDMI-A-1", status="connected", mode="1920x1080@60",
              edid: bytes | None = None, modes="1920x1080\n"):
    conn = root / f"card0-{name}"
    conn.mkdir(parents=True, exist_ok=True)
    (conn / "status").write_text(status + "\n")
    (conn / "mode").write_text((mode + "\n") if mode else "")
    (conn / "modes").write_text(modes)
    if edid is not None:
        (conn / "edid").write_bytes(edid)
    return conn


class ReadConnectorsTests(SimpleTestCase):
    def test_connected_with_edid_name_and_refresh(self):
        root = Path(tempfile.mkdtemp())
        edid = hdmi.build_edid(1920, 1080, 60)
        _fake_drm(root, edid=edid, mode="1920x1080")
        st = hdmi.hdmi_status(hdmi.parse_hdmi_settings({"mode": "force"}), root)
        self.assertEqual(st["hdmi_requested"], "1920x1080@60 (forced)")
        self.assertEqual(st["hdmi_actual"], "1920x1080@60")  # refresh from EDID
        self.assertEqual(st["hdmi_connector"], "HDMI-A-1")
        self.assertEqual(st["hdmi_monitor"], "connected")
        self.assertEqual(st["hdmi_edid"], "Sandbells")
        self.assertFalse(st["hdmi_mismatch"])

    def test_no_edid_and_low_resolution_mismatch(self):
        root = Path(tempfile.mkdtemp())
        _fake_drm(root, mode="1024x768", edid=b"\x00" * 128, modes="1024x768\n")
        st = hdmi.hdmi_status(hdmi.parse_hdmi_settings({"mode": "force"}), root)
        self.assertEqual(st["hdmi_actual"], "1024x768")
        self.assertEqual(st["hdmi_edid"], hdmi.EDID_MISSING_LABEL)
        self.assertEqual(st["hdmi_monitor"], "connected")
        self.assertTrue(st["hdmi_mismatch"])

    def test_disconnected(self):
        root = Path(tempfile.mkdtemp())
        _fake_drm(root, status="disconnected", mode="", edid=b"")
        st = hdmi.hdmi_status(hdmi.parse_hdmi_settings({"mode": "auto"}), root)
        self.assertEqual(st["hdmi_monitor"], "disconnected")
        self.assertEqual(st["hdmi_edid"], hdmi.EDID_MISSING_LABEL)
        self.assertEqual(st["hdmi_actual"], "—")

    def test_missing_sysfs_is_safe(self):
        root = Path(tempfile.mkdtemp()) / "no-drm"
        st = hdmi.hdmi_status(hdmi.parse_hdmi_settings(None), root)
        self.assertEqual(st["hdmi_actual"], "—")
        self.assertEqual(st["hdmi_monitor"], "—")
        self.assertEqual(st["hdmi_edid"], hdmi.EDID_MISSING_LABEL)
        self.assertEqual(st["hdmi_requested"], hdmi.REQUESTED_AUTO_LABEL)
        self.assertFalse(st["hdmi_mismatch"])

    def test_unreadable_files_are_safe(self):
        # A connector dir with no files at all.
        root = Path(tempfile.mkdtemp())
        (root / "card0-HDMI-A-1").mkdir()
        st = hdmi.hdmi_status(hdmi.parse_hdmi_settings({"mode": "auto"}), root)
        self.assertEqual(st["hdmi_connector"], "HDMI-A-1")
        self.assertEqual(st["hdmi_actual"], "—")
        self.assertEqual(st["hdmi_edid"], hdmi.EDID_MISSING_LABEL)

    def test_apply_needed_when_cmdline_lacks_force(self):
        root = Path(tempfile.mkdtemp())
        _fake_drm(root, edid=hdmi.build_edid(1920, 1080, 60))
        st = hdmi.hdmi_status(
            hdmi.parse_hdmi_settings({"mode": "force"}),
            root,
            cmdline_text="console=tty1 rootwait\n",
        )
        self.assertTrue(st["hdmi_apply_needed"])

    def test_empty_status_helper(self):
        st = hdmi.empty_hdmi_status()
        self.assertEqual(st["hdmi_edid"], hdmi.EDID_MISSING_LABEL)
        self.assertEqual(st["hdmi_actual"], "—")


class DisplaySettingsTests(SimpleTestCase):
    def test_hdmi_is_included_from_settings_file(self):
        folder = Path(tempfile.mkdtemp())
        path = _write_json(folder / "settings.json", _settings({"mode": "force"}))
        with mock.patch.object(__import__("bells.app_settings", fromlist=["PATHS"]), "PATHS", (path,)):
            # Patch the module's PATHS directly.
            import bells.app_settings as app
            with mock.patch.object(app, "PATHS", (path,)):
                d = display_settings()
        self.assertEqual(d["hdmi"]["mode"], "force")
        self.assertEqual(d["hdmi"]["width"], 1920)
        self.assertEqual(d["hdmi"]["requested"], "1920x1080@60 (forced)")
        self.assertEqual(d["random_bells"], 6)

    def test_missing_hdmi_is_auto(self):
        folder = Path(tempfile.mkdtemp())
        path = _write_json(folder / "settings.json", _settings(None))
        import bells.app_settings as app
        with mock.patch.object(app, "PATHS", (path,)):
            d = display_settings()
        self.assertEqual(d["hdmi"]["mode"], "auto")
        self.assertEqual(d["hdmi"]["requested"], hdmi.REQUESTED_AUTO_LABEL)

    def test_invalid_hdmi_does_not_crash(self):
        folder = Path(tempfile.mkdtemp())
        path = _write_json(folder / "settings.json", _settings({"mode": "force", "width": "wide"}))
        import bells.app_settings as app
        with mock.patch.object(app, "PATHS", (path,)):
            d = display_settings()
        self.assertTrue(d["hdmi"]["error"])
        self.assertEqual(d["hdmi"]["mode"], "auto")


class StatusSchemaTests(SimpleTestCase):
    def _items(self, payload):
        doc = from_sandbells_flat(payload)
        display = next(s for s in doc["sections"] if s["id"] == "display")
        return {it["key"]: it for it in display["items"]}

    def test_hdmi_rows_on_the_display_section(self):
        items = self._items({
            "hostname": "sandbells",
            "hdmi_requested": "1920x1080@60 (forced)",
            "hdmi_actual": "1024x768",
            "hdmi_connector": "HDMI-A-1",
            "hdmi_monitor": "connected",
            "hdmi_edid": "no EDID",
            "hdmi_mismatch": True,
        })
        self.assertEqual(items["hdmi_requested"]["value"], "1920x1080@60 (forced)")
        self.assertEqual(items["hdmi_actual"]["value"], "1024x768")
        self.assertEqual(items["hdmi_actual"]["level"], "warn")
        self.assertEqual(items["hdmi_connector"]["value"], "HDMI-A-1")
        self.assertEqual(items["hdmi_monitor"]["value"], "connected")
        self.assertEqual(items["hdmi_edid"]["value"], "no EDID")
        self.assertEqual(items["hdmi_edid"]["level"], "warn")
        # existing display rows still there
        self.assertIn("bells", items)
        self.assertIn("pattern_mode", items)

    def test_matching_force_is_ok(self):
        items = self._items({
            "hdmi_requested": "1920x1080@60 (forced)",
            "hdmi_actual": "1920x1080@60",
            "hdmi_connector": "HDMI-A-1",
            "hdmi_monitor": "connected",
            "hdmi_edid": "Sandbells",
            "hdmi_mismatch": False,
        })
        self.assertNotEqual(items["hdmi_actual"].get("level"), "warn")
        self.assertNotEqual(items["hdmi_edid"].get("level"), "warn")

    def test_dashes_when_keys_missing(self):
        items = self._items({"hostname": "sandbells"})
        self.assertEqual(items["hdmi_requested"]["value"], "—")
        self.assertEqual(items["hdmi_actual"]["value"], "—")
        self.assertEqual(items["hdmi_edid"]["value"], "—")

    def test_apply_needed_is_a_warning(self):
        items = self._items({
            "hdmi_requested": "1920x1080@60 (forced)",
            "hdmi_actual": "1024x768",
            "hdmi_connector": "HDMI-A-1",
            "hdmi_monitor": "connected",
            "hdmi_edid": "no EDID",
            "hdmi_apply_needed": True,
        })
        self.assertEqual(items["hdmi_apply"]["value"], "needed — run sudo sandbells-hdmi apply")
        self.assertEqual(items["hdmi_apply"]["level"], "warn")

    def test_labels_are_the_diagnostic_ones(self):
        items = self._items({
            "hdmi_requested": "a", "hdmi_actual": "b",
            "hdmi_connector": "c", "hdmi_monitor": "d", "hdmi_edid": "e",
        })
        self.assertEqual(items["hdmi_requested"]["label"], "HDMI requested")
        self.assertEqual(items["hdmi_actual"]["label"], "HDMI actual")
        self.assertEqual(items["hdmi_connector"]["label"], "HDMI connector")
        self.assertEqual(items["hdmi_monitor"]["label"], "HDMI monitor")
        self.assertEqual(items["hdmi_edid"]["label"], "HDMI EDID")


class SystemStatusViewTests(SimpleTestCase):
    """The API exposes HDMI facts; a missing drm tree is safe."""

    def test_payload_includes_hdmi_keys(self):
        from bells import status_views

        drm = Path(tempfile.mkdtemp()) / "drm"
        _fake_drm(drm, mode="1024x768", edid=b"\x00" * 128)
        folder = Path(tempfile.mkdtemp())
        settings = _write_json(folder / "settings.json", _settings({"mode": "force"}))
        import bells.app_settings as app
        with mock.patch.object(app, "PATHS", (settings,)), \
             mock.patch.object(status_views, "_hdmi_drm_root", return_value=drm), \
             mock.patch.object(status_views, "_hdmi_cmdline_path", return_value=None), \
             mock.patch.object(status_views, "_hdmi_state_path", return_value=None):
            response = status_views.system_status(RequestFactory().get("/api/system-status/"))
        data = json.loads(response.content)
        # wrap_document copies flat keys onto the v1 document
        self.assertEqual(data.get("hdmi_requested") or _legacy(data, "hdmi_requested"),
                         "1920x1080@60 (forced)")
        self.assertEqual(data.get("hdmi_actual") or _legacy(data, "hdmi_actual"), "1024x768")
        self.assertEqual(data.get("hdmi_edid") or _legacy(data, "hdmi_edid"), "no EDID")
        self.assertEqual(data.get("hdmi_monitor") or _legacy(data, "hdmi_monitor"), "connected")
        display = next(s for s in data["sections"] if s["id"] == "display")
        keys = {it["key"] for it in display["items"]}
        self.assertTrue({"hdmi_requested", "hdmi_actual", "hdmi_connector",
                         "hdmi_monitor", "hdmi_edid"} <= keys)

    def test_missing_drm_does_not_500(self):
        from bells import status_views

        import bells.app_settings as app
        folder = Path(tempfile.mkdtemp())
        settings = _write_json(folder / "settings.json", _settings(None))
        with mock.patch.object(app, "PATHS", (settings,)), \
             mock.patch.object(status_views, "_hdmi_drm_root", return_value=Path("/no/such/drm")), \
             mock.patch.object(status_views, "_hdmi_cmdline_path", return_value=None), \
             mock.patch.object(status_views, "_hdmi_state_path", return_value=None):
            response = status_views.system_status(RequestFactory().get("/api/system-status/"))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data.get("hdmi_edid") or _legacy(data, "hdmi_edid"), "no EDID")


def _legacy(data, key):
    return (data.get("legacy") or {}).get(key)


class CliTests(SimpleTestCase):
    def test_apply_and_status_via_cli(self):
        root, boot, edid_dir, state = _boot_tree(KMS_CONFIG)
        settings = _write_json(root / "settings.json", _settings({"mode": "force"}))
        drm = root / "drm"
        _fake_drm(drm, mode="1024x768", edid=b"")
        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            rc = hdmi.main([
                "--settings", str(settings),
                "--boot", str(boot),
                "--firmware-dir", str(edid_dir.parent),
                "--state", str(state),
                "--drm", str(drm),
                "apply",
            ])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("Reboot needed: yes", out)
        self.assertNotIn("supersecret", out)
        self.assertNotIn("TestNet", out)
        self.assertNotIn("psk", out.lower())
        buf2 = io.StringIO()
        with mock.patch("sys.stdout", buf2):
            rc = hdmi.main([
                "--settings", str(settings),
                "--boot", str(boot),
                "--firmware-dir", str(edid_dir.parent),
                "--state", str(state),
                "--drm", str(drm),
                "status",
            ])
        self.assertEqual(rc, 0)
        out = buf2.getvalue()
        self.assertIn("Requested: 1920x1080@60 (forced)", out)
        self.assertIn("Actual:    1024x768", out)
        self.assertIn("EDID:      no EDID", out)
        self.assertIn("Monitor:   connected", out)
        self.assertNotIn("supersecret", out)
