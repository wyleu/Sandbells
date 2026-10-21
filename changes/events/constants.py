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
