#!/usr/bin/env python3
"""zss2ly.py -- pull zynseq sequences out of a Zynthian snapshot (.zss) and
write a report, a standard MIDI file and a draft Sandbells chime .ly.

    python3 zss2ly.py SNAPSHOT.zss [-o OUTDIR] [--name NAME]

Handles both snapshot formats:
  * zynthian-ui oram (v5): state["zynseq_riff_b64"] = base64 RIFF-like blocks
    vers/patn/bank (big-endian, layout from zynlibs/zynseq/zynseq.cpp load()).
  * zynthian-ui vangelis/master: state["zynseq"] = JSON (getState()):
    patns{id:{beats,steps,events[[step,offset,dur,cmd,v1s,v1e,v2s,v2e,...]]}},
    scenes[{phrases[{bpb,tempo,sequences[{name,tracks[{chan,patns{pos:id}}]}]}]}]
Nothing is transposed in the main output.  If every note fits the 8 bells after
an octave shift, an extra *-octN.ly is written and flagged as a guess.
"""
import argparse, base64, json, os, re, struct, sys
from fractions import Fraction as F
from pathlib import Path

BELLS = {77: 1, 76: 2, 74: 3, 72: 4, 70: 5, 69: 6, 67: 7, 65: 8}  # F5..F4, C4=60
NAMES = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B']
LY = ['c', 'cs', 'd', 'ef', 'e', 'f', 'fs', 'g', 'af', 'a', 'bf', 'b']
NOTE_ON = 0x90


def nname(n):
    return f"{NAMES[n % 12]}{n // 12 - 1}"


# ---------------------------------------------------------------- RIFF (oram)
class R:
    def __init__(s, b): s.b, s.i = b, 0
    def u8(s): v = s.b[s.i]; s.i += 1; return v
    def u16(s): v = struct.unpack_from('>H', s.b, s.i)[0]; s.i += 2; return v
    def s16(s): v = struct.unpack_from('>h', s.b, s.i)[0]; s.i += 2; return v
    def u32(s): v = struct.unpack_from('>I', s.b, s.i)[0]; s.i += 4; return v
    def bcd(s): fr = s.u16(); return fr / 10000 + s.s16()


def parse_riff(data):
    st = {'tempo': None, 'bpb': None, 'patns': {}, 'seqs': [], 'format': 'riff'}
    r, ver = R(data), 0
    while r.i + 8 <= len(data):
        hdr = data[r.i:r.i + 4].decode('latin1'); r.i += 4
        size = r.u32(); end = r.i + size
        if hdr == 'vers':
            ver = r.u32(); st['version'] = ver
            st['tempo'] = r.u16(); st['bpb'] = r.u16()
        elif hdr == 'patn':
            p = {'id': r.u32(), 'beats': r.u32(), 'spb': r.u16()}
            p['scale'] = r.u8(); p['tonic'] = r.u8()
            if ver > 4: p['refNote'] = r.u8()
            if ver > 8:
                p['quantize'] = r.u8(); p['swingDiv'] = r.u8()
                p['swing'] = r.bcd(); p['humanTime'] = r.bcd(); p['humanVel'] = r.bcd(); p['chance'] = r.bcd()
            if ver > 4: r.u8()
            ev, esz = [], (21 if ver > 8 else 16 if ver > 7 else 14)
            while end - r.i >= esz:
                step = r.u32()
                if ver > 8: off = r.bcd(); dur = r.bcd()
                else: off = 0.0; dur = r.u16() / 100 + r.s16()
                cmd, v1, v2, v1e, v2e = (r.u8() for _ in range(5))
                if ver > 7: r.u8(); r.u8()
                if ver > 8: r.u8()
                r.u8()
                ev.append({'step': step, 'off': off, 'dur': dur, 'cmd': cmd, 'v1': v1, 'v2': v2})
            p['events'] = ev
            p['steps'] = p['beats'] * p['spb']
            st['patns'][p['id']] = p
        elif hdr == 'bank':
            bank = r.u8(); r.u8(); nseq = r.u32()
            for sq in range(nseq):
                mode, group, trig, _ = r.u8(), r.u8(), r.u8(), r.u8()
                name = data[r.i:r.i + 16].split(b'\0')[0].decode('latin1') if ver > 5 else str(sq + 1)
                if ver > 5: r.i += 16
                ntr = r.u32(); tracks = []
                for t in range(ntr):
                    if ver > 9: r.u8(); r.u8()
                    chan, out, mp, _ = r.u8(), r.u8(), r.u8(), r.u8()
                    npat = r.u16(); pats = {}
                    for _ in range(npat):
                        pos = r.u32(); pid = r.u32(); pats[pos] = pid
                    tracks.append({'chan': chan, 'patns': pats})
                ntb = r.u32(); tb = []
                for _ in range(ntb):
                    tb.append({'bar': r.u16(), 'tick': r.u16(), 'type': r.u16(), 'value': r.u16()})
                st['seqs'].append({'where': f'bank {bank} seq {sq}', 'name': name, 'mode': mode,
                                   'group': group, 'tracks': tracks, 'timebase': tb,
                                   'bpb': st['bpb'], 'tempo': st['tempo']})
        r.i = end
    return st


