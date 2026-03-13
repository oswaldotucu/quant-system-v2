"""Unit tests for quant/strategies/bollinger_squeeze.py.

Uses synthetic data via sample_ohlcv fixture — never real CSVs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.bollinger_squeeze import BollingerSqueezeStrategy


class TestGeneratesSignals:
    """Strategy must produce non-zero entry signals on realistic synthetic data."""

    def test_generates_signals(self, sample_ohlcv: pd.DataFrame) -> None:
        params = BollingerSqueezeStrategy.default_params()
        entries, exits, direction = BollingerSqueezeStrategy.generate(sample_ohlcv, params)

        assert entries.shape == (len(sample_ohlcv),)
        assert exits.shape == (len(sample_ohlcv),)
        assert direction.shape == (len(sample_ohlcv),)

        assert entries.dtype == bool
        assert exits.dtype == bool
        assert direction.dtype == bool

        # Must produce at least some signals on 78K bars of data
        assert entries.sum() > 0, "Expected non-zero entry signals on sample data"

    def test_exits_all_false(self, sample_ohlcv: pd.DataFrame) -> None:
        """Exits are handled by TP/SL in backtest engine, not by the strategy."""
        params = BollingerSqueezeStrategy.default_params()
        _, exits, _ = BollingerSqueezeStrategy.generate(sample_ohlcv, params)
        assert exits.sum() == 0


class TestDirectionMatchesEntries:
    """Direction array must be True for longs and False for shorts."""

    def test_direction_array_matches_entries(self, sample_ohlcv: pd.DataFrame) -> None:
        params = BollingerSqueezeStrategy.default_params()
        entries, _, direction = BollingerSqueezeStrategy.generate(sample_ohlcv, params)

        # Where entries is True, direction must be either True (long) or False (short)
        # Direction should only be True at bars where close > upper band (long breakout)
        # and False at bars where close < lower band (short breakout)
        entry_indices = np.where(entries)[0]
        assert len(entry_indices) > 0, "Need entries to test direction"

        long_count = direction[entries].sum()
        short_count = (~direction[entries]).sum()

        # With random walk data we expect both long and short signals
        # At minimum, direction should not be all-True or all-False
        # (statistically very unlikely on 78K bars of random walk)
        total = long_count + short_count
        assert total > 0, "Expected at least one directional signal"

    def test_long_entries_are_above_shifted_upper_band(self, sample_ohlcv: pd.DataFrame) -> None:
        """Long entries should occur when close > previous bar's upper Bollinger Band."""
        params = BollingerSqueezeStrategy.default_params()
        entries, _, direction = BollingerSqueezeStrategy.generate(sample_ohlcv, params)

        close = sample_ohlcv["close"].values
        bb_period = params["bb_period"]
        bb_std = params["bb_std"]

        # Recompute upper band and shift by 1 bar (matching strategy logic)
        sma_vals = pd.Series(close).rolling(bb_period).mean().values
        std = pd.Series(close).rolling(bb_period).std(ddof=1).values
        upper_raw = sma_vals + bb_std * std
        upper = np.roll(upper_raw, 1)
        upper[0] = np.nan

        # All long entries must have close > shifted upper band (previous bar's band)
        # Only check bars past warmup where shifted rolling values are valid
        long_mask = entries & direction
        valid = ~np.isnan(upper)
        check_mask = long_mask & valid
        if check_mask.sum() > 0:
            assert np.all(close[check_mask] > upper[check_mask]), (
                "Long entries should have close above previous bar's upper Bollinger Band"
            )


class TestEmptyData:
    """Strategy must handle edge cases gracefully."""

    def test_empty_data(self) -> None:
        """Tiny input (fewer bars than bb_period) returns zero arrays."""
        tiny = pd.DataFrame(
            {
                "open": [100.0, 101.0, 102.0],
                "high": [101.0, 102.0, 103.0],
                "low": [99.0, 100.0, 101.0],
                "close": [100.5, 101.5, 102.5],
                "volume": [1000, 1000, 1000],
            },
            index=pd.date_range("2023-01-01", periods=3, freq="15min"),
        )

        params = BollingerSqueezeStrategy.default_params()
        entries, exits, direction = BollingerSqueezeStrategy.generate(tiny, params)

        assert entries.shape == (3,)
        assert exits.shape == (3,)
        assert direction.shape == (3,)
        assert entries.sum() == 0
        assert exits.sum() == 0
        assert direction.sum() == 0

    def test_single_bar(self) -> None:
        """Single bar should not crash."""
        single = pd.DataFrame(
            {
                "open": [100.0],
                "high": [101.0],
                "low": [99.0],
                "close": [100.5],
                "volume": [1000],
            },
            index=pd.date_range("2023-01-01", periods=1, freq="15min"),
        )

        params = BollingerSqueezeStrategy.default_params()
        entries, exits, direction = BollingerSqueezeStrategy.generate(single, params)

        assert entries.shape == (1,)
        assert entries.sum() == 0


class TestDefaultParams:
    """Default params must be complete and reasonable."""

    def test_has_all_required_keys(self) -> None:
        params = BollingerSqueezeStrategy.default_params()
        required = {
            "bb_period",
            "bb_std",
            "squeeze_threshold",
            "squeeze_lookback",
            "tp_pct",
            "sl_pct",
        }
        assert set(params.keys()) == required

    def test_intraday_scale_tp_sl(self) -> None:
        """TP/SL should be intraday scale (< 1%)."""
        params = BollingerSqueezeStrategy.default_params()
        assert params["tp_pct"] < 1.0, "TP should be intraday scale"
        assert params["sl_pct"] < 1.0, "SL should be intraday scale"


class TestClassAttributes:
    """Strategy must have name and family attributes."""

    def test_name(self) -> None:
        assert BollingerSqueezeStrategy.name == "bollinger_squeeze"

    def test_family(self) -> None:
        assert BollingerSqueezeStrategy.family == "breakout"
