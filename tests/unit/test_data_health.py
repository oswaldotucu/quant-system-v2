"""Tests for data health reporting."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest


def _make_csv(path: Path, start: str, periods: int, freq: str = "15min") -> None:
    """Write a synthetic CSV to path."""
    rng = np.random.default_rng(seed=42)
    idx = pd.date_range(start, periods=periods, freq=freq, tz="America/New_York")
    close = 15000 + np.cumsum(rng.normal(0, 1, periods))
    df = pd.DataFrame({
        "open": close, "high": close + 1, "low": close - 1,
        "close": close, "volume": rng.integers(100, 5000, periods),
    }, index=idx)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index_label="datetime")


class TestDataHealth:

    def test_returns_all_files(self, tmp_path: Path) -> None:
        """Health check returns status for all 9 instrument/timeframe combos."""
        from quant.data.health import get_data_health

        data_dir = tmp_path / "raw"
        data_dir.mkdir()

        from config.instruments import TICKERS, TIMEFRAMES
        for ticker in TICKERS:
            for tf in TIMEFRAMES:
                freq = {"1m": "1min", "5m": "5min", "15m": "15min"}[tf]
                _make_csv(data_dir / f"{ticker}_{tf}.csv", "2024-01-02 18:00", 100, freq)

        health = get_data_health(data_dir)
        assert len(health) == 9
        for key, info in health.items():
            assert info["status"] in ("fresh", "stale", "missing")
            assert info["bars"] == 100
            assert "last_bar" in info

    def test_missing_file(self, tmp_path: Path) -> None:
        """Missing CSV returns 'missing' status."""
        from quant.data.health import get_data_health

        data_dir = tmp_path / "raw"
        data_dir.mkdir()

        health = get_data_health(data_dir)
        for info in health.values():
            assert info["status"] == "missing"
            assert info["bars"] == 0

    def test_stale_file(self, tmp_path: Path) -> None:
        """File with last bar > 48h ago is 'stale'."""
        from quant.data.health import get_data_health

        data_dir = tmp_path / "raw"
        _make_csv(data_dir / "MNQ_15m.csv", "2020-01-02 18:00", 100)

        health = get_data_health(data_dir)
        assert health["MNQ_15m"]["status"] == "stale"
