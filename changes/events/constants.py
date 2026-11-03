"""constants.py -- names and limits for sand.event/v1 ingest.

Every literal the events app relies on lives here, so parse.py and
models.py hold no magic numbers or strings.
"""

SCHEMA_EVENT_V1 = "sand.event/v1"
SCHEMA_PANEL_V1 = "sand.panel/v1"   # live LED mimic frames: never stored
IGNORED_SCHEMAS = (SCHEMA_PANEL_V1,)

# ---- event types ----------------------------------------------------------
TYPE_STROKE = "stroke"
TYPE_LINK = "link"              # sandswing: client connected/dropped, wifi lost/back
TYPE_INGEST = "ingest"          # this Sandbells' ingest: connected/disconnected/...
TYPE_HEARTBEAT = "heartbeat"    # sand.panel/v1 frames: shown on page 3, never stored
TYPE_CHANNEL = "channel"        # sandswing: a socket's survey kind changed (ch, kind, prev_kind, why)
KNOWN_EVENT_TYPES = (TYPE_STROKE, TYPE_LINK, TYPE_INGEST, TYPE_CHANNEL)

# ---- stamp vocabularies (from sntp_pico.SntpClock.stamp) -------------------
SYNC_UNSYNCED = "unsynced"
SYNC_SYNCED = "synced"
SYNC_STALE = "stale"            # holdover: bursts missed, estimate ageing
SYNC_HELD = "held"              # ringing: mapping frozen on purpose
SYNC_VALUES = (SYNC_UNSYNCED, SYNC_SYNCED, SYNC_STALE, SYNC_HELD)

ACC_MS = "ms"                   # good enough for bell timing
ACC_S = "s"                     # good enough for a tower-clock check
ACC_VALUES = (ACC_MS, ACC_S)    # or null

MODE_FREE = "free"
MODE_RINGING = "ringing"
MODE_VALUES = (MODE_FREE, MODE_RINGING)   # or null

# ---- wire field names -----------------------------------------------------
F_SCHEMA = "schema"
F_TYPE = "type"
F_SRC = "src"
F_ID = "id"
F_BOOT_ID = "boot_id"
F_SEQ = "seq"
F_TICK_MS = "tick_ms"
F_UTC_MS = "utc_ms"
F_ERR_MS = "err_ms"
F_ACC = "acc"
F_SYNC = "sync"
F_MODE = "mode"
F_EPOCH = "epoch"
F_SESSION = "session"
F_SRV = "srv"
F_STRATUM = "stratum"
F_BODY = "body"
BODY_CH = "ch"
BODY_UID = "uid"                # sand.panel/v1 heartbeat body: the Pico's unique id

REQUIRED_STR_FIELDS = (F_TYPE, F_SRC, F_ID, F_BOOT_ID)
REQUIRED_INT_FIELDS = (F_SEQ, F_TICK_MS)
OPTIONAL_INT_FIELDS = (F_UTC_MS, F_EPOCH, F_SESSION, F_STRATUM)
OPTIONAL_NUMBER_FIELDS = (F_ERR_MS,)
OPTIONAL_CHOICE_FIELDS = {F_ACC: ACC_VALUES, F_SYNC: SYNC_VALUES,
                          F_MODE: MODE_VALUES}

# ---- limits ---------------------------------------------------------------
SEQ_MIN = 0
STRATUM_MIN = 0
STRATUM_MAX = 16                # NTP: 16 = unsynchronised
SRC_MAX_LEN = 32
DEVICE_ID_MAX_LEN = 64
BOOT_ID_MAX_LEN = 32
TYPE_MAX_LEN = 32
CHOICE_MAX_LEN = 16             # acc / sync / mode
SRV_MAX_LEN = 45                # longest textual IPv6 address
NOTE_MAX_LEN = 200
HOST_MAX_LEN = 64               # receiving Sandbells hostname (DNS label)
MAX_LEN = {F_SRC: SRC_MAX_LEN, F_ID: DEVICE_ID_MAX_LEN,
           F_BOOT_ID: BOOT_ID_MAX_LEN, F_TYPE: TYPE_MAX_LEN}

MS_PER_S = 1000
TEXT_ENCODING = "utf-8"

