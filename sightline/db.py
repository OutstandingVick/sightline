"""Durable storage: Hermes' plugin_db() when running inside Hermes, a local file otherwise."""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager

from . import events

# One process-wide lock around "check cap + reserve spend". SQLite's BEGIN IMMEDIATE
# additionally serialises writers across processes (e.g. CLI + gateway).
SPEND_LOCK = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS grants (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
    seq INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    event TEXT NOT NULL,
    data TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    path = os.environ.get("SIGHTLINE_DB_PATH")
    if path:
        conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    else:
        try:
            from plugins.plugin_storage import plugin_db
        except ImportError:  # outside Hermes: keep dev state next to the user, not in the repo
            conn = sqlite3.connect(os.path.expanduser("~/.sightline-dev.db"),
                                   check_same_thread=False, isolation_level=None)
        else:
            conn = plugin_db("sightline")
            conn.isolation_level = None  # we manage transactions explicitly
    conn.executescript(SCHEMA)
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection | None = None):
    """BEGIN IMMEDIATE … COMMIT under the process lock; rolls back on error."""
    own = conn is None
    conn = conn or connect()
    with SPEND_LOCK:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            events.discard()
            raise
        else:
            conn.execute("COMMIT")
        finally:
            if own:
                conn.close()
    events.flush()  # after commit, outside the lock: the pane re-reads committed state
