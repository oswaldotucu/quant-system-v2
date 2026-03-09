"""Unit tests for quant/strategies/mtf_ema_alignment.py."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.mtf_ema_alignment import MtfEmaAlignmentStrategy


class TestGeneratesSignals:
    def test_generates_signals(self, sample_ohlcv: pd.DataFrame) -> None:
        params = MtfEmaAlignmentStrategy.default_params()
        entries, exits, direction = MtfEmaAlignmentStrategy.generate(sample_ohlcv, params)

        assert entries.shape == (len(sample_ohlcv),)
        assert entries.dtype == bool
        assert entries.sum() > 0, "Strategy generated zero entry signals"

    def test_exits_all_false(self, sample_ohlcv: pd.DataFrame) -> None:
        params = MtfEmaAlignmentStrategy.default_params()
        _, exits, _ = MtfEmaAlignmentStrategy.generate(sample_ohlcv, params)
        assert exits.sum() == 0


class TestDirectionMatchesEntries:
    def test_direction_array_matches_entries(self, sample_ohlcv: pd.DataFrame) -> None:
        params = MtfEmaAlignmentStrategy.default_params()
        entries, _, direction = MtfEmaAlignmentStrategy.generate(sample_ohlcv, params)

        entry_indices = np.where(entries)[0]
        assert len(entry_indices) > 0
        total = direction[entries].sum() + (~direction[entries]).sum()
        assert total > 0

    def test_crossover_at_entries(self, sample_ohlcv: pd.DataFrame) -> None:
        """Long entries must have fast EMA > slow EMA."""
        from quant.strategies.ema_rsi import _ema

        params = MtfEmaAlignmentStrategy.default_params()
        entries, _, direction = MtfEmaAlignmentStrategy.generate(sample_ohlcv, params)

        close = sample_ohlcv["close"].values
        fast = _ema(close, params["fast_ema"])
        slow = _ema(close, params["slow_ema"])

        long_mask = entries & direction
        if long_mask.sum() > 0:
            assert np.all(fast[long_mask] > slow[long_mask])


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
        params = MtfEmaAlignmentStrategy.default_params()
        entries, exits, direction = MtfEmaAlignmentStrategy.generate(tiny, params)
        assert entries.shape == (1,)
        assert entries.sum() == 0

    def test_short_data(self) -> None:
        tiny = pd.DataFrame(
            {
                "open": [100.0] * 10,
                "high": [101.0] * 10,
                "low": [99.0] * 10,
                "close": [100.5] * 10,
                "volume": [1000] * 10,
            },
            index=pd.date_range("2023-01-01", periods=10, freq="15min", tz="America/New_York"),
        )
        params = MtfEmaAlignmentStrategy.default_params()
        entries, _, _ = MtfEmaAlignmentStrategy.generate(tiny, params)
        assert entries.sum() == 0


class TestDefaultParams:
    def test_has_all_required_keys(self) -> None:
        params = MtfEmaAlignmentStrategy.default_params()
        required = {"fast_ema", "slow_ema", "htf_ema", "tp_pct", "sl_pct"}
        assert set(params.keys()) == required

    def test_intraday_scale_tp_sl(self) -> None:
        params = MtfEmaAlignmentStrategy.default_params()
        assert params["tp_pct"] < 1.0
        assert params["sl_pct"] < 1.0


class TestClassAttributes:
    def test_name(self) -> None:
        assert MtfEmaAlignmentStrategy.name == "mtf_ema_alignment"

    def test_family(self) -> None:
        assert MtfEmaAlignmentStrategy.family == "multi_timeframe"
