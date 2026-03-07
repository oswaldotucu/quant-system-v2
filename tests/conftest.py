"""Shared test fixtures.

RULE: All backtest tests use synthetic data (no real CSVs).
RULE: All DB tests use tmp_db (fresh schema in temp dir).
RULE: Never use real OOS data in tests unless in regression/.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Override settings for tests (no real .env needed)
# ---------------------------------------------------------------------------

os.environ.setdefault("DATA_DIR", "/tmp/test_data")
os.environ.setdefault("DB_PATH", "/tmp/test_quant.db")
os.environ.setdefault("PINE_DIR", "/tmp/test_pine")
os.environ.setdefault("CHECKLIST_DIR", "/tmp/test_checklists")


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """Synthetic OHLCV from 2020-01-01 to 2026-01-01 (6 years, ~1560 trading days).

    Realistic micro-futures noise: 0.1-0.2% bar volatility, trending regime.
    Used in unit tests that need data WITHOUT touching real CSVs.
    """
    rng = np.random.default_rng(seed=42)
    n_bars = 78_000  # ~6 years at 15min (26 bars/day * 250 days * 6 years = 39K; use more for safety)

    # Random walk price series
    returns = rng.normal(0.00005, 0.001, n_bars)  # 0.1% avg bar volatility
    close = 15_000 * np.exp(np.cumsum(returns))
    high = close * (1 + rng.uniform(0, 0.002, n_bars))
    low = close * (1 - rng.uniform(0, 0.002, n_bars))
    open_ = close * (1 + rng.normal(0, 0.0005, n_bars))
    volume = rng.integers(100, 5000, n_bars)

    idx = pd.date_range("2020-01-01", periods=n_bars, freq="15min", tz="America/New_York")

    return pd.DataFrame({
        "open": open_, "high": high, "low": low, "close": close, "volume": volume
    }, index=idx)


@pytest.fixture
def ema_rsi_params() -> dict[str, Any]:
    """Proven EMA+RSI params — use in regression and integration tests."""
    return {
        "ema_fast": 5,
        "ema_slow": 21,
        "rsi_period": 9,
        "rsi_os": 35,
        "rsi_ob": 65,
        "tp_pct": 1.0,
        "sl_pct": 2.8,
    }


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Fresh SQLite DB in temp dir with schema applied."""
    from db.connection import apply_schema
    db_path = tmp_path / "test.db"
    apply_schema(db_path)
    return db_path


@pytest.fixture
def test_settings(tmp_path: Path) -> Any:
    """Settings with all paths pointed at tmp_path."""
    from config.settings import Settings
    return Settings(
        data_dir=tmp_path / "raw",
        db_path=tmp_path / "test.db",
        pine_dir=tmp_path / "pine",
        checklist_dir=tmp_path / "checklists",
    )
