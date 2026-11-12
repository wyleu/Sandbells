#!/usr/bin/env python3
"""Sandbells HDMI mode: parse settings, apply a forced boot mode, read the
actual connector at runtime.

Stdlib only.  Safe to install as /usr/local/sbin/sandbells-hdmi and safe
to import from Django (no Django imports here).

Never prints Wi-Fi credentials.  Never writes /etc/sandbells/settings.json.
The library never defaults to /boot: the caller passes every path.  The
CLI resolves the Pi's boot files; tests pass a temporary directory.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants (no magic numbers at the call sites)
# ---------------------------------------------------------------------------

HDMI_MODE_AUTO = "auto"
HDMI_MODE_FORCE = "force"
HDMI_MODE_EXPLICIT = "explicit"  # accepted alias of force (5 Nov handover name)

HDMI_DEFAULT_WIDTH = 1920
HDMI_DEFAULT_HEIGHT = 1080
HDMI_DEFAULT_REFRESH = 60
HDMI_DEFAULT_CONNECTOR = "HDMI-A-1"

HDMI_MIN_WIDTH = 640
HDMI_MAX_WIDTH = 7680
HDMI_MIN_HEIGHT = 480
HDMI_MAX_HEIGHT = 4320
HDMI_MIN_REFRESH = 24
HDMI_MAX_REFRESH = 240

# Raspberry Pi firmware requires this exact value for hdmi_ignore_edid
# (legacy / FKMS).  It is not a KMS option.
HDMI_IGNORE_EDID_MAGIC = "0xa5000080"

HDMI_GROUP_CEA = 1
HDMI_GROUP_DMT = 2
HDMI_MODE_CVT_CUSTOM = 87
HDMI_DRIVE_HDMI = 2  # HDMI (with audio), not DVI
HDMI_CVT_ASPECT_16_9 = 3
HDMI_CVT_MARGINS = 0
HDMI_CVT_PROGRESSIVE = 0
HDMI_CVT_REDUCED_BLANKING = 0

# CEA (hdmi_group=1) vic numbers from the Raspberry Pi config.txt docs.
CEA_MODES: dict[tuple[int, int, int], int] = {
    (640, 480, 60): 1,
    (720, 480, 60): 2,
    (720, 576, 50): 17,
    (1280, 720, 60): 4,
    (1280, 720, 50): 19,
    (1920, 1080, 60): 16,
    (1920, 1080, 50): 31,
    (1920, 1080, 24): 32,
    (1920, 1080, 25): 33,
    (1920, 1080, 30): 34,
}

# Precise CEA/VESA detailed-timing values for the canned EDID.
# (clock_khz, hfp, hsync, hbp, vfp, vsync, vbp, hsync_pos, vsync_pos)
CEA_TIMINGS: dict[tuple[int, int, int], tuple] = {
    (1920, 1080, 60): (148500, 88, 44, 148, 4, 5, 36, True, True),
    (1920, 1080, 50): (148500, 528, 44, 148, 4, 5, 36, True, True),
    (1280, 720, 60): (74250, 110, 40, 220, 5, 5, 20, True, True),
    (1280, 720, 50): (74250, 440, 40, 220, 5, 5, 20, True, True),
    (640, 480, 60): (25175, 16, 96, 48, 10, 2, 33, False, False),
}

# CVT-RB fallback when the mode is not in CEA_TIMINGS (for a valid EDID only).
CVT_RB_H_BLANK = 160
CVT_RB_H_FRONT = 48
CVT_RB_H_SYNC = 32
CVT_RB_H_BACK = 80
CVT_RB_V_FRONT = 3
CVT_RB_V_SYNC = 6
CVT_RB_V_MIN_BACK = 6
KHZ = 1000
MHZ_TO_EDID_UNITS = 100  # EDID pixel clock is in 10 kHz units (kHz / 10)

EDID_HEADER = bytes((0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00))
EDID_LENGTH = 128
EDID_VERSION = 1
EDID_REVISION = 3
EDID_DIGITAL_INPUT = 0x80
EDID_GAMMA_22 = 120  # (2.2 - 1) * 100
EDID_FEATURES_PREFERRED_DTD = 0x0A
EDID_MANUFACTURER = "SBL"
EDID_PRODUCT_CODE = 1
EDID_WEEK = 1
EDID_YEAR_OFFSET = 1990
EDID_YEAR = 2026
EDID_NAME_TAG = 0xFC
EDID_RANGE_TAG = 0xFD
EDID_DESCRIPTOR_PAYLOAD = 13
EDID_NAME_PAD = 0x0A
EDID_NAME_FILL = 0x20
EDID_NAME_MAX = 13
EDID_DISPLAY_WIDTH_CM = 48
EDID_DISPLAY_HEIGHT_CM = 27
EDID_WIDTH_MM = 480
EDID_HEIGHT_MM = 270
EDID_FIRMWARE_SUBDIR = "edid"
EDID_FILENAME_PREFIX = "sandbells-"
EDID_MONITOR_NAME = "Sandbells"

KMS_OVERLAY = "vc4-kms-v3d"
FKMS_OVERLAY = "vc4-fkms-v3d"
DRIVER_KMS = "kms"
DRIVER_FKMS = "fkms"
DRIVER_LEGACY = "legacy"

CONFIG_BEGIN = "# --- sandbells-hdmi begin ---"
CONFIG_END = "# --- sandbells-hdmi end ---"

BACKUP_TIME_FMT = "%Y%m%dT%H%M%S"
BACKUP_SUFFIX = ".sandbells-hdmi.bak"
ORIG_SUFFIX = ".sandbells-hdmi.orig"

DEFAULT_SETTINGS_PATH = Path("/etc/sandbells/settings.json")
DEFAULT_DRM_ROOT = Path("/sys/class/drm")
DEFAULT_FIRMWARE_DIR = Path("/lib/firmware")
DEFAULT_STATE_PATH = Path("/etc/sandbells/hdmi-applied.json")
BOOT_CANDIDATES = (Path("/boot/firmware"), Path("/boot"))

STATUS_CONNECTED = "connected"
STATUS_DISCONNECTED = "disconnected"
EDID_MISSING_LABEL = "no EDID"
MONITOR_UNKNOWN = "—"
ACTUAL_UNKNOWN = "—"
REQUESTED_AUTO_LABEL = "auto (negotiate)"
FORCE_LABEL_SUFFIX = " (forced)"

VIDEO_FORCE_FLAG = "D"  # kernel video= : force the connector on as digital
MODE_RE = re.compile(
    r"^(\d+)x(\d+)([ip])?(?:@(\d+(?:\.\d+)?))?",
    re.IGNORECASE,
)
CONNECTOR_DIR_RE = re.compile(r"^card\d+-(.+)$")
HDMI_CONNECTOR_RE = re.compile(r"HDMI", re.IGNORECASE)

SETTINGS_KEYS_NEVER_PRINTED = frozenset({"psk", "password", "token", "secret", "passwd"})

EMPTY_DASH = "—"


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@dataclass
class HdmiRequest:
    """Validated display.hdmi request.  error is set instead of raising."""

    mode: str = HDMI_MODE_AUTO
    width: int | None = None
    height: int | None = None
    refresh: int | None = None
    connector: str = HDMI_DEFAULT_CONNECTOR
    error: str | None = None

    @property
    def is_force(self) -> bool:
        return self.mode == HDMI_MODE_FORCE and not self.error

    @property
    def requested_label(self) -> str:
        if self.error:
            return f"invalid ({self.error})"
        if self.mode != HDMI_MODE_FORCE:
            return REQUESTED_AUTO_LABEL
        return (
            f"{self.width}x{self.height}@{self.refresh}{FORCE_LABEL_SUFFIX}"
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "mode": self.mode if not self.error else HDMI_MODE_AUTO,
            "connector": self.connector,
            "requested": self.requested_label,
            "error": self.error,
        }
        if self.width is not None:
            d["width"] = self.width
        if self.height is not None:
            d["height"] = self.height
        if self.refresh is not None:
            d["refresh"] = self.refresh
        return d


def _as_int(value: Any, name: str, lo: int, hi: int) -> int:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{name} must be an integer")
    if isinstance(value, float) and value != int(value):
        raise ValueError(f"{name} must be an integer")
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer") from None
    if n < lo or n > hi:
        raise ValueError(f"{name} must be between {lo} and {hi}")
    return n


def parse_hdmi_settings(hdmi: Any) -> HdmiRequest:
    """Parse a display.hdmi value (or None / omitted).  Never raises."""
    if hdmi is None or hdmi == "":
        return HdmiRequest()
    if not isinstance(hdmi, dict):
        return HdmiRequest(error="hdmi must be an object")
    raw_mode = str(hdmi.get("mode") or HDMI_MODE_AUTO).strip().lower()
    if raw_mode == HDMI_MODE_EXPLICIT:
        raw_mode = HDMI_MODE_FORCE
    if raw_mode not in (HDMI_MODE_AUTO, HDMI_MODE_FORCE):
        return HdmiRequest(error=f"mode must be '{HDMI_MODE_AUTO}' or '{HDMI_MODE_FORCE}'")
    connector = str(hdmi.get("connector") or HDMI_DEFAULT_CONNECTOR).strip() or HDMI_DEFAULT_CONNECTOR
    if raw_mode == HDMI_MODE_AUTO:
        # Dimensions are ignored in auto; still validate if present so a
        # mistype is visible on the status page before the user switches.
        try:
            if any(k in hdmi for k in ("width", "height", "refresh")):
                w = _as_int(hdmi.get("width", HDMI_DEFAULT_WIDTH), "width", HDMI_MIN_WIDTH, HDMI_MAX_WIDTH)
                h = _as_int(hdmi.get("height", HDMI_DEFAULT_HEIGHT), "height", HDMI_MIN_HEIGHT, HDMI_MAX_HEIGHT)
                r = _as_int(hdmi.get("refresh", HDMI_DEFAULT_REFRESH), "refresh", HDMI_MIN_REFRESH, HDMI_MAX_REFRESH)
                return HdmiRequest(mode=HDMI_MODE_AUTO, width=w, height=h, refresh=r, connector=connector)
        except ValueError as exc:
            return HdmiRequest(error=str(exc), connector=connector)
        return HdmiRequest(mode=HDMI_MODE_AUTO, connector=connector)
    try:
        width = _as_int(
            HDMI_DEFAULT_WIDTH if hdmi.get("width") is None else hdmi.get("width"),
            "width", HDMI_MIN_WIDTH, HDMI_MAX_WIDTH,
        )
        height = _as_int(
            HDMI_DEFAULT_HEIGHT if hdmi.get("height") is None else hdmi.get("height"),
            "height", HDMI_MIN_HEIGHT, HDMI_MAX_HEIGHT,
        )
        refresh = _as_int(
            HDMI_DEFAULT_REFRESH if hdmi.get("refresh") is None else hdmi.get("refresh"),
            "refresh", HDMI_MIN_REFRESH, HDMI_MAX_REFRESH,
        )
    except ValueError as exc:
        return HdmiRequest(error=str(exc), connector=connector)
    return HdmiRequest(
        mode=HDMI_MODE_FORCE,
        width=width,
        height=height,
        refresh=refresh,
        connector=connector,
    )


def hdmi_from_settings_obj(data: Any) -> HdmiRequest:
    """Read display.hdmi from a loaded settings object."""
    if not isinstance(data, dict):
        return HdmiRequest()
    display = data.get("display")
    if not isinstance(display, dict):
        return HdmiRequest()
    return parse_hdmi_settings(display.get("hdmi"))


def load_hdmi_request(settings_path: Path | None) -> HdmiRequest:
    if settings_path is None or not settings_path.is_file():
        return HdmiRequest()
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return HdmiRequest(error="settings file is not readable JSON")
    return hdmi_from_settings_obj(data)


# ---------------------------------------------------------------------------
# EDID
# ---------------------------------------------------------------------------

def _edid_manufacturer_id(letters: str) -> bytes:
    letters = letters.upper()
    a, b, c = (ord(ch) - ord("A") + 1 for ch in letters[:3])
    word = (a << 10) | (b << 5) | c
    return bytes((word >> 8, word & 0xFF))


def _edid_checksum(block: bytes) -> int:
    return (256 - (sum(block[: EDID_LENGTH - 1]) & 0xFF)) & 0xFF


def _dtd_bytes(
    clock_khz: int,
    h_active: int,
    hfp: int,
    hsync: int,
    hbp: int,
    v_active: int,
    vfp: int,
    vsync: int,
    vbp: int,
    hsync_pos: bool,
    vsync_pos: bool,
    width_mm: int = EDID_WIDTH_MM,
    height_mm: int = EDID_HEIGHT_MM,
) -> bytes:
    h_blank = hfp + hsync + hbp
    v_blank = vfp + vsync + vbp
    clock_units = clock_khz // 10  # 10 kHz
    b = bytearray(18)
    b[0] = clock_units & 0xFF
    b[1] = (clock_units >> 8) & 0xFF
    b[2] = h_active & 0xFF
    b[3] = h_blank & 0xFF
    b[4] = ((h_active >> 8) & 0x0F) << 4 | ((h_blank >> 8) & 0x0F)
    b[5] = v_active & 0xFF
    b[6] = v_blank & 0xFF
    b[7] = ((v_active >> 8) & 0x0F) << 4 | ((v_blank >> 8) & 0x0F)
    b[8] = hfp & 0xFF
    b[9] = hsync & 0xFF
    b[10] = ((vfp & 0x0F) << 4) | (vsync & 0x0F)
    b[11] = (
        ((hfp >> 8) & 0x03) << 6
        | ((hsync >> 8) & 0x03) << 4
        | ((vfp >> 8) & 0x03) << 2
        | ((vsync >> 8) & 0x03)
    )
    b[12] = width_mm & 0xFF
    b[13] = height_mm & 0xFF
    b[14] = ((width_mm >> 8) & 0x0F) << 4 | ((height_mm >> 8) & 0x0F)
    b[15] = 0
    b[16] = 0
    flags = 0x18  # digital separate sync
    if vsync_pos:
        flags |= 0x04
    if hsync_pos:
        flags |= 0x02
    b[17] = flags
    return bytes(b)


def _cvt_rb_timing(width: int, height: int, refresh: int) -> tuple:
    h_total = width + CVT_RB_H_BLANK
    v_blank = CVT_RB_V_FRONT + CVT_RB_V_SYNC + CVT_RB_V_MIN_BACK
    v_total = height + v_blank
    clock_khz = (h_total * v_total * refresh + (KHZ - 1)) // KHZ
    # Snap the clock so refresh is exact enough for a forced mode.
    return (
        clock_khz,
        CVT_RB_H_FRONT,
        CVT_RB_H_SYNC,
        CVT_RB_H_BACK,
        CVT_RB_V_FRONT,
        CVT_RB_V_SYNC,
        CVT_RB_V_MIN_BACK,
        True,
        False,
    )


def _timing_for(width: int, height: int, refresh: int) -> tuple:
    known = CEA_TIMINGS.get((width, height, refresh))
    if known:
        return known
    return _cvt_rb_timing(width, height, refresh)


def _descriptor_name(name: str) -> bytes:
    raw = name.encode("ascii", "replace")[: EDID_NAME_MAX - 1]
    payload = raw + bytes((EDID_NAME_PAD,))
    payload = payload + bytes((EDID_NAME_FILL,)) * (EDID_DESCRIPTOR_PAYLOAD - len(payload))
    return bytes((0, 0, 0, EDID_NAME_TAG, 0)) + payload


def _descriptor_range(refresh: int) -> bytes:
    lo = max(HDMI_MIN_REFRESH, refresh - 5)
    hi = min(HDMI_MAX_REFRESH, refresh + 5)
    # Vertical rates, horizontal kHz 15-80, pixel clock 17*10=170 MHz max, no extra timing.
    payload = bytes((lo, hi, 15, 80, 17, 0x00, 0x0A, 0x20, 0x20, 0x20, 0x20, 0x20, 0x20))
    return bytes((0, 0, 0, EDID_RANGE_TAG, 0)) + payload


def _descriptor_unused() -> bytes:
    return bytes(18)


def build_edid(width: int, height: int, refresh: int, name: str = EDID_MONITOR_NAME) -> bytes:
    """A 128-byte EDID 1.3 block advertising one preferred detailed timing."""
    clock_khz, hfp, hsw, hbp, vfp, vsw, vbp, hp, vp = _timing_for(width, height, refresh)
    block = bytearray(EDID_LENGTH)
    block[0:8] = EDID_HEADER
    block[8:10] = _edid_manufacturer_id(EDID_MANUFACTURER)
    block[10] = EDID_PRODUCT_CODE & 0xFF
    block[11] = (EDID_PRODUCT_CODE >> 8) & 0xFF
    block[16] = EDID_WEEK
    block[17] = EDID_YEAR - EDID_YEAR_OFFSET
    block[18] = EDID_VERSION
    block[19] = EDID_REVISION
    block[20] = EDID_DIGITAL_INPUT
    block[21] = EDID_DISPLAY_WIDTH_CM
    block[22] = EDID_DISPLAY_HEIGHT_CM
    block[23] = EDID_GAMMA_22
    block[24] = EDID_FEATURES_PREFERRED_DTD
    # Established / standard timings unused (00 / 0101).
    for i in range(38, 54, 2):
        block[i] = 0x01
        block[i + 1] = 0x01
    dtd = _dtd_bytes(clock_khz, width, hfp, hsw, hbp, height, vfp, vsw, vbp, hp, vp)
    block[54:72] = dtd
    block[72:90] = _descriptor_name(name)
    block[90:108] = _descriptor_range(refresh)
    block[108:126] = _descriptor_unused()
    block[126] = 0  # no extensions
    block[127] = _edid_checksum(block)
    return bytes(block)


def parse_edid_name(edid: bytes | None) -> str | None:
    """Monitor name from descriptor 0xFC, or None if there is no usable EDID."""
    if not edid or len(edid) < EDID_LENGTH:
        return None
    if edid[:8] != EDID_HEADER:
        return None
    if (sum(edid[:EDID_LENGTH]) & 0xFF) != 0:
        return None
    names: list[str] = []
    for offset in (54, 72, 90, 108):
        desc = edid[offset:offset + 18]
        if desc[0] == 0 and desc[1] == 0 and desc[2] == 0 and desc[3] == EDID_NAME_TAG:
            raw = bytes(b for b in desc[5:] if b != 0)
            text = raw.decode("ascii", "replace").split("\n")[0].strip()
            if text:
                names.append(text)
    return names[0] if names else None


def edid_is_present(edid: bytes | None) -> bool:
    if not edid:
        return False
    if all(b == 0 for b in edid):
        return False
    return len(edid) >= EDID_LENGTH and edid[:8] == EDID_HEADER


def refresh_from_edid(edid: bytes | None, width: int, height: int) -> int | None:
    """Refresh (Hz) of a detailed timing that matches width x height."""
    if not edid or len(edid) < EDID_LENGTH or edid[:8] != EDID_HEADER:
        return None
    for offset in (54, 72, 90, 108):
        desc = edid[offset:offset + 18]
        clock = desc[0] | (desc[1] << 8)
        if clock == 0:
            continue
        h_act = desc[2] | ((desc[4] >> 4) & 0x0F) << 8
        h_bl = desc[3] | (desc[4] & 0x0F) << 8
        v_act = desc[5] | ((desc[7] >> 4) & 0x0F) << 8
        v_bl = desc[6] | (desc[7] & 0x0F) << 8
        if h_act != width or v_act != height:
            continue
        h_total = h_act + h_bl
        v_total = v_act + v_bl
        if h_total <= 0 or v_total <= 0:
            continue
        # clock is in 10 kHz units → Hz = clock * 10000 / (h * v)
        hz = (clock * 10000) / (h_total * v_total)
        return int(round(hz))
    return None


def edid_filename(width: int, height: int, refresh: int) -> str:
    return f"{EDID_FILENAME_PREFIX}{width}x{height}-{refresh}.bin"


def edid_firmware_relpath(width: int, height: int, refresh: int) -> str:
    return f"{EDID_FIRMWARE_SUBDIR}/{edid_filename(width, height, refresh)}"


# ---------------------------------------------------------------------------
# Driver detection
# ---------------------------------------------------------------------------

def _active_overlays(config_text: str) -> list[str]:
    found: list[str] = []
    for raw in config_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("dtoverlay="):
            name = line.split("=", 1)[1].split(",", 1)[0].strip()
            if name:
                found.append(name)
    return found


def detect_driver(config_text: str | None, drm_has_hdmi: bool | None = None) -> str:
    """Return 'kms', 'fkms' or 'legacy'.

    Full KMS (vc4-kms-v3d, current Pi OS) ignores hdmi_* in config.txt;
    the kernel video= cmdline and an EDID firmware file are used instead.
    FKMS and the legacy firmware stack still honour hdmi_group / hdmi_mode.
    """
    if config_text:
        overlays = _active_overlays(config_text)
        if KMS_OVERLAY in overlays:
            return DRIVER_KMS
        if FKMS_OVERLAY in overlays:
            return DRIVER_FKMS
        return DRIVER_LEGACY
    if drm_has_hdmi:
        return DRIVER_KMS
    return DRIVER_LEGACY


# ---------------------------------------------------------------------------
# Runtime status from /sys/class/drm (fail-safe)
# ---------------------------------------------------------------------------

@dataclass
class ConnectorStatus:
    name: str
    connected: bool | None
    width: int | None = None
    height: int | None = None
    refresh: int | None = None
    edid_name: str | None = None
    edid_present: bool = False
    modes: list[str] = field(default_factory=list)
    raw_mode: str = ""
    raw_status: str = ""

    @property
    def actual_label(self) -> str:
        if self.width is None or self.height is None:
            return ACTUAL_UNKNOWN
        if self.refresh:
            return f"{self.width}x{self.height}@{self.refresh}"
        return f"{self.width}x{self.height}"

    @property
    def monitor_label(self) -> str:
        if self.connected is None:
            return MONITOR_UNKNOWN
        return STATUS_CONNECTED if self.connected else STATUS_DISCONNECTED

    @property
    def edid_label(self) -> str:
        if self.edid_present and self.edid_name:
            return self.edid_name
        if self.edid_present and not self.edid_name:
            return "EDID (no name)"
        return EDID_MISSING_LABEL


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        return ""


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except Exception:
        return b""


def _parse_mode_string(text: str) -> tuple[int | None, int | None, int | None]:
    text = (text or "").strip().splitlines()[0].strip() if text else ""
    if not text:
        return None, None, None
    m = MODE_RE.match(text)
    if not m:
        return None, None, None
    width = int(m.group(1))
    height = int(m.group(2))
    refresh = int(round(float(m.group(4)))) if m.group(4) else None
    return width, height, refresh


def read_connector(conn_dir: Path) -> ConnectorStatus | None:
    """Read one /sys/class/drm/cardN-CONNECTOR directory.  Fail-safe."""
    try:
        if not conn_dir.is_dir():
            return None
        m = CONNECTOR_DIR_RE.match(conn_dir.name)
        if not m:
            return None
        name = m.group(1)
        raw_status = _read_text(conn_dir / "status").lower()
        if raw_status == STATUS_CONNECTED:
            connected: bool | None = True
        elif raw_status == STATUS_DISCONNECTED:
            connected = False
        else:
            connected = None
        raw_mode = _read_text(conn_dir / "mode")
        width, height, refresh = _parse_mode_string(raw_mode)
        modes_text = _read_text(conn_dir / "modes")
        modes = [ln.strip() for ln in modes_text.splitlines() if ln.strip()]
        edid = _read_bytes(conn_dir / "edid")
        present = edid_is_present(edid)
        name_from_edid = parse_edid_name(edid) if present else None
        if refresh is None and present and width and height:
            refresh = refresh_from_edid(edid, width, height)
        return ConnectorStatus(
            name=name,
            connected=connected,
            width=width,
            height=height,
            refresh=refresh,
            edid_name=name_from_edid,
            edid_present=present,
            modes=modes,
            raw_mode=raw_mode,
            raw_status=raw_status,
        )
    except Exception:
        return None


def list_hdmi_connectors(drm_root: Path) -> list[ConnectorStatus]:
    """Every HDMI-like connector under drm_root, fail-safe.  Empty if missing."""
    found: list[ConnectorStatus] = []
    try:
        if not drm_root.is_dir():
            return found
        for entry in sorted(drm_root.iterdir(), key=lambda p: p.name):
            if not CONNECTOR_DIR_RE.match(entry.name):
                continue
            if not HDMI_CONNECTOR_RE.search(entry.name):
                continue
            # Prefer the class-level symlink (card0-HDMI-A-1), skip nested
            # card0/card0-HDMI-A-1 if both exist: they share a name.
            info = read_connector(entry)
            if info and all(c.name != info.name for c in found):
                found.append(info)
    except Exception:
        return found
    return found


def pick_connector(
    connectors: list[ConnectorStatus], wanted: str | None
) -> ConnectorStatus | None:
    if wanted:
        for c in connectors:
            if c.name == wanted:
                return c
    for c in connectors:
        if c.connected:
            return c
    return connectors[0] if connectors else None


def drm_has_hdmi(drm_root: Path) -> bool:
    return bool(list_hdmi_connectors(drm_root))


# ---------------------------------------------------------------------------
# Boot-file editing (all paths supplied by the caller)
# ---------------------------------------------------------------------------

def find_boot_dir(candidates: tuple[Path, ...] | list[Path] = BOOT_CANDIDATES) -> Path | None:
    for d in candidates:
        if (d / "config.txt").is_file():
            return d
    return None


def video_token(connector: str, width: int, height: int, refresh: int) -> str:
    return f"video={connector}:{width}x{height}@{refresh}{VIDEO_FORCE_FLAG}"


def edid_firmware_token(connector: str, relpath: str) -> str:
    return f"drm.edid_firmware={connector}:{relpath}"


def _is_video_token_for(token: str, connector: str) -> bool:
    return token.startswith(f"video={connector}:")


def _edid_firmware_parts(token: str) -> list[tuple[str, str]]:
    if not token.startswith("drm.edid_firmware="):
        return []
    body = token.split("=", 1)[1]
    parts: list[tuple[str, str]] = []
    for item in body.split(","):
        if ":" not in item:
            continue
        conn, path = item.split(":", 1)
        parts.append((conn, path))
    return parts


def rewrite_cmdline(
    text: str,
    request: HdmiRequest,
) -> str:
    """Return a one-line cmdline with our video= / edid tokens updated.

    Other arguments, including any video= for a different connector, are
    left alone.  A previous Sandbells (or any) video= for this connector
    is replaced, because a forced mode has to be the one that takes effect.
    """
    # cmdline.txt is a single line; keep only non-empty tokens.
    body = text.replace("\n", " ").replace("\r", " ").strip()
    tokens = [t for t in body.split() if t]
    connector = request.connector
    kept: list[str] = []
    for t in tokens:
        if _is_video_token_for(t, connector):
            continue
        parts = _edid_firmware_parts(t)
        if parts:
            rest = [(c, p) for c, p in parts if c != connector]
            if rest:
                kept.append("drm.edid_firmware=" + ",".join(f"{c}:{p}" for c, p in rest))
            continue
        kept.append(t)
    if request.is_force:
        assert request.width and request.height and request.refresh
        rel = edid_firmware_relpath(request.width, request.height, request.refresh)
        kept.append(video_token(connector, request.width, request.height, request.refresh))
        kept.append(edid_firmware_token(connector, rel))
    return " ".join(kept) + "\n"


def _legacy_config_block(request: HdmiRequest) -> str:
    assert request.is_force and request.width and request.height and request.refresh
    lines = [CONFIG_BEGIN]
    lines.append("hdmi_force_hotplug=1")
    lines.append(f"hdmi_ignore_edid={HDMI_IGNORE_EDID_MAGIC}")
    cea = CEA_MODES.get((request.width, request.height, request.refresh))
    if cea is not None:
        lines.append(f"hdmi_group={HDMI_GROUP_CEA}")
        lines.append(f"hdmi_mode={cea}")
    else:
        lines.append(f"hdmi_group={HDMI_GROUP_DMT}")
        lines.append(f"hdmi_mode={HDMI_MODE_CVT_CUSTOM}")
        lines.append(
            "hdmi_cvt="
            f"{request.width} {request.height} {request.refresh} "
            f"{HDMI_CVT_ASPECT_16_9} {HDMI_CVT_MARGINS} "
            f"{HDMI_CVT_PROGRESSIVE} {HDMI_CVT_REDUCED_BLANKING}"
        )
    lines.append(f"hdmi_drive={HDMI_DRIVE_HDMI}")
    lines.append(CONFIG_END)
    return "\n".join(lines) + "\n"


def _strip_config_block(text: str) -> str:
    out: list[str] = []
    skipping = False
    for line in text.splitlines():
        if line.strip() == CONFIG_BEGIN:
            skipping = True
            continue
        if skipping:
            if line.strip() == CONFIG_END:
                skipping = False
            continue
        out.append(line)
    # Drop trailing extra blank lines left behind, keep one final newline.
    while out and out[-1].strip() == "":
        out.pop()
    return ("\n".join(out) + "\n") if out else ""


def rewrite_config(text: str, request: HdmiRequest, driver: str) -> str:
    """Insert or remove the marked sandbells-hdmi block.

    The block is written for legacy and FKMS (hdmi_* is honoured).  On
    full KMS it is removed, because those options are ignored and the
    kernel cmdline is the real force.
    """
    body = _strip_config_block(text)
    if request.is_force and driver in (DRIVER_LEGACY, DRIVER_FKMS):
        if body and not body.endswith("\n"):
            body += "\n"
        if body:
            body += "\n"
        body += _legacy_config_block(request)
    return body if body.endswith("\n") or body == "" else body + "\n"


def _backup(path: Path) -> Path:
    ts = datetime.now().strftime(BACKUP_TIME_FMT)
    dest = path.with_name(path.name + BACKUP_SUFFIX + "-" + ts)
    shutil.copy2(path, dest)
    orig = path.with_name(path.name + ORIG_SUFFIX)
    if not orig.exists():
        shutil.copy2(path, orig)
    return dest


@dataclass
class ApplyResult:
    ok: bool
    reboot_needed: bool
    driver: str
    changed: bool
    backups: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    error: str | None = None
    request: HdmiRequest | None = None

    def report(self) -> str:
        lines: list[str] = []
        if self.error:
            lines.append(f"ERROR: {self.error}")
        if self.request is not None:
            lines.append(f"Requested: {self.request.requested_label}")
            lines.append(f"Connector: {self.request.connector}")
        lines.append(f"Driver: {self.driver}")
        for a in self.actions:
            lines.append(a)
        for b in self.backups:
            lines.append(f"Backup: {b}")
        if not self.ok:
            lines.append("Apply failed; boot files were not left half-written.")
        elif self.reboot_needed:
            lines.append("Reboot needed: yes  (the mode is applied at boot)")
        else:
            lines.append("Reboot needed: no  (already applied)")
        return "\n".join(lines) + "\n"


def apply_hdmi(
    request: HdmiRequest,
    *,
    config_txt: Path,
    cmdline_txt: Path,
    edid_dir: Path,
    state_path: Path,
    dry_run: bool = False,
) -> ApplyResult:
    """Write a forced mode into the given boot files, or remove one.

    All paths are required.  This function will not guess /boot.  It
    refuses a missing or empty cmdline (writing an empty one would make
    a Pi unbootable).  It never writes settings.json.
    """
    if request.error:
        return ApplyResult(
            ok=False, reboot_needed=False, driver=DRIVER_KMS,
            changed=False, error=request.error, request=request,
        )
    if not config_txt.is_file():
        return ApplyResult(
            ok=False, reboot_needed=False, driver=DRIVER_KMS, changed=False,
            error=f"config.txt not found: {config_txt}", request=request,
        )
    if not cmdline_txt.is_file():
        return ApplyResult(
            ok=False, reboot_needed=False, driver=DRIVER_KMS, changed=False,
            error=f"cmdline.txt not found: {cmdline_txt}", request=request,
        )
    try:
        config_old = config_txt.read_text(encoding="utf-8")
        cmdline_old = cmdline_txt.read_text(encoding="utf-8")
    except Exception as exc:
        return ApplyResult(
            ok=False, reboot_needed=False, driver=DRIVER_KMS, changed=False,
            error=f"cannot read boot files: {exc}", request=request,
        )
    if not cmdline_old.strip():
        return ApplyResult(
            ok=False, reboot_needed=False, driver=DRIVER_KMS, changed=False,
            error="cmdline.txt is empty; refusing to write it",
            request=request,
        )
    driver = detect_driver(config_old)
    new_cmdline = rewrite_cmdline(cmdline_old, request)
    if not new_cmdline.strip():
        return ApplyResult(
            ok=False, reboot_needed=False, driver=driver, changed=False,
            error="refusing to write an empty cmdline.txt",
            request=request,
        )
    new_config = rewrite_config(config_old, request, driver)

    actions: list[str] = []
    backups: list[str] = []
    edid_path: Path | None = None
    edid_bytes: bytes | None = None
    if request.is_force:
        assert request.width and request.height and request.refresh
        edid_bytes = build_edid(request.width, request.height, request.refresh)
        edid_path = edid_dir / edid_filename(request.width, request.height, request.refresh)
        if driver == DRIVER_KMS:
            actions.append(
                "KMS: "
                + video_token(request.connector, request.width, request.height, request.refresh)
                + " and "
                + edid_firmware_token(
                    request.connector,
                    edid_firmware_relpath(request.width, request.height, request.refresh),
                )
            )
        else:
            actions.append(
                f"{driver}: hdmi_force_hotplug, hdmi_ignore_edid, "
                f"mode {request.width}x{request.height}@{request.refresh}"
            )
            # Also put video= on the cmdline so a later switch to full KMS
            # keeps the force.  rewrite_cmdline already did that.
            actions.append(
                "Also on cmdline (for KMS): "
                + video_token(request.connector, request.width, request.height, request.refresh)
            )
    else:
        actions.append("auto: Sandbells forced-mode tokens removed")

    cmdline_changed = new_cmdline.strip() != cmdline_old.replace("\r\n", "\n").replace("\r", "\n").strip()
    # Compare config without fussing over a single trailing newline.
    config_changed = new_config.strip() != config_old.strip()
    edid_changed = False
    if edid_path is not None and edid_bytes is not None:
        edid_changed = (not edid_path.is_file()) or edid_path.read_bytes() != edid_bytes
    changed = cmdline_changed or config_changed or edid_changed

    if dry_run:
        actions.append("dry-run: no files written")
        return ApplyResult(
            ok=True, reboot_needed=changed, driver=driver, changed=changed,
            actions=actions, request=request,
        )

    if not changed:
        _write_state(state_path, request, driver, backups, reboot=False)
        return ApplyResult(
            ok=True, reboot_needed=False, driver=driver, changed=False,
            actions=actions + ["already applied"], request=request,
        )

    # Write to temp files next to the targets, then replace.  Backup first.
    try:
        if cmdline_changed:
            backups.append(str(_backup(cmdline_txt)))
        if config_changed:
            backups.append(str(_backup(config_txt)))
        if cmdline_changed:
            _atomic_write(cmdline_txt, new_cmdline)
        if config_changed:
            _atomic_write(config_txt, new_config)
        if edid_path is not None and edid_bytes is not None and edid_changed:
            edid_path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(edid_path, edid_bytes, binary=True)
            actions.append(f"EDID: {edid_path}")
    except Exception as exc:
        return ApplyResult(
            ok=False, reboot_needed=False, driver=driver, changed=False,
            backups=backups, actions=actions,
            error=f"write failed: {exc}", request=request,
        )

    _write_state(state_path, request, driver, backups, reboot=True)
    return ApplyResult(
        ok=True, reboot_needed=True, driver=driver, changed=True,
        backups=backups, actions=actions, request=request,
    )


def _atomic_write(path: Path, data: str | bytes, binary: bool = False) -> None:
    tmp = path.with_name(path.name + ".sandbells-hdmi.tmp")
    if binary:
        assert isinstance(data, (bytes, bytearray))
        tmp.write_bytes(data)
    else:
        assert isinstance(data, str)
        tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)


def _write_state(
    state_path: Path,
    request: HdmiRequest,
    driver: str,
    backups: list[str],
    reboot: bool,
) -> None:
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "applied_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "driver": driver,
            "mode": request.mode,
            "width": request.width,
            "height": request.height,
            "refresh": request.refresh,
            "connector": request.connector,
            "reboot_needed": reboot,
            "backups": backups,
        }
        _atomic_write(state_path, json.dumps(payload, indent=2) + "\n")
    except Exception:
        # State is diagnostic only; a failure to write it is not fatal.
        pass


# ---------------------------------------------------------------------------
# Status payload for the Sandbells status page / API
# ---------------------------------------------------------------------------

def hdmi_status(
    request: HdmiRequest,
    drm_root: Path,
    *,
    cmdline_text: str | None = None,
    applied_state: dict | None = None,
) -> dict[str, Any]:
    """Fail-safe dict of requested and actual HDMI facts."""
    connectors = list_hdmi_connectors(drm_root)
    chosen = pick_connector(connectors, request.connector)
    actual = chosen.actual_label if chosen else ACTUAL_UNKNOWN
    monitor = chosen.monitor_label if chosen else MONITOR_UNKNOWN
    edid = chosen.edid_label if chosen else EDID_MISSING_LABEL
    connector = chosen.name if chosen else (request.connector or MONITOR_UNKNOWN)
    mismatch = False
    if request.is_force and chosen and chosen.width and chosen.height:
        mismatch = (
            chosen.width != request.width
            or chosen.height != request.height
            or (chosen.refresh is not None and request.refresh is not None
                and chosen.refresh != request.refresh)
        )
    boot_video = ""
    if cmdline_text:
        for tok in cmdline_text.split():
            if _is_video_token_for(tok, request.connector):
                boot_video = tok
                break
    apply_needed = False
    if request.is_force:
        want = video_token(request.connector, request.width, request.height, request.refresh)  # type: ignore[arg-type]
        if cmdline_text is not None and want not in cmdline_text.split():
            apply_needed = True
        if applied_state and applied_state.get("mode") != HDMI_MODE_FORCE:
            apply_needed = True
    elif applied_state and applied_state.get("mode") == HDMI_MODE_FORCE:
        apply_needed = True

    return {
        "hdmi_requested": request.requested_label,
        "hdmi_actual": actual,
        "hdmi_connector": connector,
        "hdmi_monitor": monitor,
        "hdmi_edid": edid,
        "hdmi_mismatch": mismatch,
        "hdmi_apply_needed": apply_needed,
        "hdmi_error": request.error or "",
        "hdmi_boot_video": boot_video,
        "hdmi_mode": request.mode if not request.error else HDMI_MODE_AUTO,
        "hdmi_width": request.width,
        "hdmi_height": request.height,
        "hdmi_refresh": request.refresh,
    }


def empty_hdmi_status() -> dict[str, Any]:
    return {
        "hdmi_requested": REQUESTED_AUTO_LABEL,
        "hdmi_actual": ACTUAL_UNKNOWN,
        "hdmi_connector": MONITOR_UNKNOWN,
        "hdmi_monitor": MONITOR_UNKNOWN,
        "hdmi_edid": EDID_MISSING_LABEL,
        "hdmi_mismatch": False,
        "hdmi_apply_needed": False,
        "hdmi_error": "",
        "hdmi_boot_video": "",
        "hdmi_mode": HDMI_MODE_AUTO,
        "hdmi_width": None,
        "hdmi_height": None,
        "hdmi_refresh": None,
    }


def load_applied_state(path: Path) -> dict | None:
    try:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        return None
    return None


def load_cmdline_text(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_safe(text: str) -> None:
    """Print a report, refusing to emit anything that looks like a secret."""
    lower = text.lower()
    for key in SETTINGS_KEYS_NEVER_PRINTED:
        if key in lower and ("networks" in lower or "psk" in lower or "password" in lower):
            text = "[redacted: refused to print a report that may contain a secret]\n"
            break
    sys.stdout.write(text)


def _cli_paths(args: argparse.Namespace) -> dict[str, Path]:
    boot = Path(args.boot) if args.boot else find_boot_dir()
    if boot is None:
        raise SystemExit("No boot directory with config.txt found.  Pass --boot.")
    firmware = Path(args.firmware_dir) if args.firmware_dir else DEFAULT_FIRMWARE_DIR
    return {
        "config_txt": boot / "config.txt",
        "cmdline_txt": boot / "cmdline.txt",
        "edid_dir": firmware / EDID_FIRMWARE_SUBDIR,
        "state_path": Path(args.state) if args.state else DEFAULT_STATE_PATH,
        "settings": Path(args.settings) if args.settings else DEFAULT_SETTINGS_PATH,
        "drm_root": Path(args.drm) if args.drm else DEFAULT_DRM_ROOT,
        "boot": boot,
    }


def _cmd_apply(args: argparse.Namespace) -> int:
    paths = _cli_paths(args)
    request = load_hdmi_request(paths["settings"])
    result = apply_hdmi(
        request,
        config_txt=paths["config_txt"],
        cmdline_txt=paths["cmdline_txt"],
        edid_dir=paths["edid_dir"],
        state_path=paths["state_path"],
        dry_run=args.dry_run,
    )
    _print_safe(result.report())
    return 0 if result.ok else 1


def _cmd_status(args: argparse.Namespace) -> int:
    paths = _cli_paths(args)
    request = load_hdmi_request(paths["settings"])
    status = hdmi_status(
        request,
        paths["drm_root"],
        cmdline_text=load_cmdline_text(paths["cmdline_txt"]),
        applied_state=load_applied_state(paths["state_path"]),
    )
    lines = [
        f"Requested: {status['hdmi_requested']}",
        f"Actual:    {status['hdmi_actual']}",
        f"Connector: {status['hdmi_connector']}",
        f"Monitor:   {status['hdmi_monitor']}",
        f"EDID:      {status['hdmi_edid']}",
    ]
    if status["hdmi_error"]:
        lines.append(f"Error:     {status['hdmi_error']}")
    if status["hdmi_apply_needed"]:
        lines.append("Apply:     needed (run: sudo sandbells-hdmi apply)")
    if status["hdmi_mismatch"]:
        lines.append("Mismatch:  requested and actual differ")
    if status["hdmi_boot_video"]:
        lines.append(f"This boot: {status['hdmi_boot_video']}")
    _print_safe("\n".join(lines) + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Sandbells HDMI helper: apply a forced mode from "
            "/etc/sandbells/settings.json (display.hdmi) to the Pi's boot "
            "files, or show requested and actual HDMI facts.  Never edits "
            "settings.json."
        )
    )
    parser.add_argument("--settings", help="path to settings.json")
    parser.add_argument("--boot", help="directory with config.txt and cmdline.txt")
    parser.add_argument("--firmware-dir", help="firmware directory (default /lib/firmware)")
    parser.add_argument("--state", help="applied-state JSON path")
    parser.add_argument("--drm", help="sysfs drm root (default /sys/class/drm)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_apply = sub.add_parser("apply", help="write or remove a forced boot mode")
    p_apply.add_argument("--dry-run", action="store_true", help="show what would change")
    p_apply.set_defaults(func=_cmd_apply)

    p_status = sub.add_parser("status", help="show requested and actual HDMI facts")
    p_status.set_defaults(func=_cmd_status)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except SystemExit:
        raise
    except Exception as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
