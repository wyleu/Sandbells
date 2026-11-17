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
# widget poll of /events/api/leds/ while the USB serial LED echo is live (and
# the page is visible): no slower than sandswing's SERIAL_LED_MIN_S (0.25 s),
# the shortest time a state stays on the wire, or flashes are missed
LINK_LED_POLL_MS = 250
LINK_STALE_MS = 15000           # no Pico heartbeat this long: grey (3 missed)
LINK_LOST_MS = 30000            # ...this long, or ingest down: red LOST
INGEST_FILE_STALE_MS = 15000    # link file not rewritten: ingest not running
# MIDI (cyan) instead of the Wi-Fi verdict: midi_status.json rewritten within
# INGEST_STATUS_STALE_MS, it says connected, and a stamp/clock SysEx or a note
# arrived within MIDI_LIVE_MS.  The Pico sends a clock every
# MIDI_CLOCK_EVERY_MS when quiet, so MIDI_LIVE_MS allows two to go missing.
LINK_MIDI = "midi"
# where the widget's heartbeat (LEDs, sync, heads) came from: the Wi-Fi
# ingest's link.json, or the USB serial status (ingest_serial) when the
# Wi-Fi heartbeat is not fresh and the serial one is (api.serial_link)
LINK_VIA_UDP = "udp"
# panel LED colours on screen: the Pico's rgb is dim on purpose (0..~48), so
# the brightest channel is scaled to PANEL_CSS_FULL; black is PANEL_CSS_DARK.
# The same rule as link_widget.js cssColour (FULL, DARK): tests_led_colour
# checks the two agree.
PANEL_CSS_FULL = 255
PANEL_CSS_DARK = "#222"
LINK_VIA_SERIAL = "usb serial"
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
                "sandbells-ingest-midi.service", "sandbells-ingest-serial.service")
