# HDMI mode (forced resolution for the kiosk)

The Sandbells kiosk is a Raspberry Pi 3 driving an HDMI monitor through
Luakit on Xorg.  At the tower a **passive HDMI splitter** feeding two
monitors can hide or break the monitor's EDID, and the Pi then falls
back to a low resolution that makes the kiosk unusable.

An optional `display.hdmi` block in `/etc/sandbells/settings.json`
asks for a **forced** mode that does not depend on EDID.  For the
tower, force **1920×1080 at 60 Hz**.

The setting is applied **persistently at boot** by the helper
`sandbells-hdmi` (installed by `install-steps/20-hdmi.sh`).  Django
never writes boot files, and nothing rewrites `settings.json` — you
hand-edit it.

## The setting

Omitted, or automatic (the default: leave KMS / the firmware to
negotiate, no force):

```json
"display": {
  "random_bells": 6,
  "random_windows": 3,
  "pattern_position_mode": "shorter",
  "hdmi": { "mode": "auto" }
}
```

Forced mode, recommended at the tower (width, height and refresh
default to 1920, 1080 and 60 if you leave them out):

```json
"display": {
  "random_bells": 6,
  "random_windows": 3,
  "pattern_position_mode": "shorter",
  "hdmi": {
    "mode": "force",
    "width": 1920,
    "height": 1080,
    "refresh": 60
  }
}
```

`"mode": "explicit"` is accepted as the same as `"force"`.  An optional
`"connector"` (default `HDMI-A-1`) selects which HDMI output, which on
a Pi 3 is the only one.

## Apply

After a hand-edit, on the Pi:

```
sudo sandbells-hdmi apply
```

The helper:

1. Reads `display.hdmi` only (it never prints Wi-Fi passwords and
   never writes `settings.json`).
2. Detects the video stack from `config.txt`: full KMS
   (`dtoverlay=vc4-kms-v3d`, current Raspberry Pi OS), FKMS
   (`vc4-fkms-v3d`), or the legacy firmware driver.
3. **KMS:** adds `video=HDMI-A-1:1920x1080@60D` to `cmdline.txt`
   (the `D` forces the connector on as digital, even with no hotplug)
   and installs a canned EDID at
   `/lib/firmware/edid/sandbells-1920x1080-60.bin`, referenced by
   `drm.edid_firmware=…`, so a missing or garbage EDID from a
   splitter is replaced.  The `hdmi_*` options in `config.txt` are
   ignored under full KMS and are not used.
4. **Legacy and FKMS:** writes a marked block in `config.txt`:
   `hdmi_force_hotplug=1`, `hdmi_ignore_edid=0xa5000080`, and
   `hdmi_group` / `hdmi_mode` (CEA mode 16 for 1920×1080@60; a CVT
   mode for anything we do not have a CEA number for), plus the same
   `video=` token on the cmdline so a later switch to full KMS keeps
   the force.
5. Backs up each file it changes (`cmdline.txt.sandbells-hdmi.bak-<timestamp>`,
   and a one-time `.sandbells-hdmi.orig`).  Other cmdline arguments
   and existing lines such as `hdmi_blanking=1` are left alone.
6. Prints whether a **reboot is needed**.  The mode is only in effect
   after a reboot (or a power-cycle).  A second apply with the same
   setting is a no-op and does not ask for a reboot.

`"mode": "auto"` **removes** a previously applied Sandbells force
(the marked `config.txt` block and our `video=` / `drm.edid_firmware`
tokens) and reports if a reboot is needed to return to negotiation.

The helper refuses to write an empty `cmdline.txt`.  Use
`sudo sandbells-hdmi apply --dry-run` to see the plan without writing.

Boot files are found at `/boot/firmware/config.txt` (Bookworm and
later) or `/boot/config.txt` (older images), with `cmdline.txt` next
to `config.txt`.

## Status page

The farm status page of this machine (Display section) and
`/api/system-status/` show, read **at runtime** from
`/sys/class/drm` (no X needed, fail-safe if sysfs is missing):

| Row | Meaning |
| --- | --- |
| HDMI requested | What `display.hdmi` asks for, e.g. `1920x1080@60 (forced)` or `auto (negotiate)` |
| HDMI actual | The current resolution and refresh, e.g. `1920x1080@60`, or `—` |
| HDMI connector | Kernel name, e.g. `HDMI-A-1` |
| HDMI monitor | `connected` or `disconnected` (as the kernel reports it) |
| HDMI EDID | The monitor name from EDID, or **`no EDID`** when the splitter gives none |

A mismatch between requested and actual is flagged, as is `no EDID`
and a needed apply (settings changed since the last `sandbells-hdmi apply`).
If the canned EDID is in use, the name is `Sandbells` — that is how
you can see the override took effect.

`sudo sandbells-hdmi status` prints the same facts from the shell.

## Rollback

Hand-edit `display.hdmi` to `"mode": "auto"` (or remove the block),
then:

```
sudo sandbells-hdmi apply
sudo reboot
```

To put a boot file back from the helper's first backup, copy the
`.sandbells-hdmi.orig` next to it over the live file and reboot.
Only do that if you understand the file: a broken `cmdline.txt`
will stop the Pi booting.

## Install

On a machine that already has Sandbells, after this code is on disk:

```
bash ~/Code/Sandbells/install-steps/20-hdmi.sh true
```

It installs `/usr/local/sbin/sandbells-hdmi` and runs `apply` once
against the current settings.  A new install via `master_install.sh`
includes this step automatically (it runs every `install-steps/NN-*.sh`).
The example settings ship with `"mode": "auto"`; add the force block
yourself for the tower, then apply and reboot.

## What this does not do

- It does not change Luakit's window size in `start-kiosk-solo.sh`
  (that is a separate 1920×1080 geometry, not the HDMI mode).
- It does not rewrite `/etc/sandbells/settings.json`.
- Forcing a mode the *monitor* cannot display can give a blank
  picture; 1920×1080@60 is the usual widescreen mode and is the one
  to try at the tower.  If the picture is blank after a force, roll
  back as above (SSH still works).
