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
KNOWN_EVENT_TYPES = (TYPE_STROKE, TYPE_LINK, TYPE_INGEST)

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

# ---- live list (farm page 3) ----------------------------------------------
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

# ---- page 3 link widget (link_widget.js, api.link) -------------------------
LINK_POLL_MS = 2000             # widget poll of /events/api/link/
LINK_STALE_MS = 15000           # no Pico heartbeat this long: grey (3 missed)
LINK_LOST_MS = 30000            # ...this long, or ingest down: red LOST
INGEST_FILE_STALE_MS = 15000    # link file not rewritten: ingest not running