# ---- ParseError reasons ---------------------------------------------------
R_NOT_UTF8 = "not_utf8"
R_NOT_JSON = "not_json"
R_NOT_OBJECT = "not_object"
R_BAD_SCHEMA = "bad_schema"
R_MISSING = "missing_field"
R_BAD_TYPE = "bad_type"          # wrong JSON type for the field
R_BAD_VALUE = "bad_value"        # right type, value not allowed
R_TOO_LONG = "too_long"
R_IGNORED = "ignored"            # known non-event schema: drop silently

# ---- batched store (store.py) --------------------------------------------
# A peal is a few strokes per second; one commit per batch spares the SD card.
STORE_FLUSH_COUNT = 64          # flush when this many events are buffered
STORE_FLUSH_INTERVAL_S = 1.0    # ...or when the oldest has waited this long
                                # (live pages poll the DB; WAL+NORMAL: no fsync per commit)
STORE_MAX_BUFFERED = 5000       # DB stuck: drop oldest beyond this (counted)

# ---- gap tracker (gaps.py) -----------------------------------------------
SEQ_FIRST = 1                   # sand_event.Emitter: first seq after boot
GAP_FIRST = "first"             # first event seen from this src
GAP_OK = "ok"                   # seq == last + 1
GAP_GAP = "gap"                 # seq > last + 1: missing range reported
GAP_DUPLICATE = "duplicate"     # seq == last
GAP_OUT_OF_ORDER = "out_of_order"   # seq < last (late, or an older resend)
GAP_RESET = "reset"             # new boot_id for a known src

# ---- SQLite pragmas (db.py) ----------------------------------------------
SQLITE_VENDOR = "sqlite"
SQLITE_JOURNAL_MODE = "WAL"     # readers do not block the ingest writer
SQLITE_SYNCHRONOUS = "NORMAL"   # safe with WAL, far fewer fsyncs
SQLITE_BUSY_TIMEOUT_MS = 5000   # wait for a lock instead of failing at once

# ---- ingest: WebSocket client (wsclient.py, backoff.py) ------------------
# By IP: sandbells2 cannot resolve .local names.
WS_DEFAULT_URL = "ws://192.168.0.81/ws"
# manage.py ingest_udp: the concentrator's tier 3 ("link.ring_send": "udp"):
# every event is one datagram, fire and forget (no TCP on the Pico, so no
# 10 s lwIP ERR_MEM hold).  A lost datagram is a seq gap (GapTracker).
UDP_INGEST_HOST = "0.0.0.0"
UDP_INGEST_PORT = 5055          # sandswing link_health.UDP_PORT
UDP_MAX_B = 1472                # sandswing link_health.UDP_MAX_B: one Ethernet frame
UDP_IDLE_S = 1.0                # recv timeout: flush / summary / link state this often when quiet
# back chat: each sand.panel/v1 heartbeat datagram gets one tiny ack, sent
# on the same socket to the heartbeat's source (ip, port).  The Pico turns
# its link LED green on it and rejoins Wi-Fi when acks stop (its wifi_ok()
# can say up while nothing gets through).  Best effort: never waits,
# errors are counted.
SCHEMA_ACK_V1 = "sand.ack/v1"   # sandswing link_health.ACK_SCHEMA
UDP_ACK_MIN_S = 2.0             # at most one ack per sender IP per this (heartbeats: every 5 s)
UDP_ACK_MAX_B = 100             # an ack is always smaller than this
ACK_BOOT_ID_MAX = 16            # the heartbeat's boot_id, cut to this (it is 8 hex)
UDP_ACK_LOG_EVERY = 100         # a failed ack is logged the first time and every this many
WS_CONNECT_TIMEOUT_S = 5.0
WS_RECV_TIMEOUT_S = 1.0         # idle wake-up: store.poll(), summary, stop check
BACKOFF_INITIAL_S = 1.0
BACKOFF_FACTOR = 2.0
BACKOFF_MAX_S = 30.0
# Link health (see docs/link-health.md).  The Pico sends a sand.panel/v1
# heartbeat every 5 s and drops a client that has sent heartbeats but then
# goes quiet for 20 s; this end does the same the other way round.
CLIENT_HEARTBEAT_S = 5.0        # our heartbeat text frame to the Pico
PEER_SILENT_S = 20.0            # no frame this long (after a heartbeat): dead
FIRST_FRAME_S = 60.0            # connected but not one frame this long: dead (Pico heartbeats every 5 s)
SCHEMA_HELLO_V1 = "sand.hello/v1"   # client -> Pico heartbeat (Pico ignores content)
TCP_KEEPIDLE_S = 10             # kernel keepalive under the app heartbeat
TCP_KEEPINTVL_S = 5
TCP_KEEPCNT = 3
INGEST_SRC = "sandbells"        # src of this side's own "ingest" events
# Link state file for page 3 (tmpfs; RuntimeDirectory=sandbells-ingest)
LINK_STATE_PATH = "/run/sandbells-ingest/link.json"
LINK_STATE_ENV = "SANDBELLS_LINK_STATE"
LINK_STATE_SCHEMA = "sandbells.link/v1"
LINK_STATE_MODE = 0o644         # gunicorn (another user) reads it
LINK_WRITE_MIN_S = 1.0          # frames/heartbeats: at most one write a second
LINK_WRITE_MAX_S = 5.0          # idle: rewrite so the file age says "ingest alive"
LINK_STARTING = "starting"
LINK_CONNECTED = "connected"
LINK_DOWN = "down"
LINK_STOPPED = "stopped"

