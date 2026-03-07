"""All SQL queries in one place.

RULE: No raw SQL strings outside this file. Routes and logic call these functions only.
Every function takes explicit typed arguments. No f-string SQL.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from typing import Any

from db.connection import get_conn

log = logging.getLogger(__name__)


def _safe_commit(conn: sqlite3.Connection) -> None:
    """Commit or rollback on error. Prevents silent partial state."""
    try:
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        raise


# ---------------------------------------------------------------------------
# Data models (lightweight, no ORM)
# ---------------------------------------------------------------------------


@dataclass
class Strategy:
    id: int
    name: str
    family: str
    description: str | None
    param_space: dict[str, Any]


@dataclass
class Experiment:
    id: int
    strategy: str
    ticker: str
    timeframe: str
    gate: str
    params: dict[str, Any] | None
    priority: int
    error_msg: str | None
    # SCREEN gate results
    screen_pf: float | None = None
    screen_trades: int | None = None
    # IS_OPT gate results
    is_sharpe: float | None = None
    is_pf: float | None = None
    sens_min_pf: float | None = None
    # OOS_VAL gate results
    oos_pf: float | None = None
    oos_trades: int | None = None
    oos_sharpe: float | None = None
    oos_sortino: float | None = None
    oos_calmar: float | None = None
    oos_max_dd: float | None = None
    oos_max_dd_pct: float | None = None
    daily_pnl: float | None = None
    quarterly_wr: dict[str, float] | None = None
    # CONFIRM gate results
    p_ruin: float | None = None
    p_positive: float | None = None
    wf_windows: int | None = None
    cross_confirmed: int | None = None
    max_corr: float | None = None
    # Output
    notes: str | None = None
    pine_path: str | None = None
    checklist_path: str | None = None
    # Timestamps
    created_at: str | None = None
    updated_at: str | None = None


# ---------------------------------------------------------------------------
# strategies table
# ---------------------------------------------------------------------------


def upsert_strategy(
    name: str,
    family: str,
    description: str | None,
    param_space: dict[str, Any],
    conn: sqlite3.Connection | None = None,
) -> None:
    """Insert or update a strategy definition."""
    c = conn or get_conn()
    c.execute(
        """
        INSERT INTO strategies (name, family, description, param_space)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            family = excluded.family,
            description = excluded.description,
            param_space = excluded.param_space
        """,
        (name, family, description, json.dumps(param_space)),
    )
    _safe_commit(c)


def get_strategy(name: str, conn: sqlite3.Connection | None = None) -> Strategy | None:
    """Fetch a strategy by name."""
    c = conn or get_conn()
    row = c.execute("SELECT * FROM strategies WHERE name = ?", (name,)).fetchone()
    if row is None:
        return None
    return Strategy(
        id=row["id"],
        name=row["name"],
        family=row["family"],
        description=row["description"],
        param_space=json.loads(row["param_space"]),
    )


def list_strategies(conn: sqlite3.Connection | None = None) -> list[Strategy]:
    c = conn or get_conn()
    rows = c.execute("SELECT * FROM strategies ORDER BY name").fetchall()
    return [
        Strategy(
            id=r["id"],
            name=r["name"],
            family=r["family"],
            description=r["description"],
            param_space=json.loads(r["param_space"]),
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# experiments table
# ---------------------------------------------------------------------------


def seed_experiment(
    strategy: str,
    ticker: str,
    timeframe: str,
    priority: int = 0,
    conn: sqlite3.Connection | None = None,
) -> int:
    """Create a new experiment at SCREEN gate. Returns experiment id."""
    c = conn or get_conn()
    cursor = c.execute(
        """
        INSERT INTO experiments (strategy, ticker, timeframe, priority)
        VALUES (?, ?, ?, ?)
        """,
        (strategy, ticker, timeframe, priority),
    )
    _safe_commit(c)
    return cursor.lastrowid  # type: ignore[return-value]


def get_experiment(exp_id: int, conn: sqlite3.Connection | None = None) -> Experiment | None:
    c = conn or get_conn()
    row = c.execute("SELECT * FROM experiments WHERE id = ?", (exp_id,)).fetchone()
    if row is None:
        return None
    return _row_to_experiment(row)


def list_experiments_by_gate(
    gate: str,
    conn: sqlite3.Connection | None = None,
) -> list[Experiment]:
    c = conn or get_conn()
    rows = c.execute(
        "SELECT * FROM experiments WHERE gate = ? ORDER BY priority DESC, id",
        (gate,),
    ).fetchall()
    return [_row_to_experiment(r) for r in rows]


def list_pending_experiments(conn: sqlite3.Connection | None = None) -> list[Experiment]:
    """Experiments that have not yet been rejected or deployed — ready to advance."""
    c = conn or get_conn()
    rows = c.execute(
        """
        SELECT * FROM experiments
        WHERE gate NOT IN ('REJECTED', 'DEPLOYED')
        ORDER BY priority DESC, id
        """,
    ).fetchall()
    return [_row_to_experiment(r) for r in rows]


_LEADERBOARD_GATES = ("OOS_VAL", "CONFIRM", "FWD_READY", "DEPLOYED")


def list_experiments_past_gate(
    min_gate: str,
    conn: sqlite3.Connection | None = None,
) -> list[Experiment]:
    """Return experiments at or beyond *min_gate* in the pipeline.

    Valid values for *min_gate*: OOS_VAL, CONFIRM, FWD_READY, DEPLOYED.
    Results are ordered by oos_pf descending (nulls last).
    """
    if min_gate not in _LEADERBOARD_GATES:
        raise ValueError(
            f"Invalid min_gate '{min_gate}'. Must be one of {_LEADERBOARD_GATES}"
        )
    idx = _LEADERBOARD_GATES.index(min_gate)
    gates = _LEADERBOARD_GATES[idx:]
    placeholders = ", ".join("?" for _ in gates)
    c = conn or get_conn()
    rows = c.execute(
        f"SELECT * FROM experiments WHERE gate IN ({placeholders}) "  # noqa: S608
        "ORDER BY COALESCE(oos_pf, 0) DESC, id",
        gates,
    ).fetchall()
    return [_row_to_experiment(r) for r in rows]


_UPDATABLE_COLUMNS = frozenset({
    "params", "error_msg",
    "screen_pf", "screen_trades",
    "is_sharpe", "is_pf", "sens_min_pf",
    "oos_pf", "oos_trades", "oos_sharpe", "oos_sortino", "oos_calmar",
    "oos_max_dd", "oos_max_dd_pct", "daily_pnl", "quarterly_wr", "trade_pnl",
    "p_ruin", "p_positive", "wf_windows", "cross_confirmed", "max_corr",
    "notes", "pine_path", "checklist_path",
})


def advance_experiment(
    exp_id: int,
    new_gate: str,
    updates: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Move experiment to next gate and update result columns."""
    c = conn or get_conn()
    set_clauses = ["gate = ?"]
    values: list[Any] = [new_gate]

    if updates:
        invalid = set(updates.keys()) - _UPDATABLE_COLUMNS
        if invalid:
            raise ValueError(f"Invalid update columns: {invalid}")
        for key, val in updates.items():
            set_clauses.append(f"{key} = ?")
            values.append(val if not isinstance(val, dict) else json.dumps(val))

    values.append(exp_id)
    c.execute(
        f"UPDATE experiments SET {', '.join(set_clauses)} WHERE id = ?",  # noqa: S608
        values,
    )
    _safe_commit(c)


