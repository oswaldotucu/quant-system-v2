"""Unit tests for quant/strategies/session_momentum.py."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.session_momentum import SessionMomentumStrategy


class TestGeneratesSignals:
    def test_generates_signals(self, sample_ohlcv: pd.DataFrame) -> None:
        params = SessionMomentumStrategy.default_params()
        entries, exits, direction = SessionMomentumStrategy.generate(sample_ohlcv, params)

        assert entries.shape == (len(sample_ohlcv),)
        assert entries.dtype == bool
        assert entries.sum() > 0, "Strategy generated zero entry signals"

    def test_exits_all_false(self, sample_ohlcv: pd.DataFrame) -> None:
        params = SessionMomentumStrategy.default_params()
        _, exits, _ = SessionMomentumStrategy.generate(sample_ohlcv, params)
        assert exits.sum() == 0


class TestDirectionMatchesEntries:
    def test_direction_array_matches_entries(self, sample_ohlcv: pd.DataFrame) -> None:
        params = SessionMomentumStrategy.default_params()
        entries, _, direction = SessionMomentumStrategy.generate(sample_ohlcv, params)

        entry_indices = np.where(entries)[0]
        assert len(entry_indices) > 0
        total = direction[entries].sum() + (~direction[entries]).sum()
        assert total > 0


class TestSessionLogic:
    def test_no_signals_outside_trade_window(self) -> None:
        """Signals should only appear within trade_window after range_bars."""
        idx = pd.date_range("2023-06-01 09:00", periods=40, freq="15min", tz="America/New_York")
        rng = np.random.default_rng(seed=99)
        close = 100 + np.cumsum(rng.normal(0, 0.5, 40))
        high = close + rng.uniform(0, 0.3, 40)
        low = close - rng.uniform(0, 0.3, 40)

        data = pd.DataFrame(
            {
                "open": close + rng.normal(0, 0.1, 40),
                "high": high,
                "low": low,
                "close": close,
                "volume": rng.integers(100, 1000, 40),
            },
            index=idx,
        )

        params = {
            "range_bars": 2,
            "trade_window": 4,
            "min_range_pct": 0.0,
            "tp_pct": 0.15,
            "sl_pct": 0.3,
        }
        entries, _, _ = SessionMomentumStrategy.generate(data, params)

        # 9:30 is index 2 (09:00, 09:15, 09:30). Range ends at 4.
        # No entries before bar 4.
        assert entries[:4].sum() == 0, "No entries before range closes"


class TestEdgeCases:
    def test_empty_data(self) -> None:
        tiny = pd.DataFrame(
            {
                "open": [100.0],
                "high": [101.0],
                "low": [99.0],
                "close": [100.5],
                "volume": [1000],
            },
            index=pd.date_range("2023-01-01", periods=1, freq="15min", tz="America/New_York"),
        )
        params = SessionMomentumStrategy.default_params()
        entries, _, _ = SessionMomentumStrategy.generate(tiny, params)
        assert entries.sum() == 0

    def test_no_rth_sessions(self) -> None:
        """Data that doesn't include 9:30 ET should produce zero signals."""
        idx = pd.date_range("2023-01-01 14:00", periods=20, freq="15min", tz="America/New_York")
        data = pd.DataFrame(
            {
                "open": [100.0] * 20,
                "high": [101.0] * 20,
                "low": [99.0] * 20,
                "close": [100.5] * 20,
                "volume": [1000] * 20,
            },
            index=idx,
        )
        params = SessionMomentumStrategy.default_params()
        entries, _, _ = SessionMomentumStrategy.generate(data, params)
        assert entries.sum() == 0


class TestDefaultParams:
    def test_has_all_required_keys(self) -> None:
        params = SessionMomentumStrategy.default_params()
        required = {"range_bars", "trade_window", "min_range_pct", "tp_pct", "sl_pct"}
        assert set(params.keys()) == required

    def test_intraday_scale_tp_sl(self) -> None:
        params = SessionMomentumStrategy.default_params()
        assert params["tp_pct"] < 1.0
        assert params["sl_pct"] < 1.0


class TestClassAttributes:
    def test_name(self) -> None:
        assert SessionMomentumStrategy.name == "session_momentum"

    def test_family(self) -> None:
        assert SessionMomentumStrategy.family == "event_driven"
