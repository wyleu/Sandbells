# tools/chimes: LilyPond tune -> Sandbells Chimes bundle

Runs on the desk Pi (LilyPond 2.24, poppler-utils), not on the kiosk.

    tools/chimes/chime-build ~/Documents/Sandbells-docs/Chimes/boars-head-carol.ly -o ~/chime-bundles
    tools/chimes/chime-build TUNE.ly -o OUT --overlay      # also draw the note map on the pages
    tools/chimes/chime-build TUNE.ly -o OUT --allow        # build even with notes off the bells

Output: `OUT/<slug>/` (tune.json, score.pdf, tune.midi, notemap.json,
pages/page-NNN.png, overlay/ with --overlay) and `OUT/<slug>.chime.zip`.
On sandbells: `manage.py chime_load <slug>.chime.zip`.

* The .ly is not edited.  `chime-notemap.ily` is loaded with
  `lilypond -dinclude-settings=...`: an engraver in every Voice records each
  note head's moment, bar, beat, pitch and tie, and the PostScript backend's
  `grob-cause` hook is wrapped to write each head's box on its page
  (`CHIME_NOTEMAP_OUT`).  Point-and-click is not changed.
* Pages are rendered like Sandbells does (pdftoppm, 1080 px tall); the note
  map stores positions as fractions of the page, so it fits any size.
* The MIDI is LilyPond's own (repeats unfolded in the `\midi` score); each
  played chord is matched to its printed chord, jumping back for repeats.
  Without a `\midi` block a MIDI file is made from the printed notes at
  `--tempo` (repeats then play once).
* **8-bell check (strict):** every note must be one of F5 E5 D5 C5 Bb4 A4 G4 F4
  (bells 1-8, `BELLS_8` in `changes/bells/chime_notemap.py`).  Anything else is
  listed with bar, beat and pitch and nothing is written (exit 2) unless
  `--allow`.  Notes are never transposed or bent.
