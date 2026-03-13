"""Level Breakout Strategy — the core Sentinel paradigm.

Combines price levels (PDH/PDL, OR30, Monthly/Quarterly/Semi/Annual H/L)
with directional filters (MACD, BB, KC, EMA, Consensus, Unfiltered) to
generate breakout entries with stop-order fill simulation.

This single class replaces Sentinel's 87 level-based strategy variants.

Entry logic (stop-order simulation):
- Long:  bar high >= level_high AND filter == +1 (or unfiltered) -> fill at level_high
- Short: bar low  <= level_low  AND filter == -1 (or unfiltered) -> fill at level_low
- For unfiltered: trade BOTH directions without filter confirmation
  (long-horizon levels like Annual have inherent directionality)

Exit: TP/SL (percentage from fill price) + forced time exit via session module.

Returns 4 arrays: (entries, exits, direction, entry_prices)
The 4th array enables backtest.py to use level prices as fill prices.

NO LOOK-AHEAD BIAS:
- Levels use previous period data only (shift(1) in levels.py)
- Entries check high/low (intra-bar touch), not close (which is known at bar close)
- Actually, high/low ARE known at bar close in historical data, so checking
  high >= level is NOT look-ahead — it simulates a stop order that was placed
  before the bar opened.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from quant.strategies.filters import (
    bb_filter,
    consensus_filter,
    ema_trend_filter,
    kc_filter,
    macd_filter,
)
from quant.strategies.levels import (
    compute_annual_hl,
    compute_monthly_hl,
    compute_or30,
    compute_pdhl,
    compute_quarterly_hl,
    compute_semiannual_hl,
)

log = logging.getLogger(__name__)

# Maps level_type string to computation function
LEVEL_FUNCTIONS: dict[str, Any] = {
    "pdhl": compute_pdhl,
    "or30": compute_or30,
    "monthly": compute_monthly_hl,
    "quarterly": compute_quarterly_hl,
    "semiannual": compute_semiannual_hl,
    "annual": compute_annual_hl,
}

# Maps filter_type string to filter function
# "unfiltered" is handled specially (no filter applied)
FILTER_FUNCTIONS: dict[str, Any] = {
    "macd": macd_filter,
    "bb": bb_filter,
    "kc": kc_filter,
    "ema": ema_trend_filter,
    "consensus": consensus_filter,
}


def _empty_signals(n: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return 4 empty signal arrays (entries, exits, direction, entry_prices)."""
    zeros = np.zeros(n, dtype=bool)
    return zeros.copy(), zeros.copy(), zeros.copy(), np.full(n, np.nan)


class LevelBreakoutStrategy:
    """Generic level breakout: level_type x filter_type x SL x exit_time.

    Entry: high >= level_high AND filter_direction == +1 -> long (fill at level_high)
           low  <= level_low  AND filter_direction == -1 -> short (fill at level_low)

    For filter_type == "unfiltered":
           high >= level_high -> long (fill at level_high)
           low  <= level_low  -> short (fill at level_low)

    Exit: TP/SL + forced time exit (handled by backtest engine).
    """

    name = "level_breakout"
    family = "level_breakout"

    @staticmethod
    def default_params() -> dict[str, Any]:
        return {
            "level_type": "quarterly",
            "filter_type": "macd",
            "sl_pct": 0.5,
            "tp_pct": 0.3,
        }

    @staticmethod
    def generate(
        data: pd.DataFrame,
        params: dict[str, Any],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Generate level breakout signals with stop-order fill prices.

        Returns 4 arrays: (entries, exits, direction, entry_prices)
        """
        close = data["close"].values
        high = data["high"].values
        low = data["low"].values
        n = len(close)

        level_type: str = params.get("level_type", "quarterly")
        filter_type: str = params.get("filter_type", "macd")

        # --- Compute levels ---
        level_func = LEVEL_FUNCTIONS.get(level_type)
        if level_func is None:
            valid = list(LEVEL_FUNCTIONS.keys())
            raise ValueError(f"Unknown level_type: {level_type}. Valid: {valid}")

        level_high, level_low = level_func(data)

        # --- Compute filter direction ---
        if filter_type == "unfiltered":
            filter_dir = None
        else:
            filter_func = FILTER_FUNCTIONS.get(filter_type)
            if filter_func is None:
                valid = list(FILTER_FUNCTIONS.keys())
                raise ValueError(f"Unknown filter_type: {filter_type}. Valid: {valid}")

            # Call filter with appropriate args
            if filter_type in ("kc", "consensus"):
                filter_dir = filter_func(high, low, close)
            else:
                filter_dir = filter_func(close)

        # --- Detect intra-bar level touches (stop-order simulation) ---
        # Level must be valid (not NaN)
        valid_high = ~np.isnan(level_high)
        valid_low = ~np.isnan(level_low)

        # Long entry: bar's high touches or exceeds the level high
        long_touch = valid_high & (high >= level_high)
        # Short entry: bar's low touches or goes below the level low
        short_touch = valid_low & (low <= level_low)

        # Apply filter
        if filter_dir is not None:
            # Filtered: only enter when filter agrees with direction
            long_entries = long_touch & (filter_dir == 1)
            short_entries = short_touch & (filter_dir == -1)
        else:
            # Unfiltered: trade both directions
            long_entries = long_touch
            short_entries = short_touch

        # Prevent simultaneous long and short on the same bar
        # If both trigger, prefer long (arbitrary but deterministic)
        both = long_entries & short_entries
        if both.any():
            short_entries = short_entries & ~both

        entries = long_entries | short_entries
        direction = long_entries  # True = long, False = short

        # --- Build entry_prices array ---
        # Long fills at level_high, short fills at level_low
        entry_prices = np.full(n, np.nan)
        entry_prices[long_entries] = level_high[long_entries]
        entry_prices[short_entries] = level_low[short_entries]

        exits = np.zeros(n, dtype=bool)

        return entries, exits, direction, entry_prices
