#!/usr/bin/env python3
"""Seed level-based experiments into the V2 pipeline.

Seeds 51 experiments based on Sentinel's highest-value combinations:
- 6 level types x multiple filter types x 3 instruments x 5m timeframe

The level_type and filter_type are stored in the `notes` field as
"level=<type>,filter=<type>". The pipeline must parse these notes to
inject level_type/filter_type into the params dict before running
the strategy.

Convention:
    notes = "level=annual,filter=macd"
    -> params["level_type"] = "annual", params["filter_type"] = "macd"

Schema note:
    The default unique index on (strategy, ticker, timeframe) would block
    multiple level_breakout experiments for the same instrument. This script
    migrates the index to include COALESCE(notes, '') so each
    level/filter combo is treated as a distinct experiment.

Run: uv run python scripts/seed_level_experiments.py
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from db.connection import get_conn  # noqa: E402
from quant.strategies.registry import STRATEGY_REGISTRY  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Experiment definitions — 51 total
# ---------------------------------------------------------------------------

EXPERIMENTS: list[dict[str, str]] = []

# Priority 1 (Sentinel's top alpha sources):

# ANNUAL x {UF, MACD, EMA} x {MNQ, MES, MGC} x 5m = 9
for filt in ["unfiltered", "macd", "ema"]:
    for ticker in ["MNQ", "MES", "MGC"]:
        EXPERIMENTS.append(
            {
                "strategy": "level_breakout",
                "ticker": ticker,
                "timeframe": "5m",
                "level_type": "annual",
                "filter_type": filt,
            }
        )

# SEMI x {UF, MACD, EMA, BB} x {MNQ, MES, MGC} x 5m = 12
for filt in ["unfiltered", "macd", "ema", "bb"]:
    for ticker in ["MNQ", "MES", "MGC"]:
        EXPERIMENTS.append(
            {
                "strategy": "level_breakout",
                "ticker": ticker,
                "timeframe": "5m",
                "level_type": "semiannual",
                "filter_type": filt,
            }
        )

# QUARTERLY x {UF, MACD, EMA, KC} x {MNQ, MES, MGC} x 5m = 12
for filt in ["unfiltered", "macd", "ema", "kc"]:
    for ticker in ["MNQ", "MES", "MGC"]:
        EXPERIMENTS.append(
            {
                "strategy": "level_breakout",
                "ticker": ticker,
                "timeframe": "5m",
                "level_type": "quarterly",
                "filter_type": filt,
            }
        )

# Priority 2 (proven contributors):

# MONTHLY x {MACD, UF} x {MNQ, MES, MGC} x 5m = 6
for filt in ["macd", "unfiltered"]:
    for ticker in ["MNQ", "MES", "MGC"]:
        EXPERIMENTS.append(
            {
                "strategy": "level_breakout",
                "ticker": ticker,
                "timeframe": "5m",
                "level_type": "monthly",
                "filter_type": filt,
            }
        )

# PDHL x {MACD, BB} x {MNQ, MES, MGC} x 5m = 6
for filt in ["macd", "bb"]:
    for ticker in ["MNQ", "MES", "MGC"]:
        EXPERIMENTS.append(
            {
                "strategy": "level_breakout",
                "ticker": ticker,
                "timeframe": "5m",
                "level_type": "pdhl",
                "filter_type": filt,
            }
        )

# OR30 x {MACD, KC} x {MNQ, MES, MGC} x 5m = 6
for filt in ["macd", "kc"]:
    for ticker in ["MNQ", "MES", "MGC"]:
        EXPERIMENTS.append(
            {
                "strategy": "level_breakout",
                "ticker": ticker,
                "timeframe": "5m",
                "level_type": "or30",
                "filter_type": filt,
            }
        )

if len(EXPERIMENTS) != 51:  # noqa: PLR2004
    raise RuntimeError(f"Expected 51 experiments, got {len(EXPERIMENTS)}")


# ---------------------------------------------------------------------------
# Schema migration: widen unique index to include notes
# ---------------------------------------------------------------------------


def _migrate_unique_index(conn: sqlite3.Connection) -> None:
    """Replace the experiments unique index to include notes.

    The original index is:
        CREATE UNIQUE INDEX idx_experiments_unique
            ON experiments(strategy, ticker, timeframe)
            WHERE gate NOT IN ('REJECTED');

    We need to include COALESCE(notes, '') so that different
    level_type/filter_type combos are treated as distinct experiments.
    """
    # Check if migration is needed by trying to inspect the index
    rows = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_experiments_unique'"
    ).fetchall()

    if not rows:
        log.info("Unique index not found — creating with notes included")
    else:
        index_sql = rows[0][0]
        if index_sql is not None and "notes" in index_sql.lower():
            log.info("Unique index already includes notes — no migration needed")
            return
        log.info("Migrating unique index to include notes column")

    conn.execute("DROP INDEX IF EXISTS idx_experiments_unique")
    conn.execute(
        """
        CREATE UNIQUE INDEX idx_experiments_unique
            ON experiments(strategy, ticker, timeframe, COALESCE(notes, ''))
            WHERE gate NOT IN ('REJECTED')
        """
    )
    conn.commit()
    log.info("Unique index migrated successfully")


# ---------------------------------------------------------------------------
# Seeding logic
# ---------------------------------------------------------------------------


def _ensure_strategy_in_db(conn: sqlite3.Connection) -> None:
    """Register level_breakout in the strategies table if not already present."""
    row = conn.execute(
        "SELECT COUNT(*) FROM strategies WHERE name = ?", ("level_breakout",)
    ).fetchone()
    if row is not None and row[0] > 0:
        return

    import json

    from quant.optimizer.param_space import get_param_space

    param_space = get_param_space("level_breakout")
    conn.execute(
        """
        INSERT INTO strategies (name, family, description, param_space)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(name) DO NOTHING
        """,
        ("level_breakout", "level_breakout", None, json.dumps(param_space)),
    )
    conn.commit()
    log.info("Registered level_breakout in strategies table")


def main() -> None:
    """Seed all level-based experiments."""
    # Validate strategy is in registry
    if "level_breakout" not in STRATEGY_REGISTRY:
        log.error("level_breakout not found in STRATEGY_REGISTRY — aborting")
        sys.exit(1)

    log.info("Seeding %d level-based experiments...", len(EXPERIMENTS))

    conn = get_conn()
    _migrate_unique_index(conn)
    _ensure_strategy_in_db(conn)

    seeded = 0
    skipped = 0
    errors = 0

    for exp in EXPERIMENTS:
        notes = f"level={exp['level_type']},filter={exp['filter_type']}"

        # Check for existing non-rejected experiment with same key
        cursor = conn.execute(
            """SELECT COUNT(*) FROM experiments
               WHERE strategy = ? AND ticker = ? AND timeframe = ?
               AND notes = ? AND gate != 'REJECTED'""",
            (exp["strategy"], exp["ticker"], exp["timeframe"], notes),
        )
        row = cursor.fetchone()
        count = row[0] if row is not None else 0

        if count > 0:
            skipped += 1
            continue

        # Priority: P1 experiments (annual, semiannual, quarterly) get higher priority
        priority = 10 if exp["level_type"] in ("annual", "semiannual", "quarterly") else 5

        try:
            conn.execute(
                """
                INSERT INTO experiments (strategy, ticker, timeframe, notes, priority)
                VALUES (?, ?, ?, ?, ?)
                """,
                (exp["strategy"], exp["ticker"], exp["timeframe"], notes, priority),
            )
            seeded += 1
        except sqlite3.IntegrityError as e:
            log.warning(
                "Skipping %s/%s/%s (%s): %s",
                exp["strategy"],
                exp["ticker"],
                exp["timeframe"],
                notes,
                e,
            )
            skipped += 1
        except sqlite3.Error as e:
            log.error(
                "Error seeding %s/%s/%s (%s): %s",
                exp["strategy"],
                exp["ticker"],
                exp["timeframe"],
                notes,
                e,
            )
            errors += 1

    conn.commit()
    log.info(
        "Done: %d seeded, %d skipped (already exist), %d errors",
        seeded,
        skipped,
        errors,
    )
    log.info("Total experiments defined: %d", len(EXPERIMENTS))

    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