# ---------------------------------------------------------------- JSON (master)
def parse_json(j):
    if isinstance(j, str): j = json.loads(j)
    st = {'tempo': j.get('tempo'), 'bpb': j.get('bpb'), 'patns': {}, 'seqs': [], 'format': 'json'}
    for pid, p in (j.get('patns') or {}).items():
        beats = p.get('beats', 4); steps = p.get('steps', beats * 4)
        ev = [{'step': e[0], 'off': e[1], 'dur': e[2], 'cmd': e[3], 'v1': e[4], 'v2': e[6]} for e in p.get('events', [])]
        st['patns'][int(pid)] = {'id': int(pid), 'beats': beats, 'spb': steps // beats if beats else 4,
                                 'steps': steps, 'events': ev,
                                 **{k: p.get(k) for k in ('scale', 'tonic', 'quantize', 'swing')}}
    for sc, scene in enumerate(j.get('scenes') or []):
        for ph, phrase in enumerate(scene.get('phrases') or []):
            for sq, seq in enumerate(phrase.get('sequences') or []):
                if not seq: continue
                tracks = [{'chan': t.get('chan'), 'patns': {int(k): v for k, v in (t.get('patns') or {}).items()}}
                          for t in seq.get('tracks') or []]
                st['seqs'].append({'where': f'scene {sc} phrase {ph} ({phrase.get("name","")}) seq {sq}',
                                   'name': seq.get('name', ''), 'mode': seq.get('mode'), 'group': seq.get('group'),
                                   'tracks': tracks, 'timebase': seq.get('timebase', []),
                                   'bpb': phrase.get('bpb') or st['bpb'],
                                   'tempo': phrase.get('tempo') or st['tempo']})
    return st


def load(path):
    snap = json.loads(Path(path).read_text())
    if 'zynseq' in snap: return snap, parse_json(snap['zynseq'])
    if 'zynseq_riff_b64' in snap: return snap, parse_riff(base64.b64decode(snap['zynseq_riff_b64']))
    sys.exit(f'{path}: no zynseq / zynseq_riff_b64 key; top-level keys: {list(snap)}')


