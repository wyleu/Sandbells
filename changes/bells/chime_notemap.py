"""Chimes note maps: where each note of a tune sits on its page images and
when it sounds.  Stdlib only, no Django: tools/chimes/chime-build (desk Pi)
builds them, Sandbells reads them.

Built from two things LilyPond writes for the same .ly:
  * the note-head table from chime-notemap.ily (page, box on the page in
    LilyPond units, moment, bar, position in the bar, MIDI pitch, staff);
  * the MIDI file (what is played, with repeats unfolded, and the tempo).

Each MIDI chord is matched to a printed chord (same pitches), preferring the
next one in the score, so an unfolded repeat jumps back to the printed bars.
Tied-to note heads are not matched (they are not struck again).

The note map (JSON) is a list of events in playing order:
    {"i", "tick", "beat", "sec", "pitches", "page", "fx", "fy", "bar", "beat_in_bar"}
fx, fy are fractions of the page image (0..1 from the top left), so they fit
the image at whatever size it is shown.  page is None when a played chord
could not be found on the sheet.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from fractions import Fraction

try:                                   # inside Django: bells.chime_midi
    from . import chime_midi
except ImportError:                    # chime-build: plain module on sys.path
    import chime_midi

NOTEMAP_FORMAT = "sandbells-chime-notemap"
NOTEMAP_VERSION = 1

# The Sandbach handbells: bell 1 (treble) to bell 8 (tenor), one octave of
# F major, F5 down to F4.  From the bell numbers the tunes print over each
# note (boars-head-carol.ly: "1" over f'', "8" over f').  Strict: a note is
# a bell only at exactly this pitch, no octave folding, no transposition.
BELLS_8 = (77, 76, 74, 72, 70, 69, 67, 65)
BELL_NUMBER = {pitch: n for n, pitch in enumerate(BELLS_8, start=1)}

QUARTERS_PER_WHOLE = chime_midi.QUARTERS_PER_WHOLE
FIRST_BEAT = 1
MATCH_LOOKAHEAD = 8                    # chords compared when choosing where a chord is
TSV_COLUMNS = ("page", "paper_w", "paper_h", "x1", "x2", "y1", "y2",
               "moment", "bar", "bar_pos", "midi", "pitch", "staff", "length")
TSV_TIED = "tied"                      # optional column (1 = tied-to note head)
LILY_NOTE_LETTERS = "CDEFGAB"
LILY_ALTERATIONS = {Fraction(-1): "bb", Fraction(-1, 2): "b", Fraction(0): "",
                    Fraction(1, 2): "#", Fraction(1): "##"}
LILY_OCTAVE_OF_MIDDLE_C = 4            # LilyPond octave 0 is c' = C4


class NotemapError(ValueError):
    """A note-head table or note map that cannot be used."""


@dataclass
class Head:
    page: int
    fx: float
    fy: float
    fw: float
    fh: float
    moment: Fraction
    bar: int
    bar_pos: Fraction
    midi: int
    name: str
    staff: str
    length: Fraction
    tied: bool = False                 # the tied-to end of a tie: printed, not played


@dataclass
class PrintedChord:
    moment: Fraction
    pitches: tuple
    heads: list = field(default_factory=list)

    @property
    def page(self):
        return self.heads[0].page

    def dot(self):
        """Where the dot goes: across the middle of the chord, on its top note."""
        top = min(self.heads, key=lambda h: h.fy)
        xs = [h.fx for h in self.heads if h.page == top.page]
        return top.page, sum(xs) / len(xs), top.fy


def lily_pitch_name(spec: str, midi: int) -> str:
    """'notename:alteration:octave' from the .ily as e.g. Bb4."""
    try:
        n, alt, octave = spec.split(":")
        return "%s%s%d" % (LILY_NOTE_LETTERS[int(n)], LILY_ALTERATIONS[Fraction(alt)],
                           int(octave) + LILY_OCTAVE_OF_MIDDLE_C)
    except (ValueError, KeyError, IndexError):
        return chime_midi.pitch_name(midi)


def parse_heads(tsv_text: str) -> list:
    """The .ily's table as Heads, page fractions from the top left."""
    rows = list(csv.DictReader(io.StringIO(tsv_text), delimiter="\t"))
    if rows and set(TSV_COLUMNS) - set(rows[0]):
        raise NotemapError("note-head table lacks columns %s"
                           % sorted(set(TSV_COLUMNS) - set(rows[0])))
    heads = []
    for r in rows:
        try:
            pw, ph = float(r["paper_w"]), float(r["paper_h"])
            x1, x2, y1, y2 = (float(r[k]) for k in ("x1", "x2", "y1", "y2"))
            midi = int(r["midi"])
            heads.append(Head(
                page=int(r["page"]),
                fx=(x1 + x2) / 2 / pw, fy=-(y1 + y2) / 2 / ph,
                fw=abs(x2 - x1) / pw, fh=abs(y2 - y1) / ph,
                moment=Fraction(r["moment"]), bar=int(r["bar"]),
                bar_pos=Fraction(r["bar_pos"]), midi=midi,
                name=lily_pitch_name(r["pitch"], midi), staff=r["staff"],
                length=Fraction(r["length"]),
                tied=(r.get(TSV_TIED) or "0").strip() == "1"))
        except (ValueError, ZeroDivisionError, KeyError) as e:
            raise NotemapError("bad note-head row %r: %s" % (r, e))
    return heads


def printed_chords(heads: list) -> list:
    """Chords as printed, in score order.  Tied-to heads are left out: the
    MIDI does not strike them again."""
    by_moment = {}
    for h in heads:
        if h.tied:
            continue
        by_moment.setdefault(h.moment, []).append(h)
    return [PrintedChord(m, tuple(sorted({h.midi for h in hs})), hs)
            for m, hs in sorted(by_moment.items())]


