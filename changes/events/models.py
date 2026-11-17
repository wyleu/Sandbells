"""models.py -- one row per sand.event/v1 message.

Times are integer ms (BigInteger: utc_ms ~1.8e12 overflows 32 bits).
(src, boot_id, seq) is the natural key; re-sends are ignored on insert, so
DBs from sandbells and sandbells2 merge idempotently.  host records which
Sandbells received the row and is NOT part of the key.
"""

import socket
from datetime import datetime, timedelta, timezone

from django.db import models
from django.utils import timezone

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


class ChannelMap(models.Model):
    """Which bell a device channel senses, from valid_from on.

    Many channels may map to one bell (e.g. two heads on the tenor), and
    their strokes stay distinct by ch.  A later row for the same src+ch
    replaces the earlier one from its valid_from; bell left empty means
    "unmapped" again.  Unmapped channels show as "ch N"."""
    src = models.CharField(max_length=C.SRC_MAX_LEN, default=C.DEFAULT_SRC)
    ch = models.PositiveSmallIntegerField()
    bell = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Bell number (1 = treble); empty = unmapped")
    valid_from = models.DateTimeField(
        default=timezone.now, help_text="Applies to strokes from this time on")
    note = models.CharField(max_length=C.NOTE_MAX_LEN, blank=True)

    class Meta:
        ordering = ["src", "ch", "valid_from"]
        constraints = [
            models.UniqueConstraint(fields=["src", "ch", "valid_from"],
                                    name="chmap_src_ch_from_uniq"),
        ]

    def __str__(self):
        target = ("bell %d" % self.bell) if self.bell is not None else "unmapped"
        return "%s ch %d -> %s" % (self.src, self.ch, target)

    @property
    def valid_from_ms(self):
        return int((self.valid_from - UNIX_EPOCH) / timedelta(milliseconds=1))


class HeadLevel(models.Model):
    """One reading of a head's raw phototransistor level (the Orange/White
    wire, sandswing pt_level.py on GP27), stored by ingest_serial from the
    serial heartbeat at most every PT_LOG_EVERY_S, so the day / night drift
    of the PT can be reviewed later (/farm/heads/pt-log.csv)."""
    at = models.DateTimeField(default=timezone.now, db_index=True)
    uid = models.CharField(max_length=C.PT_LOG_UID_MAX_LEN, blank=True, default="",
                           help_text="the Pico's UID")
    ch = models.PositiveSmallIntegerField(help_text="1-based channel")
    pt_v = models.FloatField(help_text="PT level, volts (mean of a short burst)")
    pt_span = models.FloatField(null=True, blank=True, help_text="max - min over the burst, volts")
    thr = models.IntegerField(null=True, blank=True, help_text="threshold target duty")
    thr_rb = models.IntegerField(null=True, blank=True, help_text="GP28 threshold readback")
    tower = models.CharField(max_length=C.PT_LOG_TOWER_MAX_LEN, blank=True, default="")

    class Meta:
        ordering = ["at"]

    def __str__(self):
        return "%s ch %d %.3f V" % (self.at, self.ch, self.pt_v)


class HeadSweep(models.Model):
    """One line-up sweep of a head (sandswing sweep.py: drive stepped from
    full down to the floor, PT level and laser current at each step), as the
    sandheads page saw it, with the number written on the head, so the same
    head can be compared by day and by night (/farm/heads/sweep-log.csv)."""
    at = models.DateTimeField(default=timezone.now, db_index=True)
    ch = models.PositiveSmallIntegerField(help_text="1-based channel it was swept in")
    label = models.CharField(max_length=C.HEADS_LABEL_MAX, blank=True, default="",
                             help_text="the number written on the head")
    end = models.CharField(max_length=C.HEADS_SWEEP_END_MAX_LEN, blank=True, default="",
                           help_text="'' every point; else why it ended early")
    points = models.JSONField(default=list,
                              help_text="[[drive duty, mA, PT volts, PT spread], ...] full drive first")
    drv_before = models.IntegerField(null=True, blank=True)
    thr_before = models.IntegerField(null=True, blank=True)
    suggested_drv = models.IntegerField(null=True, blank=True)
    suggested_thr = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ["at"]

    def __str__(self):
        return "%s ch %d %s (%d points)" % (self.at, self.ch, self.label, len(self.points or []))


class HeadChatter(models.Model):
    """One chatter-test run on the sandheads page (sandswing chatter.py):
    the laser drive and PWM speed it ran at, how many vane passes sandtest
    made, and what the Pico counted -- transitions, those with one clean
    edge, the most edges in one, the longest burst and spurious edges in a
    steady state.  Kept so drives and speeds can be compared
    (/farm/heads/chatter-log.csv)."""
    at = models.DateTimeField(default=timezone.now, db_index=True)
    ch = models.PositiveSmallIntegerField(help_text="1-based channel")
    label = models.CharField(max_length=C.HEADS_LABEL_MAX, blank=True, default="",
                             help_text="the number written on the head")
    drv = models.IntegerField(help_text="laser drive duty 0-65535")
    pwm_hz = models.IntegerField(null=True, blank=True,
                                 help_text="laser PWM frequency the Pico reported")
    passes = models.IntegerField(null=True, blank=True,
                                 help_text="sandtest round trips; null: moved by hand")
    expected = models.IntegerField(null=True, blank=True,
                                   help_text="transitions the passes should give")
    trans = models.IntegerField(null=True, blank=True)
    clean = models.IntegerField(null=True, blank=True)
    max_edges = models.IntegerField(null=True, blank=True)
    mean_x10 = models.IntegerField(null=True, blank=True)
    max_burst_ms = models.IntegerField(null=True, blank=True)
    spurious = models.IntegerField(null=True, blank=True)
    end = models.CharField(max_length=C.HEADS_CHATTER_END_MAX_LEN, blank=True, default="",
                           help_text="'' a whole run; else why it ended early")

    class Meta:
        ordering = ["at"]

    def __str__(self):
        return "%s ch %d drive %d pwm %s: %s/%s clean" % (
            self.at, self.ch, self.drv, self.pwm_hz, self.clean, self.trans)