# ---- ingest: logging (ingest.py) -----------------------------------------
LOGGER_NAME = "events.ingest"
SUMMARY_INTERVAL_S = 60.0       # one INFO summary line per this
REJECT_LOG_INTERVAL_S = 60.0    # at most one WARNING per reject reason per this

# ---- ingest: frames it cannot decode (framestate.py, docs/link-health.md) --
# A frame that is not valid UTF-8 / JSON (e.g. a Pico heartbeat cut off
# mid-string) is skipped and counted; the link is dropped only after this
# many in a row.  FIRST GUESS: replace with a number read from the journal
# ("bad frame" lines, "bad N" in the summary) once there is data.
BAD_FRAME_LIMIT = 5
BAD_FRAME_LOG_INTERVAL_S = 10.0     # at most one "bad frame" WARNING per this
BAD_FRAME_EXCERPT_BYTES = 60        # first and last this many bytes are logged
DECODE_REASONS = (R_NOT_UTF8, R_NOT_JSON)   # ParseError reasons that mean "cannot decode"
WS_CANNOT_DECODE_PREFIX = "cannot decode: "  # websocket-client WebSocketPayloadException text
FRAME_GOOD = "good_frame"       # events of the frame table
FRAME_BAD = "bad_frame"
ACT_RESET = "reset"             # actions of the frame table
ACT_COUNT = "count"
ACT_DISCONNECT = "disconnect"
BAD_FRAME_WHY_TRANSPORT = "cannot decode"   # the WebSocket library refused the text

# ---- ingest: URL from the existing Sandbells settings.json (config.py) -----
SANDBELLS_SETTINGS_PATH = "/etc/sandbells/settings.json"
SANDBELLS_SETTINGS_ENV = "SANDBELLS_SETTINGS"   # same override as the scripts
CONCENTRATOR_FAMILY = "sandswing"   # status.devices[].family to ingest from

# ---- ingest: fail fast on a missing dependency ---------------------------
WS_LIBRARY_MODULE = "websocket"
WS_LIBRARY_PIP = "websocket-client==1.8.0"
EXIT_CONFIG_ERROR = 78          # sysexits EX_CONFIG; the unit's RestartPreventExitStatus

# ---- display: local time, rings, pages (localtime.py, rings.py, api.py) --
DISPLAY_TZ_NAME = "Europe/London"   # all pages show UK local time (BST aware)
MS_PER_MINUTE = 60 * MS_PER_S
# Strokes of one device/boot closer together than this are one displayed
# "ring": a 10-15 min wait between touches stays in the same ring; a
# separate ring later in the day (or the next service) starts a new one.
RING_GAP_MS = 30 * MS_PER_MINUTE
CH_LABEL = "ch %d"                  # unmapped channel shown as "ch N"
DEFAULT_SRC = "sandswing"
LIVE_LIMIT_DEFAULT = 50             # events per /since/ response
LIVE_LIMIT_MAX = 500
DAYS_DEFAULT = 7                    # /days/ without from/to: last 7 local days
DAYS_MAX = 31                       # longest /days/ span (Pi 3: keep it light)
DATE_FORMAT = "%Y-%m-%d"
RING_TABLE_MAX_ROWS = 5000          # ring page: strokes listed (Luakit, Pi 3)
DAY_LABEL_FORMAT = "%a %d %b %Y"    # "Thu 22 Oct 2026"
SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600