INGEST_UNIT_MODES = {"sandbells-ingest-udp.service": "udp (manage.py ingest_udp)",
                     "sandbells-ingest-midi.service": "usb midi (manage.py ingest_midi)",
                     "sandbells-ingest-serial.service":
                         "usb serial status (manage.py ingest_serial)",
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

# ---- ingest: the Pico's status over its USB data port (manage.py ingest_serial, serialingest.py) --
# sandswing serial_status.py writes its slim heartbeat (sand.panel/v1, type
# heartbeat, "via": "usb_cdc") as one JSON line every serial_status.period_s
# on usb_cdc.data: the second CDC interface of the Pico's USB (ttyACM1 here;
# ttyACM0, the first, is the REPL console and is never opened).  Nothing is
# stored in the DB: the latest line goes to SERIAL_STATUS_PATH for the
# sandswing status page and the Ingest page.  MIDI is not touched.
INGEST_MODE_SERIAL = "serial"
SERIAL_STATUS_PATH = "/run/sandbells-ingest/serial_status.json"
SERIAL_STATUS_ENV = "SANDBELLS_SERIAL_STATUS"
SERIAL_DEVICE_ENV = "SANDBELLS_SERIAL_DEVICE"   # override: this tty, no search
SERIAL_MATCH_ENV = "SANDBELLS_SERIAL_MATCH"     # override: one product substring
SERIAL_SYS_TTY_GLOB = "/sys/class/tty/ttyACM*"
SERIAL_DEV_DIR = "/dev"
SERIAL_BY_ID_GLOB = "/dev/serial/by-id/*"
# the Pico: its USB product / manufacturer contains one of these
SERIAL_PRODUCT_MATCH = ("Pico 2 W", "CircuitPython")
# CircuitPython names its CDC interfaces "CircuitPython CDC control" (the
# REPL) and "CircuitPython CDC2 control" (usb_cdc.data)
SERIAL_DATA_IF_NAME = "CDC2"
SERIAL_CONSOLE_IF_NUM = 0       # bInterfaceNumber of the REPL: never this one
SERIAL_DATA_IF_NUM = 2          # usb_cdc.data's when the name is not there (by-id ...-if02)
SERIAL_BY_ID_DATA_SUFFIX = "-if%02d" % SERIAL_DATA_IF_NUM
SERIAL_URL_FORMAT = "serial:%s"  # status "port": serial:/dev/ttyACM1
SERIAL_READ_B = 1024            # one os.read
SERIAL_LINE_MAX_B = 8192        # no newline within this many bytes: dropped (sandswing max 2048)
SERIAL_IDLE_S = 1.0             # select timeout: status file this often when quiet
SERIAL_RECONNECT_S = 3.0        # no port / unplugged: look again this often
SERIAL_STATUS_RECENT_ERRORS = 10
SERIAL_HB_SCHEMA = "sand.panel/v1"
SERIAL_HB_TYPE = "heartbeat"
SERIAL_PERIOD_DEFAULT_S = 10    # sandswing serial_status.SERIAL_PERIOD_S, if a line does not say
SERIAL_STALE_PERIODS = 3        # no line for this many periods: stale
SERIAL_STALE_SLACK_MS = 5000    # ... plus this
# LED echo (sandswing serial_status.leds): {"t":"led","n","p","s"} lines on
# each panel change, at most one per 0.25 s (its SERIAL_LED_MIN_S).  The
# newest goes to SERIAL_LEDS_PATH (small, written on each such line and each
# heartbeat) for /events/api/leds/, which the link widget polls every
# LINK_LED_POLL_MS while the echo is live.
SERIAL_LED_TYPE = "led"
SERIAL_LED_MIN_S = 0.25         # sandswing serial_status.SERIAL_LED_MIN_S (LINK_LED_POLL_MS no slower)
SERIAL_LEDS_PATH = "/run/sandbells-ingest/serial_leds.json"
SERIAL_LEDS_ENV = "SANDBELLS_SERIAL_LEDS"
SERIAL_LEDS_SCHEMA = "sandbells.serial_leds/v1"
SERIAL_LEDS_N = 6               # panel LEDs in a line (sandswing panel.PANEL_N)
# the newest LED lines kept in the file ("recent"): the widget shows each for
# at least one poll, so a 0.25 s flash between two polls is not missed
SERIAL_LEDS_RECENT = 4
# the sandswing status page (bells.views.farm_device_status): a fresh serial
# status is shown instead of asking the Pico's /status over Wi-Fi (its 7 kB
# reply is what starved lwIP); a stale one only when Wi-Fi does not answer
SERIAL_FIRST = True

# ---- sandheads over the USB data port (ring_send "off": no Wi-Fi) -----------
# ingest_serial is the one owner of the port.  The sandheads page POSTs its
# {"cmd":"align",...} commands to Django, which checks them and hands them to
# ingest_serial as one datagram each on SERIAL_CMD_SOCK_PATH; ingest_serial
# writes them to the Pico as lines.  The Pico's replies (sand.panel/v1 types
# in SERIAL_HEADS_TYPES) go to SERIAL_HEADS_PATH, which the page polls.
# Protocol: sandswing docs/align-scope.md.
SERIAL_CMD_SOCK_PATH = "/run/sandbells-ingest/serial_cmd.sock"
SERIAL_CMD_SOCK_ENV = "SANDBELLS_SERIAL_CMD_SOCK"
SERIAL_CMD_SOCK_MODE = 0o660    # gunicorn and ingest_serial both run as sandbells
SERIAL_CMD_MAX_B = 256          # one command (sandswing align_scope.MSG_MAX_B)
SERIAL_CMD_QUEUE_MAX_B = 2048   # bytes waiting for the port; more: dropped (counted)
SERIAL_CMD_NAME = "align"       # the only command the page may send
SERIAL_CMD_KEYS = ("cmd", "ch", "scope", "thr", "drive", "info", "thr_mid",
                   "sweep", "use", "save", "label", "forget", "saved",
                   "pwm_hz", "chatter", "gap_ms")                    # align_scope._KEYS
SERIAL_CMD_MAX_CH = 16          # a channel number above this is refused here already
SERIAL_HEADS_PATH = "/run/sandbells-ingest/serial_heads.json"
SERIAL_HEADS_ENV = "SANDBELLS_SERIAL_HEADS"
SERIAL_HEADS_SCHEMA = "sandbells.serial_heads/v1"
SERIAL_HEADS_TYPES = ("align", "align_ack", "align_info", "align_sweep", "align_slot",
                      "align_chatter")
SERIAL_HEADS_KEEP = 12          # newest scope lines kept in the file (the page asks after=<n>)
SERIAL_HEADS_POLL_MS = 400      # the page's poll (the Pico sends a frame every 500 ms)
SERIAL_HEADS_LIVE_MS = 3000     # the page: no new line for this long while scoping: "no frames"
# sandswing serial_status: a heartbeat it could not build ({"t":"serr"})
SERIAL_ERR_TYPE = "serr"
SERIAL_ERR_LOG_EVERY = 30       # journal: the first after a connect, then every this many
# connected, yet no good heartbeat for this many stale periods: close and
# reopen the port (drops and raises DTR, which is what the Pico's
# usb_cdc.data.connected follows); the wait doubles after each reopen that
# did not help, up to SERIAL_REOPEN_MAX_FACTOR times
SERIAL_REOPEN_STALE = 1
SERIAL_REOPEN_MAX_FACTOR = 16

# ---- sandheads readings as MIDI CC (sandswing heads_cc.py) -------------------
# Commands go to the Pico over the USB data port (above); its readings and
# acks come back as Control Change on its USB MIDI out, channel
# HEADS_CC_CHANNEL.  ingest_midi decodes each report (CC_HEAD .. CC_SEQ) into
# the same sand.panel/v1 align / align_ack docs the /ws path carries, and
# keeps the newest in MIDI_HEADS_PATH for the sandheads page's poll.
# 14-bit values: MSB on CC n, LSB on n + HEADS_CC_LSB; HEADS_CC_NONE: none.
# Map and reasons: sandswing docs/align-scope.md "MIDI CC map".
MIDI_CC = "cc"                  # CcMessage.kind
MIDI_CONTROL_CHANGE = 0xB0
HEADS_CC_CHANNEL = 16
HEADS_CC_LSB = 32
HEADS_CC_HEAD = 102
HEADS_CC_FLAGS = 103
HEADS_CC_ACK_WHAT = 104
HEADS_CC_ACK_WHY = 105
HEADS_CC_SEQ = 106
HEADS_CC_SWEEP = 107            # a sweep point report: the point's index
HEADS_CC_SLOT = 108             # a saved-values report: 1 saved, 0 empty
HEADS_CC_LABEL = 109            # .. + HEADS_LABEL_MAX - 1: the label, one ASCII char each
HEADS_CC_THR = 20
HEADS_CC_RB = 21
HEADS_CC_DRV = 22
HEADS_CC_MA = 23
HEADS_CC_PT = 24
HEADS_CC_PT_SPAN = 25
HEADS_CC_PWM = 14               # every ack: the lasers' PWM frequency, HEADS_PWM_HZ_UNITS
HEADS_PWM_HZ_UNITS = 10
HEADS_CC_CHATTER = 117          # a chatter report (sandswing chatter.py): 1 counting, 0 stopped
# a chatter report's 14-bit values, in this order (heads_cc.CHATTER_CCS):
# transitions, clean, max edges, mean edges x10, longest burst ms, spurious edges
HEADS_CC_CHATTER_14 = (("trans", 26), ("clean", 27), ("max_edges", 28), ("mean_x10", 29),
                       ("max_burst_ms", 30), ("spurious", 31))
HEADS_CC_14 = (HEADS_CC_THR, HEADS_CC_RB, HEADS_CC_DRV, HEADS_CC_MA, HEADS_CC_PT,
               HEADS_CC_PT_SPAN, HEADS_CC_PWM) + tuple(cc for _, cc in HEADS_CC_CHATTER_14)
HEADS_CC_NONE = 16383
HEADS_CC_MAX = 16382            # full duty (65535) is sent as this
HEADS_DUTY_FULL = 65535
HEADS_MA_UNITS = 100            # 0.01 mA
HEADS_MA_DP = 2                 # decimals of the on-current worked out here
HEADS_MV_PER_V = 1000
HEADS_FLAG_CLEAR = 1
HEADS_FLAG_BROKE = 2
HEADS_FLAG_BUSY = 4
HEADS_FLAG_QUIET = 8
HEADS_FLAG_SCOPE = 16
HEADS_FLAG_STUCK = 32           # not quiet only because of stuck heads: thr / drive allowed
HEADS_FLAG_LIT_LOW = 64         # comparator low (held) = light on the PT (heads.pt_light "lowers")
HEADS_WHAT = {1: "thr", 2: "drive", 3: "scope", 4: "bad", 5: "thr_mid", 6: "sweep",
              7: "sweep_end", 8: "use", 9: "save", 10: "forget", 11: "saved", 12: "pwm",
              13: "chatter"}
HEADS_WHY = {1: "not an active head", 2: "tower not quiet: strokes in progress",
             3: "survey running", 4: "old head has no threshold", 5: "too fast",
             6: "at limit", 7: "laser is off", 8: "laser current over its limit",
             9: "busy", 10: "timeout", 11: "head gone", 12: "low memory",
             13: "bad command", 14: "no light on the PT", 15: "stopped",
             16: "no PT wire on this channel", 17: "sweep running",
             18: "not saved", 19: "bad label", 20: "near threshold",
             21: "PWM speed out of range", 22: "PWM speed not changed",
             23: "no chatter test running", 127: "refused"}
HEADS_TOWER_QUIET = "inactive"  # what align.js calls a quiet tower
HEADS_TOWER_BUSY = "active"
# the page's trace from MIDI: one sample per report (beam low if any low
# sample since the last report), the last HEADS_TRACE_MS of them
HEADS_TRACE_MS = 2000
HEADS_TRACE_MAX = 64
MIDI_HEADS_PATH = "/run/sandbells-ingest/midi_heads.json"
MIDI_HEADS_ENV = "SANDBELLS_MIDI_HEADS"

# ---- head line-up (sandswing sweep.py / head_store.py) ------------------------
# The page's "Find best brightness" sweeps the drive of the head with the PT
# wire; it suggests the lowest drive whose PT level is within plateau_frac of
# the level at full drive, plus margin_frac, and keeps the threshold in the
# same proportion to the PT level as now, both measured from the light side
# (the Pico's heads.pt_light, HEADS_FLAG_LIT_LOW: on head 5 more light pulls
# the PT DOWN, so lineup.js works on VREF - PT).  Below min_range_v of PT change
# over the whole sweep it suggests nothing (the PT is not seeing the laser,
# or is saturated).  settings.json "sandheads": {"sweep": {...}} overrides.
HEADS_LINEUP_SLOTS = 8          # channels with saved values (head_store.SLOTS)
HEADS_LABEL_MAX = 8             # head_store.LABEL_MAX
HEADS_LABEL_CHARS = ("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
                     "-_./# ")  # head_store.LABEL_CHARS
HEADS_SWEEP_SETTINGS_KEY = "sandheads"
HEADS_SWEEP_DEFAULTS = {"plateau_frac": 0.05, "margin_frac": 0.2, "min_range_v": 0.05}
HEADS_SWEEP_POINTS_MAX = 64     # sweep.SWEEP_POINTS_MAX
HEADS_SWEEP_END_MAX_LEN = 40    # the end reason kept with a logged sweep
HEADS_SWEEP_LOG_MAX_B = 8192    # one logged sweep (the page's POST)

# ---- chatter test (sandswing chatter.py, laser.pwm_hz) ------------------------
# Does a drive below 100 % (the laser chopped by its PWM) make the comparator
# chatter?  The page sets a drive and a PWM speed, starts the Pico's counter,
# has sandtest turn the vane through the beam `passes` round trips (each
# crosses the beam twice: 4 transitions), stops the counter and keeps one
# HeadChatter row per run.  settings.json "sandheads": {"chatter": {...}}.
HEADS_PWM_HZ_MIN = 200          # sandswing tune.LASER_PWM_HZ_MIN
HEADS_PWM_HZ_MAX = 150000       # sandswing tune.LASER_PWM_HZ_MAX
HEADS_PWM_HZ_NOW = 1000         # the firmware's default (today's speed)
HEADS_CHATTER_OPS = ("start", "stop", "report")
HEADS_CHATTER_GAP_MIN_MS = 1    # sandswing chatter.CHATTER_GAP_MIN_MS
HEADS_CHATTER_GAP_MAX_MS = 250  # sandswing chatter.CHATTER_GAP_MAX_MS (MIN_STROKE_GAP_MS)
HEADS_CHATTER_SETTINGS_KEY = "chatter"     # under HEADS_SWEEP_SETTINGS_KEY
HEADS_CHATTER_PCT_MAX = 100          # drives_pct: whole percents of full drive, 1..this
HEADS_CHATTER_DEFAULTS = {
    "passes": 10,               # sandtest round trips per run
    "speed_dps": 4.0,           # vane speed, shaft degrees a second (sandtest scan's default)
    "pad_deg": 2.0,             # past the head's window each side (sandtest scan's pad)
    "face": "reflector",        # the vane face turned to the head
    "fast_pwm_hz": 20000,       # "Run the set": the faster speed (the threshold PWM's, scope-tested)
    "drives_pct": [100, 52, 25],   # "Run the set": at today's speed, then the last at fast_pwm_hz
}
HEADS_CHATTER_TRANS_PER_PASS = 4   # a round trip crosses the beam twice: in and out each time
HEADS_CHATTER_LOG_MAX_B = 2048     # one logged run (the page's POST)
HEADS_CHATTER_END_MAX_LEN = 40
HEADS_CHATTER_LIST_MAX = 50        # rows the page shows
HEADS_CHATTER_PASSES_MAX = 1000
HEADS_CHATTER_COUNT_MAX = 16382    # a 14-bit CC saturates here

# ---- PT level log (day / night drift of the phototransistor) -----------------
# The heartbeat's body "pt" = [ch, volts, spread] (sandswing pt_level.brief, the
# Orange/White wire on GP27).  ingest_serial stores one HeadLevel row per wired
# head at most every PT_LOG_EVERY_S; /farm/heads/pt-log.csv?days=N reads them.
PT_LOG_EVERY_S = 300
PT_LOG_UID_MAX_LEN = 32         # the Pico's UID (16 hex) with room
PT_LOG_TOWER_MAX_LEN = 16       # "inactive", "active", "ringing_down"
PT_LOG_DAYS_DEFAULT = 7
PT_LOG_DAYS_MAX = 366
