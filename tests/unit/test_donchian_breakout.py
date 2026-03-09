"""Unit tests for Donchian Channel Breakout strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.donchian_breakout import DonchianBreakoutStrategy


class TestGeneratesSignals:
    """Strategy should produce non-zero entry signals on realistic synthetic data."""

    def test_generates_signals(self, sample_ohlcv: pd.DataFrame) -> None:
        params = DonchianBreakoutStrategy.default_params()
        entries, exits, direction = DonchianBreakoutStrategy.generate(sample_ohlcv, params)

        assert entries.shape == (len(sample_ohlcv),)
        assert exits.shape == (len(sample_ohlcv),)
        assert direction.shape == (len(sample_ohlcv),)
        assert entries.dtype == bool
        assert exits.dtype == bool
        assert direction.dtype == bool

        # Must produce at least some signals on 78K bars of synthetic data
        assert entries.sum() > 0, "Strategy generated zero entry signals"


class TestDirectionMatchesEntries:
    """Direction array should be True for long entries and False for short entries."""

    def test_direction_array_matches_entries(self, sample_ohlcv: pd.DataFrame) -> None:
        params = DonchianBreakoutStrategy.default_params()
        entries, _, direction = DonchianBreakoutStrategy.generate(sample_ohlcv, params)

        # Where entries fire, direction must be True (long) or False (short)
        entry_indices = np.where(entries)[0]
        assert len(entry_indices) > 0, "Need entries to test direction"

        long_count = direction[entry_indices].sum()
        short_count = len(entry_indices) - long_count

        # With default params on random walk, expect both longs and shorts
        # (trend filter with 50 EMA still allows both directions)
        assert long_count > 0, "Expected some long entries"
        assert short_count > 0, "Expected some short entries"

    def test_long_entries_above_channel(self, sample_ohlcv: pd.DataFrame) -> None:
        """Long entries should occur where close > upper channel."""
        params = DonchianBreakoutStrategy.default_params()
        params["use_trend_filter"] = 0  # disable filter to isolate channel logic
        entries, _, direction = DonchianBreakoutStrategy.generate(sample_ohlcv, params)

        close = sample_ohlcv["close"].values
        high = sample_ohlcv["high"].values
        entry_period = params["entry_period"]

        long_indices = np.where(entries & direction)[0]
        for idx in long_indices[:50]:  # check first 50 long entries
            upper = np.max(high[idx - entry_period : idx])
            assert close[idx] > upper, (
                f"Long entry at {idx}: close={close[idx]:.2f} not > upper={upper:.2f}"
            )


class TestEmptyData:
    """Returns zero arrays when data is too short to compute channels."""

    def test_empty_data(self) -> None:
        """With fewer bars than entry_period, no signals should fire."""
        params = DonchianBreakoutStrategy.default_params()
        entry_period = params["entry_period"]

        # Create tiny dataframe shorter than entry_period
        n = entry_period - 1
        rng = np.random.default_rng(seed=99)
        idx = pd.date_range("2020-01-01", periods=n, freq="15min", tz="America/New_York")
        data = pd.DataFrame(
            {
                "open": rng.normal(15000, 10, n),
                "high": rng.normal(15010, 10, n),
                "low": rng.normal(14990, 10, n),
                "close": rng.normal(15000, 10, n),
                "volume": rng.integers(100, 5000, n),
            },
            index=idx,
        )

        entries, exits, direction = DonchianBreakoutStrategy.generate(data, params)

        assert entries.sum() == 0
        assert exits.sum() == 0
        assert direction.sum() == 0
        assert len(entries) == n

    def test_single_bar(self) -> None:
        """Single bar of data should return zero arrays without error."""
        idx = pd.date_range("2020-01-01", periods=1, freq="15min", tz="America/New_York")
        data = pd.DataFrame(
            {
                "open": [15000.0],
                "high": [15010.0],
                "low": [14990.0],
                "close": [15000.0],
                "volume": [1000],
            },
            index=idx,
        )
        params = DonchianBreakoutStrategy.default_params()

        entries, exits, direction = DonchianBreakoutStrategy.generate(data, params)

        assert entries.sum() == 0
        assert len(entries) == 1


class TestTrendFilterReducesSignals:
    """With trend filter ON, signals should be <= signals without filter."""

    def test_trend_filter_reduces_signals(self, sample_ohlcv: pd.DataFrame) -> None:
        params_no_filter = DonchianBreakoutStrategy.default_params()
        params_no_filter["use_trend_filter"] = 0

        params_with_filter = DonchianBreakoutStrategy.default_params()
        params_with_filter["use_trend_filter"] = 1

        entries_no_filter, _, _ = DonchianBreakoutStrategy.generate(sample_ohlcv, params_no_filter)
        entries_with_filter, _, _ = DonchianBreakoutStrategy.generate(
            sample_ohlcv, params_with_filter
        )

        count_no_filter = entries_no_filter.sum()
        count_with_filter = entries_with_filter.sum()

        assert count_no_filter > 0, "Unfiltered should produce signals"
        assert count_with_filter <= count_no_filter, (
            f"Trend filter should reduce or maintain signal count: "
            f"filtered={count_with_filter}, unfiltered={count_no_filter}"
        )


class TestDefaultParams:
    """Default params should be well-formed."""

    def test_default_params_keys(self) -> None:
        params = DonchianBreakoutStrategy.default_params()
        expected_keys = {"entry_period", "trend_ema", "use_trend_filter", "tp_pct", "sl_pct"}
        assert set(params.keys()) == expected_keys

    def test_class_attributes(self) -> None:
        assert DonchianBreakoutStrategy.name == "donchian_breakout"
        assert DonchianBreakoutStrategy.family == "trend_following"