# ---- live list (the Strokes page, /events/strokes/) ------------------------
TIME_OK_ACC = ACC_MS                        # marker bright only for ms ...
TIME_OK_SYNC = (SYNC_SYNCED, SYNC_HELD)     # ... and a locked mapping
LIVE_PREV_SEQ_SPAN = 1000      # look back this many seqs for a ch's last stroke
LIVE_FIRST_LOAD = 20           # strokes shown when the panel opens
LIVE_DOM_ROWS = 50             # rows kept in the page
LIVE_POLL_MS = 1000
LIVE_RETRY_MAX_MS = 5000       # quiet back-off ceiling on errors
LIVE_FAILS_WARN = 5            # failed polls in a row before the warning
LIVE_IDLE_NOTE_MS = 2 * MS_PER_MINUTE
LIVE_FETCH_TIMEOUT_MS = 4000
BELL_LABEL = "Bell %d"

# ---- home page bell strokes (bells/home.html data-strike-gap-ms, bell_feed.js) --
# Each stroke swings the struck bell's clapper (the pad press movement); strokes
# that arrive together in one poll answer start this far apart (3 x this is
# about one LIVE_POLL_MS, see bell_feed.js MAX_MOVES).
BELL_STRIKE_GAP_MS = 350

# ---- page 3 link widget (link_widget.js, api.link) -------------------------
LINK_POLL_MS = 2000             # widget poll of /events/api/link/
LINK_STALE_MS = 15000           # no Pico heartbeat this long: grey (3 missed)
LINK_LOST_MS = 30000            # ...this long, or ingest down: red LOST
INGEST_FILE_STALE_MS = 15000    # link file not rewritten: ingest not running
# MIDI (cyan) instead of the Wi-Fi verdict: midi_status.json rewritten within
# INGEST_STATUS_STALE_MS, it says connected, and a stamp/clock SysEx or a note
# arrived within MIDI_LIVE_MS.  The Pico sends a clock every
# MIDI_CLOCK_EVERY_MS when quiet, so MIDI_LIVE_MS allows two to go missing.
LINK_MIDI = "midi"
MIDI_CLOCK_EVERY_MS = 10000     # sandswing midi_stamp.py clock interval
MIDI_LIVE_MS = 2 * MIDI_CLOCK_EVERY_MS + 5000

# ---- ingest status file + page (ingeststatus.py, /events/ingest/) ----------
# ingest_udp's own counters for the Ingest page: one small JSON file next to
# the link state (same tmpfs RuntimeDirectory), written atomically.  Separate
# from link.json so the page can tell "ingest alive" from "Pico alive".
INGEST_STATUS_PATH = "/run/sandbells-ingest/status.json"
INGEST_STATUS_ENV = "SANDBELLS_INGEST_STATUS"
INGEST_STATUS_SCHEMA = "sandbells.ingest_status/v1"
INGEST_STATUS_WRITE_S = 5.0     # rewrite at least this often (file age = alive)
INGEST_STATUS_CHANGE_S = 1.0    # on a change: at most one write per this
INGEST_STATUS_STALE_MS = 15000  # file older than this: STALE (3 writes missed)
INGEST_STATUS_RECENT = 10       # rejected / bad datagrams kept, newest last
INGEST_STATUS_EXCERPT = 80      # characters of each one shown
INGEST_MODE_UDP = "udp"
UDP_URL_FORMAT = "udp://%s:%d"   # the link state's "url" while ingest_udp listens
INGEST_STATE_RUNNING = "running"
INGEST_STATE_STOPPED = "stopped"
INGEST_QUIET_MS = 15000         # running but no datagram this long: QUIET
INGEST_UNITS = ("sandbells-ingest-udp.service", "sandbells-ingest.service",
                "sandbells-ingest-midi.service")
INGEST_UNIT_MODES = {"sandbells-ingest-udp.service": "udp (manage.py ingest_udp)",
                     "sandbells-ingest-midi.service": "usb midi (manage.py ingest_midi)",
                     "sandbells-ingest.service": "websocket (manage.py ingest_events)"}
SYSTEMCTL = "systemctl"
SYSTEMCTL_TIMEOUT_S = 2.0       # per call; the page never waits longer
PROC_NET_UDP = "/proc/net/udp"  # is the port bound (by anyone)?
INGEST_PAGE_REFRESH_S = 5       # the page reloads itself (no JS)

