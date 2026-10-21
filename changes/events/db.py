"""db.py -- SQLite pragmas for a long-running writer beside gunicorn.

WAL lets the kiosk read while ingest writes; synchronous=NORMAL cuts
fsyncs (SD card wear); busy_timeout waits for a lock instead of raising
"database is locked".  Applied to every new connection, SQLite only.
"""

from . import constants as C

PRAGMAS = (
    "PRAGMA journal_mode=%s" % C.SQLITE_JOURNAL_MODE,
    "PRAGMA synchronous=%s" % C.SQLITE_SYNCHRONOUS,
    "PRAGMA busy_timeout=%d" % C.SQLITE_BUSY_TIMEOUT_MS,
)


def apply_pragmas(connection):
    """connection: anything with cursor() (Django wrapper or sqlite3)."""
    cur = connection.cursor()
    try:
        for sql in PRAGMAS:
            cur.execute(sql)
    finally:
        cur.close()


def on_connection_created(sender, connection, **kwargs):
    if connection.vendor == C.SQLITE_VENDOR:
        apply_pragmas(connection)
