"""Simple integer-versioned schema migration runner.

Usage:
    from db.migrations import run_migrations
    run_migrations(db_path)

Migrations are SQL strings in the MIGRATIONS list below.
Each entry is applied exactly once, tracked in the 'schema_version' pragma.
"""

from __future__ import annotations

import logging
from pathlib import Path

from db.connection import _open_connection

log = logging.getLogger(__name__)

# Add new migrations at the end. Never edit existing ones.
MIGRATIONS: list[str] = [
    # v1: add trade_pnl column for portfolio correlation analysis
    "ALTER TABLE experiments ADD COLUMN trade_pnl TEXT;",
]


def run_migrations(db_path: Path) -> None:
    """Apply any pending migrations to the database."""
    conn = _open_connection(db_path)
    try:
        current_version = conn.execute("PRAGMA user_version;").fetchone()[0]
        pending = MIGRATIONS[current_version:]

        if not pending:
            log.debug("DB schema is up to date (version %d)", current_version)
            return

        for i, sql in enumerate(pending, start=current_version + 1):
            log.info("Applying migration %d...", i)
            conn.executescript(sql)
            conn.execute(f"PRAGMA user_version = {i};")
            conn.commit()

        log.info("Migrations complete. DB at version %d", current_version + len(pending))
    finally:
        conn.close()
