"""Unit tests for db/ — schema integrity, FOREIGN KEY enforcement, queries."""

from __future__ import annotations

from pathlib import Path

import pytest

from db.connection import apply_schema, _open_connection


def test_schema_applies_cleanly(tmp_path: Path) -> None:
    """Schema should apply without errors on a fresh DB."""
    db = tmp_path / "test.db"
    apply_schema(db)  # should not raise


def test_foreign_key_enforced(tmp_path: Path) -> None:
    """Inserting an experiment with unknown strategy must fail."""
    db = tmp_path / "test.db"
    apply_schema(db)
    conn = _open_connection(db)
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO experiments (strategy, ticker, timeframe) VALUES (?, ?, ?)",
            ("nonexistent_strategy", "MNQ", "15m"),
        )
        conn.commit()
    conn.close()


def test_experiment_gate_check_constraint(tmp_path: Path) -> None:
    """Invalid gate value must be rejected by CHECK constraint."""
    db = tmp_path / "test.db"
    apply_schema(db)
    conn = _open_connection(db)
    # First insert a strategy
    conn.execute(
        "INSERT INTO strategies (name, family, param_space) VALUES (?, ?, ?)",
        ("test_strat", "test", "{}"),
    )
    conn.commit()
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO experiments (strategy, ticker, timeframe, gate) VALUES (?, ?, ?, ?)",
            ("test_strat", "MNQ", "15m", "INVALID_GATE"),
        )
        conn.commit()
    conn.close()


def test_seed_and_get_experiment(tmp_path: Path) -> None:
    """seed_experiment + get_experiment round-trip."""
    db = tmp_path / "test.db"
    apply_schema(db)
    conn = _open_connection(db)
    conn.execute(
        "INSERT INTO strategies (name, family, param_space) VALUES (?, ?, ?)",
        ("ema_rsi", "trend_following", '{"ema_fast": {"low": 3, "high": 10}}'),
    )
    conn.commit()

    from db.queries import seed_experiment, get_experiment
    import os

    os.environ["DB_PATH"] = str(db)

    exp_id = seed_experiment("ema_rsi", "MNQ", "15m", conn=conn)
    exp = get_experiment(exp_id, conn=conn)

    assert exp is not None
    assert exp.strategy == "ema_rsi"
    assert exp.ticker == "MNQ"
    assert exp.gate == "SCREEN"
    conn.close()


def test_advance_experiment_with_trade_pnl(tmp_path: Path) -> None:
    """trade_pnl round-trip via advance_experiment + load_trade_pnl."""
    db = tmp_path / "test.db"
    apply_schema(db)
    conn = _open_connection(db)

    # Apply migration to add trade_pnl column
    conn.execute("ALTER TABLE experiments ADD COLUMN trade_pnl TEXT;")
    conn.commit()

    conn.execute(
        "INSERT INTO strategies (name, family, param_space) VALUES (?, ?, ?)",
        ("ema_rsi", "trend_following", "{}"),
    )
    conn.commit()

    from db.queries import seed_experiment, advance_experiment, load_trade_pnl
    import json

    exp_id = seed_experiment("ema_rsi", "MNQ", "15m", conn=conn)

    pnl = [100.0, -50.0, 200.0, -30.0, 150.0]
    advance_experiment(
        exp_id, "IS_OPT",
        updates={"trade_pnl": json.dumps(pnl)},
        conn=conn,
    )
    loaded = load_trade_pnl(exp_id, conn=conn)

    assert loaded == pnl

    # Test None case
    exp_id2 = conn.execute(
        "INSERT INTO experiments (strategy, ticker, timeframe) VALUES (?, ?, ?)",
        ("ema_rsi", "MES", "15m"),
    ).lastrowid
    conn.commit()
    assert load_trade_pnl(exp_id2, conn=conn) is None

    conn.close()


def test_advance_experiment_rejects_invalid_columns(tmp_path: Path) -> None:
    """advance_experiment rejects column names not in the allowlist."""
    db = tmp_path / "test.db"
    apply_schema(db)
    conn = _open_connection(db)

    conn.execute(
        "INSERT INTO strategies (name, family, param_space) VALUES (?, ?, ?)",
        ("ema_rsi", "trend_following", "{}"),
    )
    conn.commit()

    from db.queries import seed_experiment, advance_experiment

    exp_id = seed_experiment("ema_rsi", "MNQ", "15m", conn=conn)

    with pytest.raises(ValueError, match="Invalid update columns"):
        advance_experiment(
            exp_id, "IS_OPT",
            updates={"malicious_column": "DROP TABLE"},
            conn=conn,
        )

    conn.close()
