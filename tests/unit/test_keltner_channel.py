"""Unit tests for the Keltner Channel strategy.

Verifies signal generation on synthetic data.
All tests use the sample_ohlcv fixture — no real CSVs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.keltner_channel import KeltnerChannelStrategy


class TestGeneratesSignals:
    """Keltner Channel must produce non-zero entries on realistic synthetic data."""

    def test_generates_signals(self, sample_ohlcv: pd.DataFrame) -> None:
        params = KeltnerChannelStrategy.default_params()
        entries, exits, direction = KeltnerChannelStrategy.generate(sample_ohlcv, params)

        assert entries.shape == (len(sample_ohlcv),)
        assert exits.shape == (len(sample_ohlcv),)
        assert direction.shape == (len(sample_ohlcv),)
        assert entries.dtype == bool
        assert exits.dtype == bool
        assert direction.dtype == bool

        # Must produce at least some signals on 78K bars of synthetic data
        n_entries = int(np.sum(entries))
        assert n_entries > 0, "Expected non-zero entry signals on sample data"


class TestDirectionMatchesEntries:
    """Direction array must be True for long entries, False for short entries."""

    def test_direction_array_matches_entries(self, sample_ohlcv: pd.DataFrame) -> None:
        params = KeltnerChannelStrategy.default_params()
        entries, _exits, direction = KeltnerChannelStrategy.generate(sample_ohlcv, params)

        # Where entries fire, direction must split into longs and shorts
        entry_indices = np.where(entries)[0]
        assert len(entry_indices) > 0, "Need entries to verify direction"

        long_entries = entries & direction
        short_entries = entries & ~direction

        # Every entry must be either long or short (not both)
        assert np.all(long_entries | short_entries == entries)
        assert not np.any(long_entries & short_entries)

        # Both longs and shorts should appear in a trending random walk
        n_long = int(np.sum(long_entries))
        n_short = int(np.sum(short_entries))
        assert n_long > 0, "Expected at least some long entries"
        assert n_short > 0, "Expected at least some short entries"


class TestEmptyData:
    """Tiny or empty input must return zero-filled arrays without crashing."""

    def test_empty_dataframe(self) -> None:
        """Zero-row DataFrame returns zero arrays."""
        data = pd.DataFrame(
            {"open": [], "high": [], "low": [], "close": [], "volume": []},
            dtype=float,
        )
        params = KeltnerChannelStrategy.default_params()
        entries, exits, direction = KeltnerChannelStrategy.generate(data, params)

        assert len(entries) == 0
        assert len(exits) == 0
        assert len(direction) == 0

    def test_single_bar(self) -> None:
        """Single bar is below MIN_BARS_FOR_SIGNALS — returns zeros."""
        data = pd.DataFrame(
            {
                "open": [100.0],
                "high": [101.0],
                "low": [99.0],
                "close": [100.5],
                "volume": [1000],
            }
        )
        params = KeltnerChannelStrategy.default_params()
        entries, exits, direction = KeltnerChannelStrategy.generate(data, params)

        assert len(entries) == 1
        assert not np.any(entries)
        assert not np.any(exits)

    def test_two_bars(self) -> None:
        """Two bars is below MIN_BARS_FOR_SIGNALS — returns zeros."""
        data = pd.DataFrame(
            {
                "open": [100.0, 101.0],
                "high": [101.0, 102.0],
                "low": [99.0, 100.0],
                "close": [100.5, 101.5],
                "volume": [1000, 1100],
            }
        )
        params = KeltnerChannelStrategy.default_params()
        entries, exits, direction = KeltnerChannelStrategy.generate(data, params)

        assert len(entries) == 2
        assert not np.any(entries)
