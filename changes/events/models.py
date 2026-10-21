"""models.py -- one row per sand.event/v1 message.

Times are integer ms (BigInteger: utc_ms ~1.8e12 overflows 32 bits).
(src, boot_id, seq) is the natural key; re-sends are ignored on insert, so
DBs from sandbells and sandbells2 merge idempotently.  host records which
Sandbells received the row and is NOT part of the key.
"""

import socket
from datetime import datetime, timedelta, timezone

from django.db import models

from . import constants as C

UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def receiving_host():
    """Short hostname of this Sandbells (e.g. 'sandbells2'), truncated."""
    return socket.gethostname().split(".")[0][:C.HOST_MAX_LEN]


class Event(models.Model):
    src = models.CharField(max_length=C.SRC_MAX_LEN)
    device_id = models.CharField(max_length=C.DEVICE_ID_MAX_LEN,
                                 help_text="'id' on the wire")
    boot_id = models.CharField(max_length=C.BOOT_ID_MAX_LEN)
    seq = models.BigIntegerField()
    type = models.CharField(max_length=C.TYPE_MAX_LEN)
    ch = models.SmallIntegerField(null=True, blank=True)
    tick_ms = models.BigIntegerField()
    utc_ms = models.BigIntegerField(null=True, blank=True)
    err_ms = models.FloatField(null=True, blank=True)
    acc = models.CharField(max_length=C.CHOICE_MAX_LEN, null=True, blank=True)
    sync = models.CharField(max_length=C.CHOICE_MAX_LEN, null=True, blank=True)
    mode = models.CharField(max_length=C.CHOICE_MAX_LEN, null=True, blank=True)
    epoch = models.IntegerField(null=True, blank=True)
    session = models.IntegerField(null=True, blank=True)
    srv = models.CharField(max_length=C.SRV_MAX_LEN, null=True, blank=True)
    stratum = models.SmallIntegerField(null=True, blank=True)
    body = models.JSONField(default=dict, blank=True)
    raw = models.JSONField(default=dict, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    host = models.CharField(max_length=C.HOST_MAX_LEN, default="", blank=True,
                            help_text="Sandbells that received it")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["src", "boot_id", "seq"],
                                    name="event_src_boot_seq_uniq"),
        ]
        indexes = [
            models.Index(fields=["session", "utc_ms"],
                         name="event_session_utc_idx"),
            models.Index(fields=["utc_ms"], name="event_utc_idx"),
        ]

    def __str__(self):
        return "%s %s/%s #%s" % (self.type, self.src, self.boot_id, self.seq)

    @classmethod
    def from_parsed(cls, p, host=None):
        """Unsaved Event from a parse.ParsedEvent.  host defaults to this
        machine's hostname, read now (not at import)."""
        if host is None:
            host = receiving_host()
        return cls(
            src=p.src, device_id=p.device_id, boot_id=p.boot_id, seq=p.seq,
            type=p.type, ch=p.ch, tick_ms=p.tick_ms, utc_ms=p.utc_ms,
            err_ms=p.err_ms, acc=p.acc, sync=p.sync, mode=p.mode,
            epoch=p.epoch, session=p.session, srv=p.srv, stratum=p.stratum,
            body=p.body, raw=p.raw, host=host,
        )

    @property
    def utc(self):
        """Aware UTC datetime from utc_ms (display only), or None."""
        if self.utc_ms is None:
            return None
        return UNIX_EPOCH + timedelta(milliseconds=self.utc_ms)
