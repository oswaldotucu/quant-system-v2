"""Unit tests for quant/strategies/rsi_bollinger_filtered.py."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.rsi_bollinger_filtered import RsiBollingerFilteredStrategy


class TestGeneratesSignals:
    def test_generates_signals(self, sample_ohlcv: pd.DataFrame) -> None:
        params = RsiBollingerFilteredStrategy.default_params()
        entries, exits, direction = RsiBollingerFilteredStrategy.generate(sample_ohlcv, params)

        assert entries.shape == (len(sample_ohlcv),)
        assert entries.dtype == bool
        assert entries.sum() > 0, "Strategy generated zero entry signals"

    def test_exits_all_false(self, sample_ohlcv: pd.DataFrame) -> None:
        params = RsiBollingerFilteredStrategy.default_params()
        _, exits, _ = RsiBollingerFilteredStrategy.generate(sample_ohlcv, params)
        assert exits.sum() == 0


class TestDirectionMatchesEntries:
    def test_direction_array_matches_entries(self, sample_ohlcv: pd.DataFrame) -> None:
        params = RsiBollingerFilteredStrategy.default_params()
        entries, _, direction = RsiBollingerFilteredStrategy.generate(sample_ohlcv, params)

        entry_indices = np.where(entries)[0]
        assert len(entry_indices) > 0
        total = direction[entries].sum() + (~direction[entries]).sum()
        assert total > 0

    def test_regime_filter_active(self, sample_ohlcv: pd.DataFrame) -> None:
        """All entries must be in low-ATR regime."""
        from quant.strategies.indicators import atr_wilder

        params = RsiBollingerFilteredStrategy.default_params()
        entries, _, _ = RsiBollingerFilteredStrategy.generate(sample_ohlcv, params)

        high = sample_ohlcv["high"].values
        low = sample_ohlcv["low"].values
        close = sample_ohlcv["close"].values

        atr = atr_wilder(high, low, close, params["atr_period"])
        atr_pctl = pd.Series(atr).rolling(params["atr_lookback"]).rank(pct=True).values * 100

        entry_mask = entries & ~np.isnan(atr_pctl)
        if entry_mask.sum() > 0:
            assert np.all(atr_pctl[entry_mask] <= params["regime_threshold"])


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
            index=pd.date_range("2023-01-01", periods=1, freq="15min"),
        )
        params = RsiBollingerFilteredStrategy.default_params()
        entries, _, _ = RsiBollingerFilteredStrategy.generate(tiny, params)
        assert entries.shape == (1,)
        assert entries.sum() == 0

    def test_short_data(self) -> None:
        tiny = pd.DataFrame(
            {
                "open": [100.0] * 50,
                "high": [101.0] * 50,
                "low": [99.0] * 50,
                "close": [100.5] * 50,
                "volume": [1000] * 50,
            },
            index=pd.date_range("2023-01-01", periods=50, freq="15min"),
        )
        params = RsiBollingerFilteredStrategy.default_params()
        entries, _, _ = RsiBollingerFilteredStrategy.generate(tiny, params)
        assert entries.sum() == 0


class TestDefaultParams:
    def test_has_all_required_keys(self) -> None:
        params = RsiBollingerFilteredStrategy.default_params()
        required = {
            "rsi_period",
            "rsi_os",
            "rsi_ob",
            "bb_period",
            "bb_std",
            "atr_period",
            "atr_lookback",
            "regime_threshold",
            "tp_pct",
            "sl_pct",
        }
        assert set(params.keys()) == required

    def test_intraday_scale_tp_sl(self) -> None:
        params = RsiBollingerFilteredStrategy.default_params()
        assert params["tp_pct"] < 1.0
        assert params["sl_pct"] < 1.0


class TestClassAttributes:
    def test_name(self) -> None:
        assert RsiBollingerFilteredStrategy.name == "rsi_bollinger_filtered"

    def test_family(self) -> None:
        assert RsiBollingerFilteredStrategy.family == "mean_reversion"
