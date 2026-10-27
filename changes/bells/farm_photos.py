"""farm_photos.py -- which photo belongs to which machine (one place, pure).

The pictures live in bells/static/img/farm/ as <file>.jpg (600x600, header
size) and <file>-thumb.jpg (160x160, small spots).  PHOTOS maps a machine key
to its file stem; ALIASES maps other spellings of a key (registry ids that are
not the bare host name) to a PHOTOS key.  A machine with no entry simply has
no photo: photo_for() returns None and every page copes (no broken image).

Keys are the farm registry id / name / host in /etc/sandbells/settings.json,
lower case, without ".local".  To add a machine: drop <key>.jpg and
<key>-thumb.jpg into static/img/farm/, add one line to PHOTOS, and the test
FarmPhotoFilesTests checks the files are there.
"""

PHOTOS = {
    "sandbells":  "sandbells",     # the display machine, sandbells.local (HiFiBerry case, 4 labelled knobs)
    "sandbells2": "sandbells2",    # sandbells2.local (HiFiBerry case with a fan)
    "sandswing":  "sandswing",     # the Pico 2 W concentrator (4-RJ45 wall plate, 6 status LEDs)
    "sandsense":  "sandsense",     # laser tower-clock monitor (white box with knob)
    "sandgps3":   "sandgps3",      # home GPS PPS stratum 1 clock (small OLED)
    "sandmon":    "sandmon",       # tower clock source / time hotspot (Pi Zero 2 W, round clock display)
    "sandtest":   "sandtest",      # opto / stepper test rig (black box); its page is on branch "sandtest"
}

ALIASES = {
    "sandsense-clock": "sandsense",    # the id used in status-v1.md's example registry
}

IMG_DIR = "img/farm"          # under the static root
LARGE = ""                    # file suffix of the 600x600 picture
THUMB = "-thumb"              # file suffix of the 160x160 picture
THUMB_MAX_PX = 80             # at or below this display size the thumbnail is used


def normalise(key):
    """'SandSwing.local ' -> 'sandswing'; anything odd -> ''."""
    if not isinstance(key, str):
        return ""
    k = key.strip().lower()
    if k.endswith(".local"):
        k = k[: -len(".local")]
    return k


def photo_key(*keys):
    """The first of the given keys (id, name, host ...) that has a photo, or None."""
    for key in keys:
        k = normalise(key)
        k = ALIASES.get(k, k)
        if k in PHOTOS:
            return k
    return None


def photo_for(*keys):
    """Static path ('img/farm/sandswing.jpg') pair (large, thumb) or None."""
    k = photo_key(*keys)
    if k is None:
        return None
    stem = PHOTOS[k]
    return ("%s/%s%s.jpg" % (IMG_DIR, stem, LARGE), "%s/%s%s.jpg" % (IMG_DIR, stem, THUMB))


def all_files():
    """Every static path the registry names (for the file-exists test)."""
    out = []
    for stem in sorted(set(PHOTOS.values())):
        out += ["%s/%s%s.jpg" % (IMG_DIR, stem, LARGE), "%s/%s%s.jpg" % (IMG_DIR, stem, THUMB)]
    return out
