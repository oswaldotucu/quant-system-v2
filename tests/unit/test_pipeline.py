"""Unit tests for quant/pipeline/ — gates.py and runner.py.

Tests the pipeline core: gate sequence, GateResult immutability, run_gate dispatch,
and run_next_gate DB side effects (advance/reject/error).

RULE: All gate execution is mocked — no real backtest engine calls.
RULE: DB tests use tmp_path with fresh schema.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from db.connection import _open_connection, apply_schema
from db.migrations import run_migrations
from db.queries import Experiment, get_experiment, seed_experiment
from quant.pipeline.gates import GATE_SEQUENCE, GateResult, run_gate
from quant.pipeline.runner import run_next_gate

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_experiment(
    *,
    exp_id: int = 1,
    strategy: str = "ema_rsi",
    ticker: str = "MNQ",
    timeframe: str = "15m",
    gate: str = "SCREEN",
    params: dict[str, Any] | None = None,
    priority: int = 0,
    error_msg: str | None = None,
) -> Experiment:
    """Create a minimal Experiment for unit tests (no DB needed)."""
    return Experiment(
        id=exp_id,
        strategy=strategy,
        ticker=ticker,
        timeframe=timeframe,
        gate=gate,
        params=params,
        priority=priority,
        error_msg=error_msg,
    )


def _setup_test_db(tmp_path: Path) -> Path:
    """Create a fresh test DB with schema and migrations applied."""
    db_path = tmp_path / "test.db"
    apply_schema(db_path)
    run_migrations(db_path)
    # Insert a strategy so FK constraint passes
    conn = _open_connection(db_path)
    conn.execute(
        "INSERT INTO strategies (name, family, param_space) VALUES (?, ?, ?)",
        ("ema_rsi", "trend_following", '{"ema_fast": {"low": 3, "high": 10}}'),
    )
    conn.commit()
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# Gate Sequence Tests
# ---------------------------------------------------------------------------


class TestGateSequence:
    def test_gate_sequence_has_all_gates(self) -> None:
        """GATE_SEQUENCE should have SCREEN through DEPLOYED plus REJECTED."""
        expected_gates = {
            "SCREEN",
            "IS_OPT",
            "OOS_VAL",
            "CONFIRM",
            "FWD_READY",
            "DEPLOYED",
            "REJECTED",
        }
        assert set(GATE_SEQUENCE.keys()) == expected_gates

    def test_gate_sequence_terminal_states(self) -> None:
        """DEPLOYED and REJECTED should map to None (terminal)."""
        assert GATE_SEQUENCE["DEPLOYED"] is None
        assert GATE_SEQUENCE["REJECTED"] is None

    def test_gate_sequence_progression(self) -> None:
        """Gates should progress SCREEN -> IS_OPT -> OOS_VAL -> CONFIRM -> FWD_READY -> DEPLOYED."""
        assert GATE_SEQUENCE["SCREEN"] == "IS_OPT"
        assert GATE_SEQUENCE["IS_OPT"] == "OOS_VAL"
        assert GATE_SEQUENCE["OOS_VAL"] == "CONFIRM"
        assert GATE_SEQUENCE["CONFIRM"] == "FWD_READY"
        assert GATE_SEQUENCE["FWD_READY"] == "DEPLOYED"


# ---------------------------------------------------------------------------
# GateResult Tests
# ---------------------------------------------------------------------------


class TestGateResult:
    def test_gate_result_is_frozen(self) -> None:
        """GateResult should be immutable (frozen dataclass)."""
        result = GateResult(gate="SCREEN", passed=True, reason="ok", metrics={})
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.passed = False  # type: ignore[misc]

    def test_gate_result_fields(self) -> None:
        """GateResult should contain all expected fields."""
        result = GateResult(
            gate="SCREEN",
            passed=True,
            reason="PF=1.5 trades=50",
            metrics={"screen_pf": 1.5, "screen_trades": 50},
        )
        assert result.gate == "SCREEN"
        assert result.passed is True
        assert result.reason == "PF=1.5 trades=50"
        assert result.metrics == {"screen_pf": 1.5, "screen_trades": 50}


# ---------------------------------------------------------------------------
# run_gate Tests (dispatch logic, no real backtest)
# ---------------------------------------------------------------------------


class TestRunGate:
    """Tests for run_gate dispatch logic.

    run_gate calls get_settings(), get_strategy(), and get_ohlcv() before the
    match statement, so we must mock all three to test dispatch behavior.
    """

    def test_run_gate_unknown_gate_raises(self) -> None:
        """run_gate with unknown gate name should raise ValueError."""
        exp = _make_experiment(gate="NONEXISTENT")
        with (
            patch("quant.pipeline.gates.get_settings"),
            patch("quant.pipeline.gates.get_strategy"),
            patch("quant.pipeline.gates.get_ohlcv"),
        ):
            with pytest.raises(ValueError, match="Unknown gate"):
                run_gate(exp, "NONEXISTENT")

    def test_run_gate_fwd_ready_raises(self) -> None:
        """FWD_READY gate should raise ValueError (human-only)."""
        exp = _make_experiment(gate="FWD_READY")
        with (
            patch("quant.pipeline.gates.get_settings"),
            patch("quant.pipeline.gates.get_strategy"),
            patch("quant.pipeline.gates.get_ohlcv"),
        ):
            with pytest.raises(ValueError, match="human approval"):
                run_gate(exp, "FWD_READY")


# ---------------------------------------------------------------------------
# run_next_gate Tests (mock gate execution, test DB routing)
# ---------------------------------------------------------------------------


class TestRunNextGate:
    def test_run_next_gate_pass_advances(self, tmp_path: Path) -> None:
        """When gate passes, experiment should advance to next gate."""
        db_path = _setup_test_db(tmp_path)

        import config.settings as settings_mod
        import db.connection as conn_mod

        # Save and reset singletons
        old_settings = settings_mod._settings
        old_conn = getattr(conn_mod._local, "conn", None)
        try:
            settings_mod._settings = settings_mod.Settings(
                data_dir=tmp_path / "raw",
                db_path=db_path,
                pine_dir=tmp_path / "pine",
                checklist_dir=tmp_path / "checklists",
            )
            conn_mod._local.conn = None  # force re-open with new path

            exp_id = seed_experiment("ema_rsi", "MNQ", "15m")
            exp = get_experiment(exp_id)
            assert exp is not None
            assert exp.gate == "SCREEN"

            mock_result = GateResult(
                gate="SCREEN",
                passed=True,
                reason="PF=1.5 trades=50",
                metrics={"screen_pf": 1.5, "screen_trades": 50},
            )
            with patch("quant.pipeline.runner.run_gate", return_value=mock_result):
                result = run_next_gate(exp)

            assert result.passed is True
            assert result.gate == "SCREEN"

            # Verify DB state: experiment should be at IS_OPT
            updated = get_experiment(exp_id)
            assert updated is not None
            assert updated.gate == "IS_OPT"
            assert updated.screen_pf == 1.5
            assert updated.screen_trades == 50
        finally:
            settings_mod._settings = old_settings
            conn_mod.close_conn()
            if old_conn is not None:
                conn_mod._local.conn = old_conn

    def test_run_next_gate_fail_rejects(self, tmp_path: Path) -> None:
        """When gate fails, experiment should be marked REJECTED."""
        db_path = _setup_test_db(tmp_path)

        import config.settings as settings_mod
        import db.connection as conn_mod

        old_settings = settings_mod._settings
        old_conn = getattr(conn_mod._local, "conn", None)
        try:
            settings_mod._settings = settings_mod.Settings(
                data_dir=tmp_path / "raw",
                db_path=db_path,
                pine_dir=tmp_path / "pine",
                checklist_dir=tmp_path / "checklists",
            )
            conn_mod._local.conn = None

            exp_id = seed_experiment("ema_rsi", "MNQ", "15m")
            exp = get_experiment(exp_id)
            assert exp is not None

            mock_result = GateResult(
                gate="SCREEN",
                passed=False,
                reason="PF=0.8 trades=10",
                metrics={"screen_pf": 0.8, "screen_trades": 10},
            )
            with patch("quant.pipeline.runner.run_gate", return_value=mock_result):
                result = run_next_gate(exp)

            assert result.passed is False

            # Verify DB state: experiment should be REJECTED
            updated = get_experiment(exp_id)
            assert updated is not None
            assert updated.gate == "REJECTED"
            assert updated.error_msg is not None
            assert "SCREEN" in updated.error_msg
        finally:
            settings_mod._settings = old_settings
            conn_mod.close_conn()
            if old_conn is not None:
                conn_mod._local.conn = old_conn

    def test_run_next_gate_exception_marks_error(self, tmp_path: Path) -> None:
        """When gate raises exception, experiment should have error_msg set."""
        db_path = _setup_test_db(tmp_path)

        import config.settings as settings_mod
        import db.connection as conn_mod

        old_settings = settings_mod._settings
        old_conn = getattr(conn_mod._local, "conn", None)
        try:
            settings_mod._settings = settings_mod.Settings(
                data_dir=tmp_path / "raw",
                db_path=db_path,
                pine_dir=tmp_path / "pine",
                checklist_dir=tmp_path / "checklists",
            )
            conn_mod._local.conn = None

            exp_id = seed_experiment("ema_rsi", "MNQ", "15m")
            exp = get_experiment(exp_id)
            assert exp is not None

            with patch(
                "quant.pipeline.runner.run_gate",
                side_effect=RuntimeError("backtest engine crashed"),
            ):
                result = run_next_gate(exp)

            assert result.passed is False
            assert "Exception" in result.reason

            # Verify DB state: experiment should still be at SCREEN (not rejected)
            # but with error_msg set
            updated = get_experiment(exp_id)
            assert updated is not None
            assert updated.gate == "SCREEN"  # NOT rejected — allows retry
            assert updated.error_msg is not None
            assert "backtest engine crashed" in updated.error_msg
        finally:
            settings_mod._settings = old_settings
            conn_mod.close_conn()
            if old_conn is not None:
                conn_mod._local.conn = old_conn

    def test_run_next_gate_terminal_gate_noop(self, tmp_path: Path) -> None:
        """Experiment at terminal gate (DEPLOYED/REJECTED) returns early."""
        exp = _make_experiment(gate="DEPLOYED")
        result = run_next_gate(exp)

        assert result.passed is True
        assert result.reason == "terminal gate"

    def test_run_next_gate_rejected_terminal(self, tmp_path: Path) -> None:
        """Experiment at REJECTED gate returns early."""
        exp = _make_experiment(gate="REJECTED")
        result = run_next_gate(exp)

        assert result.passed is True
        assert result.reason == "terminal gate"

    def test_run_next_gate_result_includes_elapsed(self, tmp_path: Path) -> None:
        """Result from run_next_gate should include elapsed_s in metrics."""
        db_path = _setup_test_db(tmp_path)

        import config.settings as settings_mod
        import db.connection as conn_mod

        old_settings = settings_mod._settings
        old_conn = getattr(conn_mod._local, "conn", None)
        try:
            settings_mod._settings = settings_mod.Settings(
                data_dir=tmp_path / "raw",
                db_path=db_path,
                pine_dir=tmp_path / "pine",
                checklist_dir=tmp_path / "checklists",
            )
            conn_mod._local.conn = None

            exp_id = seed_experiment("ema_rsi", "MNQ", "15m")
            exp = get_experiment(exp_id)
            assert exp is not None

            mock_result = GateResult(
                gate="SCREEN",
                passed=True,
                reason="PF=2.0 trades=100",
                metrics={"screen_pf": 2.0, "screen_trades": 100},
            )
            with patch("quant.pipeline.runner.run_gate", return_value=mock_result):
                result = run_next_gate(exp)

            assert "elapsed_s" in result.metrics
            assert isinstance(result.metrics["elapsed_s"], float)
            assert result.metrics["elapsed_s"] >= 0.0
        finally:
            settings_mod._settings = old_settings
            conn_mod.close_conn()
            if old_conn is not None:
                conn_mod._local.conn = old_conn