def mark_experiment_error(
    exp_id: int,
    error_msg: str,
    conn: sqlite3.Connection | None = None,
) -> None:
    c = conn or get_conn()
    c.execute(
        "UPDATE experiments SET error_msg = ? WHERE id = ?",
        (error_msg, exp_id),
    )
    _safe_commit(c)


def reject_experiment(
    exp_id: int,
    reason: str,
    conn: sqlite3.Connection | None = None,
) -> None:
    c = conn or get_conn()
    c.execute(
        "UPDATE experiments SET gate = 'REJECTED', error_msg = ? WHERE id = ?",
        (reason, exp_id),
    )
    _safe_commit(c)


# ---------------------------------------------------------------------------
# Aggregate queries
# ---------------------------------------------------------------------------


def count_experiments_by_gate(
    conn: sqlite3.Connection | None = None,
) -> dict[str, int]:
    """Return a dict mapping each gate name to its experiment count."""
    c = conn or get_conn()
    rows = c.execute(
        "SELECT gate, COUNT(*) as n FROM experiments GROUP BY gate"
    ).fetchall()
    return {row["gate"]: row["n"] for row in rows}


def get_last_activity(
    conn: sqlite3.Connection | None = None,
) -> str | None:
    """Return the most recent updated_at timestamp across all experiments."""
    c = conn or get_conn()
    row = c.execute(
        "SELECT MAX(updated_at) as last FROM experiments"
    ).fetchone()
    if row is None or row["last"] is None:
        return None
    return row["last"]


