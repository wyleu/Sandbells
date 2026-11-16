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

## Play and the dot (second patch)

A tune with a MIDI file gets a player on the Chimes screen (top of the tune
menu on the right, so it never covers the sheet's title) and in the
full-screen view (a narrow column in the left black margin, faint until
touched):

* **Play / Stop / Tempo** (50-150 %, `chime_player.TEMPO_PERCENT_*`).
  With a note map a dot (red, white ring, black edge, so it shows on red
  bell-1 note heads) follows the music and the page turns by itself.
* **MIDI out on/off**, **HDMI audio on/off**, and the **MIDI port** menu.
  The switches are kept in the database (`ChimeOutputs`, one row, also in
  the admin under Bells > Chimes player outputs), so they survive a reload
  or a restart.  They apply to the next Play; changed while that tune
  plays, it is started again from where it is.  **Both off:** Play still
  runs the dot, silently.

What each output does:

* **MIDI out:** a copy of the tune, with the tempo and the start point
  already in its times, is played with `aplaymidi -p PORT` (alsa-utils,
  already on sandbells2).  Stop kills it, then sends sustain off, all sound
  off and all notes off on all 16 channels to that port.  **Never the
  Pico:** ports whose client or port name contains `Pico`, `CircuitPython`
  or `Pico 2 W` (what ingest_midi looks for) are left out of every list and
  refused by Play, the switch POST and the admin.  `GET /chimes/player/ports/`
  lists the allowed ports (`aplaymidi -l`, the Pico left out).
  Port "automatic": the first allowed port that is not Midi Through (Midi
  Through if it is the only one).
* **HDMI audio:** bell samples through fluidsynth (`-n`: no MIDI input, so
  it never opens an ALSA MIDI port) on the HDMI ALSA device.  Needs
  `sudo apt install fluidsynth` and the soundfont.

Settings (optional; first values only, the screen changes them after
that; nothing is written to any settings file): `"chimes"` in
`/etc/sandbells/settings.json`

| key | default | |
|---|---|---|
| `midi_out` | `true` | MIDI out switch, first value |
| `midi_port` | `""` (automatic) | `14:0`-style id or part of a client name |
| `midi_exclude` | `[]` | more names to leave out (the Pico ones are always left out) |
| `hdmi_audio` | `false` | HDMI audio switch, first value (needs fluidsynth) |
| `hdmi_device` | `hdmi:CARD=vc4hdmi,DEV=0` | ALSA device for fluidsynth (Pi 3, KMS) |
| `soundfont` | `/usr/local/share/sounds/sf2/sandbach_bells_8.sf2` if present, else `/usr/share/sounds/sf2/FluidR3_GM.sf2` | |
| `gain` | `0.6` | fluidsynth gain |
| `program_changes` | `false` | send the file's programs to fluidsynth (MIDI out always sends them) |
| `aplaymidi`, `fluidsynth` | `aplaymidi`, `fluidsynth` | program paths |

Django settings `SANDBELLS_CHIMES_MIDI_PORT`, `SANDBELLS_CHIMES_HDMI_DEVICE`,
`SANDBELLS_CHIMES_SOUNDFONT`, `SANDBELLS_CHIMES_GAIN`,
`SANDBELLS_CHIMES_PLAYER_STATE` win over the JSON.  With the old firmware
audio driver the HDMI device is e.g. `plughw:CARD=b1`; `aplay -L | grep -i hdmi`
lists the names.  The 12-note font (`Sandbach Bells_n_12.sf2`) is used only
when named in `soundfont`; spaces in the path are fine.

* Build the files on the desk Pi with `tools/chimes/chime-build` (see
  `tools/chimes/README.md`), then `manage.py chime_load <slug>.chime.zip`.
  The admin also takes a MIDI file and a `notemap.json` per tune.
* **8 bells, strict:** a tune with notes other than F5 E5 D5 C5 Bb4 A4 G4 F4
  shows a warning in the admin (list column "8 bells", and the notes with
  bar and beat on the tune) and on the player.
* One player at a time: Play stops whatever is playing.  The driver
  (`bells/chime_driver.py`) runs detached in its own process group; Stop
  kills that group (aplaymidi and fluidsynth included).  State:
  `media/chimes/player-state.json` (with the MIDI-out copy next to it).
* Play, Stop and the switches are POSTs with the CSRF token, and only from
  this Pi or the LAN.  `GET /chimes/player/state/` gives the tune, the start
  time, tempo, what it is playing to (`playing_to`) and the switches
  (`outputs`).
* JS helpers: `node --test changes/bells/js_tests/*.test.js`.

Rollback of this part: `python manage.py migrate bells 0005`.