def _run(played, i, printed, j):
    """How many chords from here on agree (pitches equal), up to the lookahead."""
    k = 0
    while (k < MATCH_LOOKAHEAD and i + k < len(played) and j + k < len(printed)
           and played[i + k][2] == printed[j + k].pitches):
        k += 1
    return k


def align(played: list, printed: list) -> list:
    """For each played chord (tick, sec, pitches) the index of its printed chord,
    or None.  Next-in-score wins unless another place agrees for longer
    (a repeat going back, a tie or grace note skipped)."""
    out, last = [], -1
    for i, chord in enumerate(played):
        cands = [j for j, p in enumerate(printed) if p.pitches == chord[2]]
        if not cands:
            cands = [j for j, p in enumerate(printed) if set(chord[2]) & set(p.pitches)]
        if not cands:
            out.append(None)
            continue
        scored = [(_run(played, i, printed, j), j) for j in cands]
        best = max(s for s, _ in scored)
        ahead = [j for s, j in scored if s == best and j > last]
        j = min(ahead) if ahead else min((j for s, j in scored if s == best),
                                         key=lambda j: abs(j - last))
        out.append(j)
        last = j
    return out


def beat_in_bar(bar_pos: Fraction) -> float:
    return float(FIRST_BEAT + bar_pos * QUARTERS_PER_WHOLE)


def bell_check(heads: list, played_notes: list = (), bells=BELLS_8) -> list:
    """Every note not on a bell: printed ones with bar and beat, then played
    ones (MIDI) the score does not show.  Empty list: the tune fits the bells."""
    allowed = set(bells)
    problems, seen = [], set()
    for h in sorted(heads, key=lambda h: (h.moment, h.midi)):
        if h.midi not in allowed and (h.moment, h.midi) not in seen:
            seen.add((h.moment, h.midi))
            problems.append({"bar": h.bar, "beat": beat_in_bar(h.bar_pos),
                             "pitch": h.name, "midi": h.midi, "staff": h.staff})
    printed = {h.midi for h in heads}
    for n in played_notes:
        if n.pitch not in allowed and n.pitch not in printed:
            problems.append({"bar": None, "beat": None, "sec": round(n.sec, 3),
                             "pitch": chime_midi.pitch_name(n.pitch), "midi": n.pitch,
                             "staff": "midi"})
    return problems


def describe_problem(p: dict) -> str:
    where = ("bar %s beat %g" % (p["bar"], p["beat"]) if p.get("bar") is not None
             else "%.2f s into the MIDI" % p.get("sec", 0))
    return "%s: %s (MIDI %d) is not one of the 8 bells" % (where, p["pitch"], p["midi"])


def build(heads: list, mf: "chime_midi.MidiFile", title: str = "",
          page_sizes: dict = None) -> dict:
    """The note map for one tune."""
    played_notes = chime_midi.notes(mf)
    played = chime_midi.chords(played_notes)
    printed = printed_chords(heads)
    where = align(played, printed)
    tm = chime_midi.TempoMap(mf)
    events = []
    for i, ((tick, sec, pitches), j) in enumerate(zip(played, where)):
        ev = {"i": i, "tick": tick, "beat": round(tick / mf.ppq, 4), "sec": round(sec, 4),
              "pitches": list(pitches), "page": None, "fx": None, "fy": None,
              "bar": None, "beat_in_bar": None}
        if j is not None:
            page, fx, fy = printed[j].dot()
            ev.update(page=page, fx=round(fx, 5), fy=round(fy, 5),
                      bar=printed[j].heads[0].bar,
                      beat_in_bar=beat_in_bar(printed[j].heads[0].bar_pos))
        events.append(ev)
    pages = sorted({h.page for h in heads})
    return {
        "format": NOTEMAP_FORMAT, "version": NOTEMAP_VERSION, "title": title,
        "ppq": mf.ppq, "bpm": round(tm.first_bpm(), 3),
        "duration_sec": round(max((n.end_sec for n in played_notes), default=0.0), 4),
        "pages": pages, "page_sizes": page_sizes or {},
        "bells": list(BELLS_8),
        "out_of_set": bell_check(heads, played_notes),
        "unplaced": sum(1 for j in where if j is None),
        "events": events,
    }


def load(text: str) -> dict:
    """A note map from JSON, checked enough for the player to trust it."""
    try:
        data = json.loads(text)
    except ValueError as e:
        raise NotemapError("note map is not JSON: %s" % e)
    if not isinstance(data, dict) or data.get("format") != NOTEMAP_FORMAT:
        raise NotemapError("not a Sandbells chime note map")
    events = data.get("events")
    if not isinstance(events, list):
        raise NotemapError("note map has no events")
    last = -1.0
    for ev in events:
        if not isinstance(ev, dict) or not isinstance(ev.get("sec"), (int, float)):
            raise NotemapError("note map event without a time: %r" % (ev,))
        if ev["sec"] < last:
            raise NotemapError("note map events are not in time order")
        last = ev["sec"]
        if ev.get("page") is not None:
            if not all(isinstance(ev.get(k), (int, float)) and 0 <= ev[k] <= 1
                       for k in ("fx", "fy")):
                raise NotemapError("note map event off its page: %r" % (ev,))
    return data


def event_at(events: list, sec: float):
    """Index of the last event at or before sec (written time), or -1."""
    lo, hi = 0, len(events)
    while lo < hi:
        mid = (lo + hi) // 2
        if events[mid]["sec"] <= sec:
            lo = mid + 1
        else:
            hi = mid
    return lo - 1
