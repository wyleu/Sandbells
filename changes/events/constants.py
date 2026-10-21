"""constants.py -- names and limits for sand.event/v1 ingest.

Every literal the events app relies on lives here, so parse.py and
models.py hold no magic numbers or strings.
"""

SCHEMA_EVENT_V1 = "sand.event/v1"

# ---- event types ----------------------------------------------------------
TYPE_STROKE = "stroke"
KNOWN_EVENT_TYPES = (TYPE_STROKE,)

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

# ---- batched store (store.py) --------------------------------------------
# A peal is a few strokes per second; one commit per batch spares the SD card.
STORE_FLUSH_COUNT = 64          # flush when this many events are buffered
STORE_FLUSH_INTERVAL_S = 5.0    # ...or when the oldest has waited this long
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

# ---- ingest: logging (ingest.py) -----------------------------------------
LOGGER_NAME = "events.ingest"
SUMMARY_INTERVAL_S = 60.0       # one INFO summary line per this
REJECT_LOG_INTERVAL_S = 60.0    # at most one WARNING per reject reason per this

# ---- ingest: URL from the existing Sandbells settings.json (config.py) -----
SANDBELLS_SETTINGS_PATH = "/etc/sandbells/settings.json"
SANDBELLS_SETTINGS_ENV = "SANDBELLS_SETTINGS"   # same override as the scripts
CONCENTRATOR_FAMILY = "sandswing"   # status.devices[].family to ingest from
