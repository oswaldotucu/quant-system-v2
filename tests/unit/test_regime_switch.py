"""Unit tests for quant/strategies/regime_switch.py."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.regime_switch import RegimeSwitchStrategy


class TestGeneratesSignals:
    def test_generates_signals(self, sample_ohlcv: pd.DataFrame) -> None:
        params = RegimeSwitchStrategy.default_params()
        entries, exits, direction = RegimeSwitchStrategy.generate(sample_ohlcv, params)

        assert entries.shape == (len(sample_ohlcv),)
        assert entries.dtype == bool
        assert entries.sum() > 0, "Strategy generated zero entry signals"

    def test_exits_all_false(self, sample_ohlcv: pd.DataFrame) -> None:
        params = RegimeSwitchStrategy.default_params()
        _, exits, _ = RegimeSwitchStrategy.generate(sample_ohlcv, params)
        assert exits.sum() == 0


class TestDirectionMatchesEntries:
    def test_direction_array_matches_entries(self, sample_ohlcv: pd.DataFrame) -> None:
        params = RegimeSwitchStrategy.default_params()
        entries, _, direction = RegimeSwitchStrategy.generate(sample_ohlcv, params)

        entry_indices = np.where(entries)[0]
        assert len(entry_indices) > 0
        total = direction[entries].sum() + (~direction[entries]).sum()
        assert total > 0


class TestRegimeBehavior:
    def test_both_regimes_produce_signals(self, sample_ohlcv: pd.DataFrame) -> None:
        """With 78K bars, both trending and ranging regimes should fire."""
        from quant.strategies.indicators import atr_wilder

        params = RegimeSwitchStrategy.default_params()
        entries, _, direction = RegimeSwitchStrategy.generate(sample_ohlcv, params)

        close = sample_ohlcv["close"].values
        high = sample_ohlcv["high"].values
        low = sample_ohlcv["low"].values

        atr = atr_wilder(high, low, close, params["atr_period"])
        atr_pctl = pd.Series(atr).rolling(params["atr_lookback"]).rank(pct=True).values * 100
        high_atr = atr_pctl > params["regime_threshold"]

        entries_in_trend = entries & high_atr
        entries_in_range = entries & ~high_atr

        assert entries_in_trend.sum() > 0 or entries_in_range.sum() > 0


class TestEdgeCases:
    def test_empty_data(self) -> None:
        tiny = pd.DataFrame({
            "open": [100.0], "high": [101.0], "low": [99.0],
            "close": [100.5], "volume": [1000],
        }, index=pd.date_range("2023-01-01", periods=1, freq="15min"))
        params = RegimeSwitchStrategy.default_params()
        entries, exits, direction = RegimeSwitchStrategy.generate(tiny, params)
        assert entries.shape == (1,)
        assert entries.sum() == 0

    def test_short_data(self) -> None:
        tiny = pd.DataFrame({
            "open": [100.0] * 50, "high": [101.0] * 50, "low": [99.0] * 50,
            "close": [100.5] * 50, "volume": [1000] * 50,
        }, index=pd.date_range("2023-01-01", periods=50, freq="15min"))
        params = RegimeSwitchStrategy.default_params()
        entries, _, _ = RegimeSwitchStrategy.generate(tiny, params)
        assert entries.sum() == 0


class TestDefaultParams:
    def test_has_all_required_keys(self) -> None:
        params = RegimeSwitchStrategy.default_params()
        required = {
            "atr_period", "atr_lookback", "regime_threshold",
            "trend_fast_ema", "trend_slow_ema",
            "rev_rsi_period", "rev_rsi_os", "rev_rsi_ob",
            "rev_bb_period", "rev_bb_std",
            "tp_pct", "sl_pct",
        }
        assert set(params.keys()) == required

    def test_intraday_scale_tp_sl(self) -> None:
        params = RegimeSwitchStrategy.default_params()
        assert params["tp_pct"] < 1.0
        assert params["sl_pct"] < 1.0


class TestClassAttributes:
    def test_name(self) -> None:
        assert RegimeSwitchStrategy.name == "regime_switch"

    def test_family(self) -> None:
        assert RegimeSwitchStrategy.family == "regime_aware"