def count_total_experiments(
    conn: sqlite3.Connection | None = None,
) -> int:
    """Return total count of all experiments."""
    c = conn or get_conn()
    row = c.execute("SELECT COUNT(*) as n FROM experiments").fetchone()
    return row["n"] if row else 0


# ---------------------------------------------------------------------------
# trade_pnl storage (for portfolio correlation)
# ---------------------------------------------------------------------------


def load_trade_pnl(
    exp_id: int,
    conn: sqlite3.Connection | None = None,
) -> list[float] | None:
    """Load per-trade P&L for an experiment. Returns None if not stored."""
    c = conn or get_conn()
    row = c.execute("SELECT trade_pnl FROM experiments WHERE id = ?", (exp_id,)).fetchone()
    if row is None or row["trade_pnl"] is None:
        return None
    return json.loads(row["trade_pnl"])


# ---------------------------------------------------------------------------
# optuna_trials table
# ---------------------------------------------------------------------------


def insert_trial(
    exp_id: int,
    trial_num: int,
    params: dict[str, Any],
    is_sharpe: float,
    is_train_pf: float,
    is_val_pf: float,
    state: str = "complete",
    conn: sqlite3.Connection | None = None,
) -> None:
    c = conn or get_conn()
    c.execute(
        """
        INSERT INTO optuna_trials
            (exp_id, trial_num, params, is_sharpe, is_train_pf, is_val_pf, state)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (exp_id, trial_num, json.dumps(params), is_sharpe, is_train_pf, is_val_pf, state),
    )
    _safe_commit(c)


def get_best_trial(
    exp_id: int,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Return the trial with highest is_sharpe for this experiment."""
    c = conn or get_conn()
    row = c.execute(
        """
        SELECT * FROM optuna_trials
        WHERE exp_id = ? AND state = 'complete'
        ORDER BY is_sharpe DESC
        LIMIT 1
        """,
        (exp_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "trial_num": row["trial_num"],
        "params": json.loads(row["params"]),
        "is_sharpe": row["is_sharpe"],
        "is_train_pf": row["is_train_pf"],
        "is_val_pf": row["is_val_pf"],
    }


def count_trials(exp_id: int, conn: sqlite3.Connection | None = None) -> int:
    c = conn or get_conn()
    row = c.execute(
        "SELECT COUNT(*) as n FROM optuna_trials WHERE exp_id = ?", (exp_id,)
    ).fetchone()
    return row["n"] if row else 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_experiment(row: sqlite3.Row) -> Experiment:
    return Experiment(
        id=row["id"],
        strategy=row["strategy"],
        ticker=row["ticker"],
        timeframe=row["timeframe"],
        gate=row["gate"],
        params=json.loads(row["params"]) if row["params"] else None,
        priority=row["priority"],
        error_msg=row["error_msg"],
        # SCREEN
        screen_pf=row["screen_pf"],
        screen_trades=row["screen_trades"],
        # IS_OPT
        is_sharpe=row["is_sharpe"],
        is_pf=row["is_pf"],
        sens_min_pf=row["sens_min_pf"],
        # OOS_VAL
        oos_pf=row["oos_pf"],
        oos_trades=row["oos_trades"],
        oos_sharpe=row["oos_sharpe"],
        oos_sortino=row["oos_sortino"],
        oos_calmar=row["oos_calmar"],
        oos_max_dd=row["oos_max_dd"],
        oos_max_dd_pct=row["oos_max_dd_pct"],
        daily_pnl=row["daily_pnl"],
        quarterly_wr=json.loads(row["quarterly_wr"]) if row["quarterly_wr"] else None,
        # CONFIRM
        p_ruin=row["p_ruin"],
        p_positive=row["p_positive"],
        wf_windows=row["wf_windows"],
        cross_confirmed=row["cross_confirmed"],
        max_corr=row["max_corr"],
        # Output
        notes=row["notes"],
        pine_path=row["pine_path"],
        checklist_path=row["checklist_path"],
        # Timestamps
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
