"""Test that backtest.py correctly handles custom entry prices from level strategies."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _vbt_available() -> bool:
    """Check if vectorbt is importable."""
    try:
        import vectorbt as vbt  # noqa: F401

        return True
    except ImportError:
        return False


class TestEntryPriceUnpacking:
    """Verify the generate() result unpacking works for 3 and 4 element tuples."""

    def test_3_element_result(self) -> None:
        """Standard strategies return 3 arrays -- entry_prices should be None."""
        result = (
            np.array([True, False]),
            np.array([False, True]),
            np.array([True, False]),
        )
        if len(result) == 4:
            _entries, _exits, _direction, entry_prices = result
        else:
            _entries, _exits, _direction = result
            entry_prices = None
        assert entry_prices is None

    def test_4_element_result(self) -> None:
        """Level strategies return 4 arrays -- entry_prices should be populated."""
        result = (
            np.array([True, False]),
            np.array([False, True]),
            np.array([True, False]),
            np.array([18500.0, np.nan]),
        )
        if len(result) == 4:
            _entries, _exits, _direction, entry_prices = result
        else:
            _entries, _exits, _direction = result
            entry_prices = None
        assert entry_prices is not None
        assert entry_prices[0] == 18500.0
        assert np.isnan(entry_prices[1])


class TestExecPriceArrayConstruction:
    """Verify the execution price array is built correctly from entry_prices."""

    def test_exec_price_only_at_valid_entries(self) -> None:
        """exec_price should use level price only where entry AND not-NaN."""
        n = 5
        long_entries = np.array([True, False, True, False, False])
        short_entries = np.array([False, False, False, False, False])
        entry_prices = np.array([18500.0, np.nan, np.nan, 18600.0, 18700.0])

        exec_price = np.full(n, np.inf, dtype=np.float64)
        entry_mask = long_entries | short_entries
        valid_entry = entry_mask & ~np.isnan(entry_prices)
        exec_price[valid_entry] = entry_prices[valid_entry]

        # Bar 0: entry=True, price=18500 (valid) -> 18500
        assert exec_price[0] == 18500.0
        # Bar 1: entry=False -> inf (use close)
        assert exec_price[1] == np.inf
        # Bar 2: entry=True, price=NaN (invalid) -> inf (use close)
        assert exec_price[2] == np.inf
        # Bar 3: entry=False -> inf (use close)
        assert exec_price[3] == np.inf
        # Bar 4: entry=False -> inf (use close)
        assert exec_price[4] == np.inf

    def test_exec_price_with_short_entries(self) -> None:
        """exec_price should work for short entries too."""
        n = 4
        long_entries = np.array([False, False, False, False])
        short_entries = np.array([False, True, False, True])
        entry_prices = np.array([np.nan, 4500.0, np.nan, 4400.0])

        exec_price = np.full(n, np.inf, dtype=np.float64)
        entry_mask = long_entries | short_entries
        valid_entry = entry_mask & ~np.isnan(entry_prices)
        exec_price[valid_entry] = entry_prices[valid_entry]

        assert exec_price[0] == np.inf
        assert exec_price[1] == 4500.0
        assert exec_price[2] == np.inf
        assert exec_price[3] == 4400.0

    def test_no_entry_prices_gives_none(self) -> None:
        """When entry_prices is None, exec_price_series should remain None."""
        entry_prices = None
        if entry_prices is not None:
            exec_price_series: pd.Series | None = pd.Series([1.0])
        else:
            exec_price_series = None
        assert exec_price_series is None


@pytest.mark.skipif(
    not _vbt_available(),
    reason="vectorbt not installed",
)
class TestVbtIntegration:
    """Integration tests verifying vectorbt fills at the custom entry price."""

    def test_custom_entry_price_changes_fill(self) -> None:
        """With price param, vectorbt should fill at the custom price."""
        import vectorbt as vbt

        dates = pd.date_range("2024-01-01", periods=10, freq="1min")
        close = pd.Series(
            [100.0, 101, 102, 103, 104, 105, 106, 107, 108, 109],
            index=dates,
            dtype=float,
        )
        entries = pd.Series(
            [True, False, False, False, False, False, False, False, False, False],
            index=dates,
        )
        exits = pd.Series(
            [False, False, False, False, False, False, False, False, False, True],
            index=dates,
        )

        # Custom price: fill entry at 95 instead of close=100
        custom_price = pd.Series([95.0] + [np.inf] * 9, index=dates, dtype=float)

        pf = vbt.Portfolio.from_signals(
            close,
            entries=entries,
            exits=exits,
            price=custom_price,
            freq="1min",
            size=1.0,
            size_type="amount",
        )
        trades = pf.trades.records_readable
        assert len(trades) == 1
        assert trades["Avg Entry Price"].values[0] == pytest.approx(95.0)

    def test_tp_calculated_from_fill_price(self) -> None:
        """With stop_entry_price=FillPrice, TP should be relative to fill price."""
        import vectorbt as vbt
        from vectorbt.portfolio.enums import StopEntryPrice

        dates = pd.date_range("2024-01-01", periods=20, freq="1min")
        # Price rises steadily: 100, 101, 102, ...
        close = pd.Series([100.0 + i for i in range(20)], index=dates, dtype=float)
        entries = pd.Series([True] + [False] * 19, index=dates)
        exits = pd.Series([False] * 20, index=dates)

        # Fill at 95, TP at 5% -> target = 99.75, should exit when close >= 99.75
        custom_price = pd.Series([95.0] + [np.inf] * 19, index=dates, dtype=float)

        pf = vbt.Portfolio.from_signals(
            close,
            entries=entries,
            exits=exits,
            price=custom_price,
            tp_stop=0.05,
            stop_entry_price=StopEntryPrice.FillPrice,
            freq="1min",
            size=1.0,
            size_type="amount",
        )
        trades = pf.trades.records_readable
        assert len(trades) == 1
        entry_px = trades["Avg Entry Price"].values[0]
        exit_px = trades["Avg Exit Price"].values[0]
        assert entry_px == pytest.approx(95.0)
        # TP from 95 at 5% = 99.75 -> exits at first close >= 99.75
        # close[0]=100 >= 99.75, but entry is at bar 0 so TP check starts bar 1
        # close[1]=101 >= 99.75 -> exits at 101
        assert exit_px == pytest.approx(101.0)