# ---------------------------------------------------------------- timeline
def clocks_per_beat(track, patns):
    """Track positions are sequencer clocks; PPQN differs by version (24/96/1920)."""
    pos = sorted(track['patns'])
    for q in (1920, 96, 24):
        ok = all(p % (q // max(1, patns[track['patns'][p]]['spb']) or 1) == 0 for p in pos if track['patns'][p] in patns)
        ok = ok and all(pos[i] + patns[track['patns'][pos[i]]]['beats'] * q <= pos[i + 1]
                        for i in range(len(pos) - 1) if track['patns'][pos[i]] in patns)
        if ok and (not pos or pos[-1] < 10000 * q): return q
    return None


def seq_notes(seq, patns):
    """-> list of (start_beats Fraction, dur_beats Fraction, note, vel, chan, pid, step)."""
    out = []
    for t in seq['tracks']:
        q = clocks_per_beat(t, patns)
        if q is None: q = 24
        t['ppqn_guess'] = q
        for pos, pid in sorted(t['patns'].items()):
            p = patns.get(pid)
            if not p: continue
            base = F(pos, q)
            for e in p['events']:
                if e['cmd'] != NOTE_ON or e['v2'] == 0: continue
                spb = p['spb']
                st = base + (F(e['step']) + F(e['off']).limit_denominator(64)) / spb
                du = F(e['dur']).limit_denominator(64) / spb
                out.append((st, du, e['v1'], e['v2'], t['chan'], pid, e['step']))
    return sorted(out)


# ---------------------------------------------------------------- MIDI
def vlq(n):
    b = [n & 0x7F]; n >>= 7
    while n: b.insert(0, 0x80 | (n & 0x7F)); n >>= 7
    return bytes(b)


def write_midi(path, notes, tempo, bpb, tpq=480, shift=0):
    evs = []
    for st, du, n, v, ch, *_ in notes:
        a = int(st * tpq); b = int((st + du) * tpq)
        evs.append((a, 1, bytes([0x90 | (ch & 15), n + shift, v])))
        evs.append((max(b, a + 1), 0, bytes([0x80 | (ch & 15), n + shift, 0])))
    evs.sort(key=lambda e: (e[0], e[1]))
    us = int(round(60_000_000 / (tempo or 120)))
    trk = b'\x00\xFF\x51\x03' + us.to_bytes(3, 'big')
    trk += b'\x00\xFF\x58\x04' + bytes([bpb or 4, 2, 24, 8])
    trk += b'\x00\xFF\x59\x02' + bytes([0xFF, 0])  # key: 1 flat (F major), major
    t0 = 0
    for t, _, m in evs:
        trk += vlq(t - t0) + m; t0 = t
    trk += b'\x00\xFF\x2F\x00'
    Path(path).write_bytes(b'MThd' + struct.pack('>IHHH', 6, 0, 1, tpq) + b'MTrk' + struct.pack('>I', len(trk)) + trk)


# ---------------------------------------------------------------- LilyPond
DUR = {F(4): '1', F(3): '2.', F(2): '2', F(3, 2): '4.', F(1): '4', F(3, 4): '8.', F(1, 2): '8',
       F(3, 8): '16.', F(1, 4): '16', F(1, 8): '32', F(7, 2): '2..', F(7, 4): '4..', F(6): '1.'}


def split_dur(d):
    out = []
    for v in sorted(DUR, reverse=True):
        while d >= v: out.append(DUR[v]); d -= v
    if d: out.append(None)
    return out


def ly_pitch(n):
    pc, octv = LY[n % 12], n // 12 - 1
    return pc + ("'" * (octv - 3) if octv >= 3 else "," * (3 - octv))


# Front-page list: changes/bells/static/js/bell_band.js  BELL_COLOURS
# (blank.html / the bells page loads that file). Read from the file when it
# is found; this copy is the fallback so the scripts still run offline.
# Do not edit the numbers by hand — copy them from that file.
BELL_COLOURS_FALLBACK = {
    1: "#ff2020", 2: "#ff8c00", 3: "#ffd000", 4: "#22c022",
    5: "#00d4d4", 6: "#2050ff", 7: "#e000e0", 8: "#8b0000",
}
# LilyPond notename 0=C..6=B, alteration, octave 0 = C4-B4. MIDI 60 = C4.
PC_LY = (
    (0, 'NATURAL'), (0, 'SHARP'), (1, 'NATURAL'), (2, 'FLAT'),
    (2, 'NATURAL'), (3, 'NATURAL'), (3, 'SHARP'), (4, 'NATURAL'),
    (5, 'FLAT'), (5, 'NATURAL'), (6, 'FLAT'), (6, 'NATURAL'),
)
_bell_colours_cache = None


def bell_band_candidates():
    out = []
    envf = os.environ.get('SANDBELLS_BELL_BAND')
    if envf:
        out.append(Path(envf))
    roots = []
    for e in ('SANDBELLS', 'SANDBELLS_ROOT'):
        if os.environ.get(e):
            roots.append(Path(os.environ[e]))
    # When this file lives in tools/chimes, parents[1] is the Sandbells root.
    here = Path(__file__).resolve()
    if here.parent.name == 'chimes' and here.parents[1].name:
        roots.append(here.parents[1])
    roots += [
        Path('/workspace/chimes-work/Sandbells'),
        Path.home() / 'Code' / 'Sandbells',
        Path.home() / 'Sandbells',
    ]
    rel = Path('changes/bells/static/js/bell_band.js')
    out.extend(r / rel for r in roots)
    return out


def parse_bell_colours(text):
    m = re.search(r'BELL_COLOURS\s*=\s*\{([^}]*)\}', text)
    if not m:
        return None
    found = {int(a): '#' + b.lower()
             for a, b in re.findall(r'(\d+)\s*:\s*"#([0-9A-Fa-f]{6})"', m.group(1))}
    if set(found) != set(range(1, 9)):
        return None
    return found


def load_bell_colours():
    """-> (bell_number -> '#rrggbb', source description)."""
    global _bell_colours_cache
    if _bell_colours_cache is not None:
        return _bell_colours_cache
    for p in bell_band_candidates():
        if p.is_file():
            got = parse_bell_colours(p.read_text())
            if got:
                _bell_colours_cache = (got, str(p))
                return _bell_colours_cache
    _bell_colours_cache = (dict(BELL_COLOURS_FALLBACK),
                           'embedded fallback (bell_band.js not found)')
    return _bell_colours_cache


def ly_pitch_scheme(midi):
    name, alt = PC_LY[midi % 12]
    octv = midi // 12 - 5
    return f'(ly:make-pitch {octv} {name} {alt})'


def hex_rgb_scheme(hx):
    hx = hx.lstrip('#')
    r, g, b = (int(hx[i:i + 2], 16) for i in (0, 2, 4))
    return f'(rgb-color (/ {r} 255) (/ {g} 255) (/ {b} 255))'


def colours_ily():
    colours, src = load_bell_colours()
    inv = {bell: midi for midi, bell in BELLS.items()}
    lines = []
    for bell in range(1, 9):
        midi = inv[bell]
        hx = colours[bell]
        lines.append(
            f'    (cons {ly_pitch_scheme(midi)} {hex_rgb_scheme(hx)})'
            f' ; bell {bell} {nname(midi)} {hx}'
        )
    block = (
        '% Bell colours from the Sandbells front page,\n'
        '% changes/bells/static/js/bell_band.js  BELL_COLOURS\n'
        f'% (this copy: {src}).\n'
        '% Coloured by bell number (pitch and octave), so F5 and F4 differ.\n'
        '#(define color-mapping\n'
        '   (list\n'
        + '\n'.join(lines) + '\n'
        '    ))\n'
        '#(define (pitch-to-color pitch)\n'
        '   (let ((color (assoc pitch color-mapping equal?)))\n'
        '     (if color (cdr color))))\n'
        '\n'
        '#(define (color-notehead grob)\n'
        '   (pitch-to-color\n'
        "    (ly:event-property (event-cause grob) 'pitch)))\n"
    )
    return block, src



def write_ly(path, title, notes, tempo, bpb, shift=0, note='', fill=False, ends=(), one_page=True):
    """fill: each chord lasts to the next onset, bar line or phrase end (onsets unchanged).
    one_page: house layout (Chirpy Chirpy): A4 landscape, staff size 48, one page."""
    # group onsets into chords; a chord sounds until the next onset (bells ring on),
    # but if it was shorter than the gap the rest of the gap is a rest.
    on = {}
    for st, du, n, *_ in notes: on.setdefault(st, []).append((n + shift, du))
    times = sorted(on)
    bar = F(bpb or 4)
    items = []  # (start, length, pitches or None)
    cur = F(0)
    for i, t in enumerate(times):
        if t > cur: items.append((cur, t - cur, None))
        nxt = times[i + 1] if i + 1 < len(times) else None
        d = max(du for _, du in on[t])
        if nxt is not None and d >= nxt - t: d = nxt - t
        if fill:
            stops = [x for x in ([nxt] if nxt is not None else []) + list(ends) if x is not None and x > t]
            stops.append((t // bar + 1) * bar)
            d = max(d, min(stops) - t)
        items.append((t, d, sorted({p for p, _ in on[t]})))
        cur = t + d
    end = -(-cur // bar) * bar if cur else bar
    if end > cur: items.append((cur, end - cur, None))
    body, lyr, bad = [], [], []
    for st, ln, ps in items:
        pos = st
        segs = []
        while ln > 0:
            room = bar - (pos % bar)
            seg = min(ln, room); segs.append((pos, seg)); pos += seg; ln -= seg
        for k, (p0, seg) in enumerate(segs):
            ds = split_dur(seg)
            for m, d in enumerate(ds):
                if d is None: bad.append(str(p0)); continue
                if ps is None: body.append('r' + d)
                else:
                    pit = ps[0] and (ly_pitch(ps[0]) if len(ps) == 1 else '<' + ' '.join(ly_pitch(x) for x in ps) + '>')
                    last = (k == len(segs) - 1 and m == len(ds) - 1)
                    body.append(pit + d + ('' if last else '~'))
            if (p0 + seg) % bar == 0: body.append('|\n   ')
        if ps is not None:
            lyr.append('"' + '/'.join(str(BELLS.get(x, '?' + nname(x))) for x in sorted(ps, reverse=True)) + '"')
    num, den = (bpb or 4), 4
    # House page, copied from Chirpy-chirpy-cheep-cheep.ly:
    #   #(set-global-staff-size 48)
    #   \paper { #(set-paper-size "a4landscape") }
    #   no empty subtitle, bell numbers not \tiny, empty \layout.
    # one_page adds page-count = 1 and turns off ragged bottoms so a
    # longer tune (Little Donkey, 14 bars) stays on one page at size 48.
    paper = '  #(set-paper-size "a4landscape")\n'
    if one_page:
        paper += ('  page-count = 1\n'
                  '  ragged-bottom = ##f\n'
                  '  ragged-last-bottom = ##f\n')
    txt = f'''\\version "2.24.1"
\\language "english"
#(set-global-staff-size 48)
% DRAFT generated by zss2ly.py from a zynseq snapshot. {note}
% Bell numbers: F5=1 E5=2 D5=3 C5=4 Bb4=5 A4=6 G4=7 F4=8.

\\header {{
    title = "{title}"
    tagline = "Sandbells"
}}
{colours_ily()[0]}
\\paper {{
{paper}}}

tune = {{
  \\override NoteHead.color = #color-notehead
  \\clef treble
  \\key f \\major
  \\numericTimeSignature \\time {num}/{den}
   {' '.join(body).strip()}
  \\bar "|."
}}

\\score {{
  <<
  \\new Staff = "bells" \\with {{
  instrumentName = "Bells"
  midiInstrument = "tubular bells"
  }}
  \\new Voice = "bells" \\tune
  \\new Lyrics \\with {{ alignAboveContext = "bells" }} {{
    \\lyricsto "bells" {{
      {' '.join(lyr)}
    }}
  }}
  >>
  \\layout {{ }}
}}
\\score {{
  \\unfoldRepeats {{ \\tune }}
  \\midi {{
    \\tempo 4={int(round(tempo or 100))}
  }}
}}
'''
    Path(path).write_text(txt)
    return bad


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('zss'); ap.add_argument('-o', default='.'); ap.add_argument('--name')
    a = ap.parse_args()
    out = Path(a.o); out.mkdir(parents=True, exist_ok=True)
    snap, st = load(a.zss)
    name = a.name or Path(a.zss).stem
    rep = [f'# {a.zss}', f'format: {st["format"]} version: {st.get("version")}  global tempo: {st["tempo"]}  bpb: {st["bpb"]}',
           f'snapshot top-level keys: {", ".join(snap)}']
    chains = snap.get('chains') or {}
    if chains: rep.append(f'chains: {json.dumps({k: {kk: v.get(kk) for kk in ("title","midi_chan","midi_thru") if kk in v} for k, v in chains.items()})[:600]}')
    used = set()
    for s in st['seqs']:
        for t in s['tracks']: used |= set(t['patns'].values())
    rep.append('\n## Patterns')
    for pid, p in sorted(st['patns'].items()):
        nev = [e for e in p['events'] if e['cmd'] == NOTE_ON]
        if not p['events']: continue
        rep.append(f'pattern {pid}{" (used)" if pid in used else " (not placed in any sequence)"}: beats={p["beats"]} spb={p["spb"]} steps={p["steps"]} events={len(p["events"])} notes={len(nev)}')
        for e in sorted(p['events'], key=lambda e: (e['step'], e['v1'])):
            if e['cmd'] == NOTE_ON:
                rep.append(f'   step {e["step"]:4}{"+%.2f" % e["off"] if e["off"] else "":6} {nname(e["v1"]):4} ({e["v1"]:3}) bell {BELLS.get(e["v1"], "--OFF--")!s:7} vel {e["v2"]:3} dur {e["dur"]:g} steps')
            else:
                rep.append(f'   step {e["step"]:4} cmd 0x{e["cmd"]:02X} {e["v1"]} {e["v2"]}')
    rep.append('\n## Sequences with patterns')
    made = []
    for idx, s in enumerate(st['seqs']):
        if not any(t['patns'] for t in s['tracks']): continue
        notes = seq_notes(s, st['patns'])
        rep.append(f'{s["where"]} name="{s["name"]}" mode={s["mode"]} group={s["group"]} tempo={s["tempo"]} bpb={s["bpb"]} timebase={s["timebase"]}')
        for t in s['tracks']:
            rep.append(f'   track chan={t["chan"]} (MIDI ch {t["chan"] + 1 if t["chan"] is not None else "?"}) ppqn_guess={t.get("ppqn_guess")} patterns at clock: {dict(sorted(t["patns"].items()))}')
        if not notes: continue
        off = sorted({n for _, _, n, *_ in notes if n not in BELLS})
        rep.append(f'   {len(notes)} notes; off the 8 bells: {[nname(n) for n in off] or "none"}')
        rep.append('   bells:  ' + ' '.join('/'.join(str(BELLS.get(x[2], nname(x[2]))) for x in notes if x[0] == t) for t in sorted({x[0] for x in notes})))
        rep.append('   pitches: ' + ' '.join(f'{nname(n)}@{float(t):g}' for t, _, n, *_ in notes))
        tag = f'{name}-seq{idx}'
        tempo = s['tempo'] or st['tempo'] or 100
        bpb = s['bpb'] or st['bpb'] or 4
        write_midi(out / f'{tag}.mid', notes, tempo, bpb)
        bad = write_ly(out / f'{tag}.ly', f'{name} {s["name"]}'.strip(), notes, tempo, bpb)
        made += [f'{tag}.mid', f'{tag}.ly']
        if bad: rep.append(f'   !! durations not expressible at beats {bad}')
        if off:
            for sh in (12, -12, 24, -24):
                if all(n + sh in BELLS for _, _, n, *_ in notes):
                    write_ly(out / f'{tag}-oct{sh:+d}.ly', f'{name} {s["name"]}'.strip(), notes, tempo, bpb, sh,
                             f'GUESS: shifted {sh:+d} semitones to fit the bells.')
                    write_midi(out / f'{tag}-oct{sh:+d}.mid', notes, tempo, bpb, shift=sh)
                    made += [f'{tag}-oct{sh:+d}.ly', f'{tag}-oct{sh:+d}.mid']
                    rep.append(f'   all notes fit the bells if shifted {sh:+d} semitones -> {tag}-oct{sh:+d}.ly (guess)')
    rep.append('\nfiles: ' + ', '.join(made))
    (out / f'{name}-report.txt').write_text('\n'.join(rep) + '\n')
    print('\n'.join(rep))


if __name__ == '__main__':
    main()