# ---- ingest: USB MIDI from the Pico (manage.py ingest_midi, midiparse.py, midiingest.py) --
# With no usable Wi-Fi the Pico's USB plugs into this Pi; each bell stroke
# arrives as a USB MIDI NoteOn (sandswing ring.py: NoteOn vel 100 on the
# stroke, NoteOff vel 0 on the release).  MIDI has no timestamp: the stroke
# is stamped with this Pi's clock when the bytes are read (utc_ms from
# time.time, tick_ms from time.monotonic).  Stored as sand.event/v1 strokes
# through the same Ingest / EventStore as ingest_udp, src MIDI_SRC.
MIDI_SRC = "midi"               # Event.src of MIDI strokes (udp/ws ones: "sandswing")
MIDI_DEVICE_ID = "sandswing-pico"   # Event.device_id ('id' on the wire), as sandswing's
MIDI_BODY_VIA = "via"           # body field naming the transport ...
MIDI_BODY_NOTE = "note"         # ... the MIDI note number ...
MIDI_BODY_VEL = "vel"           # ... and its velocity
MIDI_CHANNEL = 1                # 1-based; sandswing ring.open_midi: adafruit out_channel=0
MIDI_CHANNEL_ANY = 0            # --channel 0: accept NoteOns on any channel
MIDI_CHANNELS = 16
# note -> sandswing channel (body "ch", 1-based), from sandswing ring.NOTES
# (65, 64, 62, 60, 58, 57, 55, 53) for channels 1..8: the note a channel's
# bell (or its trigger plug, sandswing 0cfd112) plays.  The bell number then
# comes from ChannelMap, as for udp strokes (MAP_SRC_FALLBACK).
MIDI_NOTE_TO_CH = {65: 1, 64: 2, 62: 3, 60: 4, 58: 5, 57: 6, 55: 7, 53: 8}
MIDI_UNMAPPED_LOG_EVERY = 100   # an unmapped note is logged the first time and every this many
# Which ALSA card is the Pico: the first card whose /proc/asound/cards lines
# (or its midiN files) contain one of these.  The Pico 2 W shows as
# card 'Pico 2 W', seq port 'Pico 2 W CircuitPython usb_midi'.
MIDI_CARD_MATCH = ("Pico 2 W", "CircuitPython")
MIDI_CARD_ENV = "SANDBELLS_MIDI_CARD"       # override: one substring to match instead
MIDI_DEVICE_ENV = "SANDBELLS_MIDI_DEVICE"   # override: this rawmidi device, no search
MIDI_PROC_CARDS = "/proc/asound/cards"
MIDI_PROC_CARD_DIR = "/proc/asound/card%d"
MIDI_PROC_MIDI_GLOB = "midi*"               # /proc/asound/cardN/midiD: one per rawmidi device
MIDI_DEV_FORMAT = "/dev/snd/midiC%dD%d"
MIDI_URL_FORMAT = "midi:%s"                 # status "port": midi:/dev/snd/midiC3D0, midi:seq:Pico 2 W
# How the bytes are read.  raw: the rawmidi device with plain os.read (no
# package).  seq: `aseqdump -p <card>` (alsa-utils): an ALSA sequencer
# subscriber, so it shares the port with PipeWire's MIDI bridge, which holds
# the rawmidi input open (raw then gets EBUSY).  auto: raw, else seq on EBUSY.
MIDI_TRANSPORT_RAW = "raw"
MIDI_TRANSPORT_SEQ = "seq"
MIDI_TRANSPORT_AUTO = "auto"
MIDI_TRANSPORTS = (MIDI_TRANSPORT_AUTO, MIDI_TRANSPORT_RAW, MIDI_TRANSPORT_SEQ)
MIDI_SEQ_DUMP = "aseqdump"
MIDI_SEQ_LINEBUF = ("stdbuf", "-oL")        # aseqdump's stdout into a pipe: line buffered
MIDI_READ_B = 256               # one os.read
MIDI_IDLE_S = 1.0               # select timeout: flush / summary / status this often when quiet
MIDI_RECONNECT_S = 3.0          # no port / unplugged: look again this often (never a busy loop)
MIDI_STOP_WAIT_S = 2.0          # aseqdump: wait this long for it to exit, then kill
# status file (same tmpfs as status.json; separate, so ingest_udp and
# ingest_midi can run side by side)
INGEST_MODE_MIDI = "midi"
MIDI_STATUS_PATH = "/run/sandbells-ingest/midi_status.json"
MIDI_STATUS_ENV = "SANDBELLS_MIDI_STATUS"
MIDI_STATUS_RECENT_ERRORS = 10
# MIDI 1.0 bytes (midiparse.py)
MIDI_STATUS_BIT = 0x80          # a byte >= this is a status byte, below it data
MIDI_TYPE_MASK = 0xF0
MIDI_CHANNEL_MASK = 0x0F
MIDI_NOTE_OFF = 0x80
MIDI_NOTE_ON = 0x90
MIDI_SYSEX_START = 0xF0
MIDI_SYSEX_END = 0xF7
MIDI_REALTIME_MIN = 0xF8        # 0xF8-0xFF: one byte, anywhere, running status kept
MIDI_DATA_LEN = {0x80: 2, 0x90: 2, 0xA0: 2, 0xB0: 2, 0xC0: 1, 0xD0: 1, 0xE0: 2}
MIDI_COMMON_DATA_LEN = {0xF1: 1, 0xF2: 2, 0xF3: 1, 0xF4: 0, 0xF5: 0, 0xF6: 0}
MIDI_ON = "on"
MIDI_OFF = "off"
# The Pico's stroke stamp (sandswing src/midi_stamp.py, docs/midi-stamp.md):
# right after each stroke NoteOn one SysEx with the stroke's keypad stamp,
#     F0 7D 53 01 sh sl cc t4 t3 t2 t1 t0 F7
# 7D the non-commercial manufacturer ID, 53 'S', 01 the layout version,
# seq 14 bits (strokes 1..16383 then 1; 0 = none yet), cc the bell channel
# 1-8 (0 = a clock message: the Pico's ms now, sent when quiet), t the ms on
# the Pico's tick scale, 35 bits, 7 per byte, most significant first.
# Any other SysEx is skipped (counted in sysex_skipped).
MIDI_STAMP = "stamp"            # StampMessage.kind
MIDI_STAMP_MFR_ID = 0x7D
MIDI_STAMP_TAG = 0x53           # 'S'
MIDI_STAMP_VERSION = 1
MIDI_STAMP_LEN = 13             # F0 .. F7
MIDI_STAMP_SEQ_BYTES = 2
MIDI_STAMP_T_BYTES = 5
MIDI_STAMP_SEQ_MAX = 16383      # 14 bits; a stroke seq after this is 1
MIDI_STAMP_CH_CLOCK = 0
MIDI_SEVEN_BITS = 7
MIDI_SYSEX_KEEP_B = 32          # a SysEx longer than this is not ours: not kept, just skipped
# aseqdump prints a SysEx as "System exclusive" then its bytes in hex (F0 .. F7)
MIDI_SEQ_SYSEX_WORDS = "System exclusive"
# Pairing: a NoteOn stroke is held until its stamp arrives (same bell
# channel), at most this long; then stored unstamped at its arrival time.
MIDI_STAMP_WAIT_MS = 50
# Offset (host ms - Pico ms) = the minimum over a sliding window of
# (arrival - stamp): the least-delayed sample.  Window: the last N samples,
# none older than MAX_AGE.  The host side of the offset is time.monotonic
# (an NTP step on the wall clock cannot jump it); utc_ms adds wall - monotonic.
MIDI_STAMP_WINDOW_N = 64
MIDI_STAMP_WINDOW_MS = 300000   # 5 min (clock messages every 10 s keep it fed when quiet)
# A stamp more than this before the last one: the Pico restarted (its tick
# scale began again), not a late message -> the window starts afresh.
MIDI_STAMP_REBOOT_BACK_MS = 1000
# Stroke stamp body fields (besides ch / note / vel / via)
MIDI_BODY_PICO_MS = "pico_ms"
MIDI_BODY_STAMP_SEQ = "seq"
MIDI_BODY_STAMPED = "stamped"
MIDI_BODY_OFFSET_MS = "offset_ms"
# a ChannelMap lookup for a MIDI stroke uses the Pico's own src's rows
# (same Pico, same channels), so bells show the same as over udp.
MAP_SRC_FALLBACK = {MIDI_SRC: DEFAULT_SRC}
