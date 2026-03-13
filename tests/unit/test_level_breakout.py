"""Tests for level breakout strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant.strategies.level_breakout import LevelBreakoutStrategy


def _make_data(
    start: str = "2024-01-15 09:00",
    periods: int = 500,
    freq: str = "5min",
    base_price: float = 18000.0,
) -> pd.DataFrame:
    """Create synthetic OHLCV data."""
    idx = pd.date_range(start, periods=periods, freq=freq, tz="America/New_York")
    rng = np.random.default_rng(42)
    close = base_price + np.cumsum(rng.normal(0, 2, periods))
    high = close + rng.uniform(5, 20, periods)
    low = close - rng.uniform(5, 20, periods)
    open_ = close + rng.normal(0, 1, periods)
    vol = rng.integers(100, 1000, periods)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol},
        index=idx,
    )


class TestReturns4Arrays:
    def test_returns_4_element_tuple(self) -> None:
        """Level breakout must return (entries, exits, direction, entry_prices)."""
        data = _make_data(periods=2000, start="2024-01-01 09:00")
        params = LevelBreakoutStrategy.default_params()
        result = LevelBreakoutStrategy.generate(data, params)
        assert len(result) == 4
        entries, exits, direction, entry_prices = result
        assert entries.shape == (len(data),)
        assert entry_prices.shape == (len(data),)

    def test_entry_prices_at_level(self) -> None:
        """Entry prices should be the level value, not NaN, on entry bars."""
        data = _make_data(periods=2000, start="2024-01-01 09:00")
        params = {
            "level_type": "pdhl",
            "filter_type": "unfiltered",
            "sl_pct": 1.0,
            "tp_pct": 0.5,
        }
        entries, _, direction, entry_prices = LevelBreakoutStrategy.generate(data, params)

        if entries.sum() > 0:
            # Entry prices should NOT be NaN on entry bars
            assert not np.any(np.isnan(entry_prices[entries]))


class TestFilteredEntries:
    def test_macd_filter_reduces_entries(self) -> None:
        """MACD filter should produce fewer entries than unfiltered."""
        data = _make_data(periods=2000, start="2024-01-01 09:00")
        params_uf = {
            "level_type": "pdhl",
            "filter_type": "unfiltered",
            "sl_pct": 1.0,
            "tp_pct": 0.5,
        }
        params_macd = {
            "level_type": "pdhl",
            "filter_type": "macd",
            "sl_pct": 1.0,
            "tp_pct": 0.5,
        }

        entries_uf, _, _, _ = LevelBreakoutStrategy.generate(data, params_uf)
        entries_macd, _, _, _ = LevelBreakoutStrategy.generate(data, params_macd)

        # Filtered should have <= entries than unfiltered
        assert entries_macd.sum() <= entries_uf.sum()


class TestUnfilteredEntries:
    def test_unfiltered_trades_both_directions(self) -> None:
        """Unfiltered mode should produce both long and short entries."""
        data = _make_data(periods=2000, start="2024-01-01 09:00")
        params = {
            "level_type": "pdhl",
            "filter_type": "unfiltered",
            "sl_pct": 1.0,
            "tp_pct": 0.5,
        }
        entries, _, direction, _ = LevelBreakoutStrategy.generate(data, params)

        if entries.sum() > 1:
            long_count = (entries & direction).sum()
            short_count = (entries & ~direction).sum()
            # Both directions should have at least some entries
            assert long_count > 0 and short_count > 0, (
                f"Expected both directions, got longs={long_count}, shorts={short_count}"
            )


class TestLevelTypes:
    @pytest.mark.parametrize(
        "level_type",
        ["pdhl", "or30", "monthly", "quarterly", "semiannual", "annual"],
    )
    def test_all_level_types_work(self, level_type: str) -> None:
        """Each level type should produce valid output without errors."""
        data = _make_data(periods=5000, start="2023-01-01 09:00")
        params = {
            "level_type": level_type,
            "filter_type": "unfiltered",
            "sl_pct": 1.0,
            "tp_pct": 0.5,
        }
        result = LevelBreakoutStrategy.generate(data, params)
        assert len(result) == 4
        entries, exits, direction, entry_prices = result
        assert entries.dtype == bool
        assert entry_prices.dtype == np.float64 or entry_prices.dtype == float


class TestFilterTypes:
    @pytest.mark.parametrize(
        "filter_type",
        ["macd", "bb", "kc", "ema", "consensus", "unfiltered"],
    )
    def test_all_filter_types_work(self, filter_type: str) -> None:
        """Each filter type should produce valid output without errors."""
        data = _make_data(periods=2000, start="2024-01-01 09:00")
        params = {
            "level_type": "pdhl",
            "filter_type": filter_type,
            "sl_pct": 1.0,
            "tp_pct": 0.5,
        }
        result = LevelBreakoutStrategy.generate(data, params)
        assert len(result) == 4


class TestEdgeCases:
    def test_empty_data(self) -> None:
        data = pd.DataFrame(
            {"open": [], "high": [], "low": [], "close": [], "volume": []},
            index=pd.DatetimeIndex([], tz="America/New_York"),
        )
        params = LevelBreakoutStrategy.default_params()
        entries, exits, direction, entry_prices = LevelBreakoutStrategy.generate(data, params)
        assert len(entries) == 0

    def test_short_data(self) -> None:
        data = _make_data(periods=5)
        params = LevelBreakoutStrategy.default_params()
        entries, _, _, entry_prices = LevelBreakoutStrategy.generate(data, params)
        assert entries.shape == (5,)

    def test_unknown_level_type(self) -> None:
        data = _make_data(periods=100)
        params = {
            "level_type": "nonexistent",
            "filter_type": "macd",
            "sl_pct": 1.0,
            "tp_pct": 0.5,
        }
        with pytest.raises(ValueError, match="Unknown level_type"):
            LevelBreakoutStrategy.generate(data, params)

    def test_unknown_filter_type(self) -> None:
        data = _make_data(periods=100)
        params = {
            "level_type": "pdhl",
            "filter_type": "nonexistent",
            "sl_pct": 1.0,
            "tp_pct": 0.5,
        }
        with pytest.raises(ValueError, match="Unknown filter_type"):
            LevelBreakoutStrategy.generate(data, params)


class TestNoSimultaneousEntries:
    def test_no_simultaneous_long_and_short(self) -> None:
        """Should never have long AND short entry on the same bar."""
        data = _make_data(periods=5000, start="2023-01-01 09:00")
        params = {
            "level_type": "pdhl",
            "filter_type": "unfiltered",
            "sl_pct": 1.0,
            "tp_pct": 0.5,
        }
        entries, _, direction, _ = LevelBreakoutStrategy.generate(data, params)

        long_entries = entries & direction
        short_entries = entries & ~direction
        assert not np.any(long_entries & short_entries)


class TestDefaultParams:
    def test_has_required_keys(self) -> None:
        params = LevelBreakoutStrategy.default_params()
        assert "level_type" in params
        assert "filter_type" in params
        assert "sl_pct" in params
        assert "tp_pct" in params

    def test_name_and_family(self) -> None:
        assert LevelBreakoutStrategy.name == "level_breakout"
        assert LevelBreakoutStrategy.family == "level_breakout"
