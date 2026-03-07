"""Thread-local SQLite connection management.

Every connection enforces:
- PRAGMA foreign_keys = ON
- PRAGMA journal_mode = DELETE  (WAL has issues on macOS Docker volume mounts)

Usage:
    from db.connection import get_conn

    with get_conn() as conn:
        conn.execute("SELECT ...")
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path

from config.settings import get_settings

log = logging.getLogger(__name__)

_local = threading.local()


def _open_connection(db_path: Path) -> sqlite3.Connection:
    """Open a new SQLite connection with required pragmas."""
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = DELETE;")
    return conn


def get_conn() -> sqlite3.Connection:
    """Return the thread-local connection, opening one if needed."""
    settings = get_settings()
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = _open_connection(settings.db_path)
        log.debug("Opened SQLite connection for thread %s", threading.current_thread().name)
    return _local.conn


def close_conn() -> None:
    """Close the thread-local connection."""
    if hasattr(_local, "conn") and _local.conn is not None:
        _local.conn.close()
        _local.conn = None


def apply_schema(db_path: Path) -> None:
    """Apply schema.sql to a fresh database. Idempotent if tables already exist."""
    schema_path = Path(__file__).parent / "schema.sql"
    conn = _open_connection(db_path)
    try:
        conn.executescript(schema_path.read_text())
        conn.commit()
        log.info("Schema applied to %s", db_path)
    finally:
        conn.close()
