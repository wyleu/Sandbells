"""parse.py -- one sand.event/v1 message -> ParsedEvent, or ParseError.

Pure: standard library only, no Django, no network.  Unknown event types
are accepted with known_type=False so they can still be stored.
"""

import ipaddress
import json
from dataclasses import dataclass, field

from . import constants as C


class ParseError(ValueError):
    """A message that cannot be stored.  reason is one of constants.R_*."""

    def __init__(self, reason, field_name=None, detail=""):
        self.reason = reason
        self.field = field_name
        self.detail = detail
        msg = reason if field_name is None else "%s: %s" % (reason, field_name)
        super().__init__(msg + (" (%s)" % detail if detail else ""))


@dataclass
class ParsedEvent:
    type: str
    src: str
    device_id: str
    boot_id: str
    seq: int
    tick_ms: int
    known_type: bool
    utc_ms: int = None
    err_ms: float = None
    acc: str = None
    sync: str = None
    mode: str = None
    epoch: int = None
    session: int = None
    srv: str = None
    stratum: int = None
    ch: int = None
    body: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _is_number(v):
    return _is_int(v) or isinstance(v, float)


def _load(raw):
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = bytes(raw).decode(C.TEXT_ENCODING)
        except UnicodeDecodeError as e:
            raise ParseError(C.R_NOT_UTF8, detail=str(e))
    try:
        doc = json.loads(raw)
    except (TypeError, ValueError) as e:
        raise ParseError(C.R_NOT_JSON, detail=str(e))
    if not isinstance(doc, dict):
        raise ParseError(C.R_NOT_OBJECT)
    return doc


def _required_str(doc, name):
    v = doc.get(name)
    if v is None:
        raise ParseError(C.R_MISSING, name)
    if not isinstance(v, str):
        raise ParseError(C.R_BAD_TYPE, name)
    if not v:
        raise ParseError(C.R_MISSING, name, "empty")
    if len(v) > C.MAX_LEN[name]:
        raise ParseError(C.R_TOO_LONG, name)
    return v


def _required_int(doc, name):
    v = doc.get(name)
    if v is None:
        raise ParseError(C.R_MISSING, name)
    if not _is_int(v):
        raise ParseError(C.R_BAD_TYPE, name)
    return v


def _optional_int(doc, name):
    v = doc.get(name)
    if v is not None and not _is_int(v):
        raise ParseError(C.R_BAD_TYPE, name)
    return v


def _optional_number(doc, name):
    v = doc.get(name)
    if v is None:
        return None
    if not _is_number(v):
        raise ParseError(C.R_BAD_TYPE, name)
    return float(v)


def _optional_choice(doc, name, allowed):
    v = doc.get(name)
    if v is None:
        return None
    if not isinstance(v, str):
        raise ParseError(C.R_BAD_TYPE, name)
    if v not in allowed:
        raise ParseError(C.R_BAD_VALUE, name, v)
    return v


def _optional_srv(doc):
    v = doc.get(C.F_SRV)
    if v is None:
        return None
    if not isinstance(v, str):
        raise ParseError(C.R_BAD_TYPE, C.F_SRV)
    try:
        ipaddress.ip_address(v)
    except ValueError:
        raise ParseError(C.R_BAD_VALUE, C.F_SRV, v)
    return v


def _body_and_ch(doc):
    body = doc.get(C.F_BODY)
    if body is None:
        return {}, None
    if not isinstance(body, dict):
        raise ParseError(C.R_BAD_TYPE, C.F_BODY)
    ch = body.get(C.BODY_CH)
    if ch is not None and not _is_int(ch):
        raise ParseError(C.R_BAD_TYPE, C.F_BODY + "." + C.BODY_CH)
    return body, ch


def parse(raw):
    """raw: str or bytes holding one JSON object.  -> ParsedEvent."""
    doc = _load(raw)
    if doc.get(C.F_SCHEMA) != C.SCHEMA_EVENT_V1:
        raise ParseError(C.R_BAD_SCHEMA, C.F_SCHEMA, repr(doc.get(C.F_SCHEMA)))

    strs = {n: _required_str(doc, n) for n in C.REQUIRED_STR_FIELDS}
    ints = {n: _required_int(doc, n) for n in C.REQUIRED_INT_FIELDS}
    if ints[C.F_SEQ] < C.SEQ_MIN:
        raise ParseError(C.R_BAD_VALUE, C.F_SEQ)

    opt = {n: _optional_int(doc, n) for n in C.OPTIONAL_INT_FIELDS}
    stratum = opt[C.F_STRATUM]
    if stratum is not None and not C.STRATUM_MIN <= stratum <= C.STRATUM_MAX:
        raise ParseError(C.R_BAD_VALUE, C.F_STRATUM)
    choice = {n: _optional_choice(doc, n, allowed)
              for n, allowed in C.OPTIONAL_CHOICE_FIELDS.items()}
    body, ch = _body_and_ch(doc)

    return ParsedEvent(
        type=strs[C.F_TYPE],
        src=strs[C.F_SRC],
        device_id=strs[C.F_ID],
        boot_id=strs[C.F_BOOT_ID],
        seq=ints[C.F_SEQ],
        tick_ms=ints[C.F_TICK_MS],
        known_type=strs[C.F_TYPE] in C.KNOWN_EVENT_TYPES,
        utc_ms=opt[C.F_UTC_MS],
        err_ms=_optional_number(doc, C.F_ERR_MS),
        acc=choice[C.F_ACC],
        sync=choice[C.F_SYNC],
        mode=choice[C.F_MODE],
        epoch=opt[C.F_EPOCH],
        session=opt[C.F_SESSION],
        srv=_optional_srv(doc),
        stratum=stratum,
        ch=ch,
        body=body,
        raw=doc,
    )
