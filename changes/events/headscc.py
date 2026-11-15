"""headscc.py -- the sandheads readings / acks the Pico sends as MIDI
Control Change (sandswing heads_cc.py) -> sand.panel/v1 align / align_ack
docs, the same the page gets over /ws.  ingest_midi feeds every CcMessage
to HeadsCcDecoder.cc(); each whole report (CC_HEAD .. CC_SEQ on
HEADS_CC_CHANNEL) becomes one doc for MIDI_HEADS_PATH (serialheads.HeadsFile).
No Django import.  Map: sandswing docs/align-scope.md "MIDI CC map".

A report while strokes are in progress carries only the PT level: the
other readings are the head's last ones, marked busy.  The trace is one
sample per report (low if the beam was broken at any sample since the
last report), the last HEADS_TRACE_MS of them: coarse, but it shows a
break.
"""

import binascii
import os
import time
from collections import deque

from . import constants as C


def midi_heads_path():
    return os.environ.get(C.MIDI_HEADS_ENV) or C.MIDI_HEADS_PATH


def _v14(raw, cc):
    if cc not in raw or cc + C.HEADS_CC_LSB not in raw:
        return None
    v = (raw[cc] << 7) | raw[cc + C.HEADS_CC_LSB]
    return None if v == C.HEADS_CC_NONE else v


def _duty(v):
    return None if v is None else int(round(v * C.HEADS_DUTY_FULL / C.HEADS_CC_MAX))


def _ma(v):
    return None if v is None else v / C.HEADS_MA_UNITS


def _on_ma(ma, drv):
    """The laser current while on: CC_MA is the Pico's AVERAGE over whole
    PWM periods (sandswing tune.py), so divide by the drive duty (CC_DRV).
    None at duty 0 or without both."""
    if ma is None or not drv:
        return None
    return round(ma * C.HEADS_DUTY_FULL / drv, C.HEADS_MA_DP)


def _volts(v):
    return None if v is None else v / C.HEADS_MV_PER_V


def bits_hex(bits):
    """[1, 0, ...] oldest first -> MSB-first hex (align.js decodeRuns)."""
    pack = bytearray((len(bits) + 7) // 8)
    for j, b in enumerate(bits):
        if b:
            pack[j >> 3] |= 0x80 >> (j & 7)
    return binascii.hexlify(bytes(pack)).decode()


class HeadsCcDecoder:
    """cc(msg, utc_ms) -> calls out(doc) for every whole report."""

    def __init__(self, out, channel=C.HEADS_CC_CHANNEL):
        self.out = out
        self.channel = channel
        self.raw = None
        self.last = {}            # ch -> {"thr", "rb", "drv", "ma"}
        self.trace = {}           # ch -> deque of (utc_ms, bit)
        self.reports = 0
        self.partial = 0          # a report cut short (a new CC_HEAD before its CC_SEQ)
        self.ignored = 0          # other channels / CCs outside a report

    def cc(self, msg, utc_ms):
        if msg.channel != self.channel:
            self.ignored += 1
            return None
        if msg.cc == C.HEADS_CC_HEAD:
            if self.raw is not None:
                self.partial += 1
            self.raw = {msg.cc: msg.value}
            return None
        if self.raw is None:
            self.ignored += 1
            return None
        self.raw[msg.cc] = msg.value
        if msg.cc != C.HEADS_CC_SEQ:
            return None
        raw, self.raw = self.raw, None
        doc = self.doc(raw, utc_ms)
        self.reports += 1
        if doc is not None:
            self.out(doc)
        return doc

    def doc(self, raw, utc_ms):
        ch = raw.get(C.HEADS_CC_HEAD)
        flags = raw.get(C.HEADS_CC_FLAGS, 0)
        tower = C.HEADS_TOWER_QUIET if flags & C.HEADS_FLAG_QUIET else C.HEADS_TOWER_BUSY
        if C.HEADS_CC_ACK_WHAT in raw:
            why = raw.get(C.HEADS_CC_ACK_WHY, 0)
            body = {"what": C.HEADS_WHAT.get(raw[C.HEADS_CC_ACK_WHAT], "bad"),
                    "ch": ch or None, "ok": why == 0,
                    "why": None if why == 0 else C.HEADS_WHY.get(why, C.HEADS_WHY[127]),
                    "thr": _duty(_v14(raw, C.HEADS_CC_THR)),
                    "drv": _duty(_v14(raw, C.HEADS_CC_DRV)), "tower": tower, "via": "midi"}
            return {"schema": C.SERIAL_HB_SCHEMA, "type": "align_ack", "body": body}
        if not ch:
            return None
        last = self.last.setdefault(ch, {"thr": None, "rb": None, "drv": None, "ma": None})
        full = C.HEADS_CC_THR in raw
        if full:
            last.update(thr=_duty(_v14(raw, C.HEADS_CC_THR)),
                        rb=_duty(_v14(raw, C.HEADS_CC_RB)),
                        drv=_duty(_v14(raw, C.HEADS_CC_DRV)), ma=_ma(_v14(raw, C.HEADS_CC_MA)))
        bit = 1 if (flags & C.HEADS_FLAG_CLEAR and not flags & C.HEADS_FLAG_BROKE) else 0
        tr = self.trace.setdefault(ch, deque(maxlen=C.HEADS_TRACE_MAX))
        tr.append((utc_ms, bit))
        while tr and utc_ms - tr[0][0] > C.HEADS_TRACE_MS:
            tr.popleft()
        n = len(tr)
        dt = (tr[-1][0] - tr[0][0]) / (n - 1) if n > 1 else 0
        body = {"ch": ch, "n": n, "dt": round(dt, 1), "gap": int(dt),
                "bits": bits_hex([b for _, b in tr]),
                "ma": last["ma"], "ma_on": _on_ma(last["ma"], last["drv"]), "rb": last["rb"], "thr": last["thr"], "drv": last["drv"],
                "pt": _volts(_v14(raw, C.HEADS_CC_PT)),
                "pt_span": _volts(_v14(raw, C.HEADS_CC_PT_SPAN)),
                "tower": tower, "busy": bool(flags & C.HEADS_FLAG_BUSY) or not full,
                "seq": raw.get(C.HEADS_CC_SEQ), "via": "midi"}
        return {"schema": C.SERIAL_HB_SCHEMA, "type": "align", "body": body}
