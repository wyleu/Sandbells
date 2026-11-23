# tools/chimes/tunes

Sources for the Sandbells chime sheets, by type:

- `ly/` — LilyPond tunes, one `.ly` per sheet
- `zss/` — Zynthian sequencer snapshots (from the cajon)
- `midi/` — MIDI recorded from a keyboard while reading a PDF sheet
  (empty until the first recording; see `midi/README.md`)

`bell-colours.ily` is in `tools/chimes/`.  `chime-build` adds that folder
to LilyPond's include path, so `\include "bell-colours.ily"` works when
you build.  `ly/bell-colours.ily` is a symlink to it, so Frescobaldi
finds the include when you open a tune from `ly/` (no extra include path).

Scripts: `tools/chimes/zss2chime` and `tools/chimes/zss2ly.py` turn a
`.zss` snapshot into a house-style `.ly` and a bundle.  Little Donkey
was built that way from `zss/little-donkey-a.zss`.

Build on the desk Pi (LilyPond 2.24, poppler-utils), from the Sandbells
root.  Each command is the one used for that tune's bundle.  A tune
should be one page; if `chime-build` stops with exit 3, rearrange the
layout, or add `--pages-ok` only if the tune genuinely needs more than
one page.

| Tune | Source | Slug | Build |
|---|---|---|---|
| The Boars Head Carol | `ly/boars-head-carol.ly` | the-boars-head-carol | `tools/chimes/chime-build tools/chimes/tunes/ly/boars-head-carol.ly -o ~/chime-bundles` |
| Chirpy Chirpy Cheep Cheep | `ly/Chirpy-chirpy-cheep-cheep.ly` | chirpy-chirpy-cheep-cheep | `tools/chimes/chime-build tools/chimes/tunes/ly/Chirpy-chirpy-cheep-cheep.ly -o ~/chime-bundles` |
| Felix Navidad | `ly/Felix-navidad.ly` | felix-navidad | `tools/chimes/chime-build tools/chimes/tunes/ly/Felix-navidad.ly -o ~/chime-bundles` |
| Felix Navidad (back) | `ly/Felix-navidad-back.ly` | felix-navidad-back | `tools/chimes/chime-build tools/chimes/tunes/ly/Felix-navidad-back.ly -o ~/chime-bundles --title "Felix Navidad (back)"` |
| Stairway to Heaven | `ly/Stairway-to-heaven.ly` | stairway-to-heaven | `tools/chimes/chime-build tools/chimes/tunes/ly/Stairway-to-heaven.ly -o ~/chime-bundles` |
| Stairway to Heaven (simple) | `ly/Stairway-to-heaven-simple.ly` | stairway-to-heaven-simple | `tools/chimes/chime-build tools/chimes/tunes/ly/Stairway-to-heaven-simple.ly -o ~/chime-bundles --title "Stairway to Heaven (simple)"` |
| Sandbell Rounds | `ly/Sandbell-Rounds.ly` | sandbell-rounds | `tools/chimes/chime-build tools/chimes/tunes/ly/Sandbell-Rounds.ly -o ~/chime-bundles` |
| Troika Sleigh Ride | `ly/troika-sleigh-ride.ly` | troika-sleigh-ride | `tools/chimes/chime-build tools/chimes/tunes/ly/troika-sleigh-ride.ly -o ~/chime-bundles` |
| Congratulations | `ly/Congratulations.ly` | congratulations | `tools/chimes/chime-build tools/chimes/tunes/ly/Congratulations.ly -o ~/chime-bundles` |
| Nimrod Enigma Variations | `ly/Nimrod-Enigma-Variations.ly` | nimrod-enigma-variations | `tools/chimes/chime-build tools/chimes/tunes/ly/Nimrod-Enigma-Variations.ly -o ~/chime-bundles` |
| Sandbell Rounds (numbered) | `ly/Sandebell-Rounds.ly` | sandbell-rounds-numbered | `tools/chimes/chime-build tools/chimes/tunes/ly/Sandebell-Rounds.ly -o ~/chime-bundles --title "Sandbell Rounds (numbered)"` |
| Little Donkey | `ly/little-donkey.ly` | little-donkey | `tools/chimes/chime-build tools/chimes/tunes/ly/little-donkey.ly -o ~/chime-bundles` |

Little Donkey from the snapshot (writes `ly/little-donkey.ly` and the bundle):

    tools/chimes/zss2chime tools/chimes/tunes/zss/little-donkey-a.zss \
        -o ~/chime-bundles --title "Little Donkey"
