"""Volatility Breakout strategy — CANDIDATE (V1 shows weak OOS PF ~1.22).

DO NOT USE — currently failing the OOS_MIN_PF >= 1.5 threshold.
Kept as reference. NOT in STRATEGY_REGISTRY.

Logic:
- Detect Bollinger Band squeeze (BB width < squeeze_threshold * rolling avg width)
- After min_squeeze_bars of squeeze, enter on first bar that closes outside BB
- ATR-sized SL; asymmetric TP (atr_tp > atr_sl for R:R > 1)
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


class VolatilityBreakoutStrategy:
    name = "volatility_breakout"
    family = "breakout"

    @staticmethod
    def default_params() -> dict[str, Any]:
        return {
            "bb_period": 20,
            "bb_std": 2.0,
            "squeeze_threshold": 0.7,
            "min_squeeze_bars": 5,
            "tp_pct": 0.15,  # ~37 pts MNQ (intraday scale)
            "sl_pct": 0.3,  # 2:1 risk vs TP
        }

    @staticmethod
    def generate(
        data: pd.DataFrame,
        params: dict[str, Any],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Generate breakout signals from Bollinger Band squeezes."""
        close = data["close"].values
        _high = data["high"].values
        _low = data["low"].values
        n = len(close)

        bb_period = params["bb_period"]
        bb_std = params["bb_std"]
        squeeze_threshold = params["squeeze_threshold"]
        min_squeeze_bars = params["min_squeeze_bars"]

        # Bollinger Bands
        rolling_mean = pd.Series(close).rolling(bb_period).mean().values
        rolling_std = pd.Series(close).rolling(bb_period).std(ddof=1).values
        bb_upper = rolling_mean + bb_std * rolling_std
        bb_lower = rolling_mean - bb_std * rolling_std
        bb_width = bb_upper - bb_lower
        avg_bb_width = pd.Series(bb_width).rolling(bb_period * 2).mean().values

        # Squeeze: current width < threshold * avg width
        in_squeeze = bb_width < squeeze_threshold * avg_bb_width

        # Count consecutive squeeze bars
        squeeze_count = np.zeros(n, dtype=int)
        for i in range(1, n):
            if in_squeeze[i]:
                squeeze_count[i] = squeeze_count[i - 1] + 1
            else:
                squeeze_count[i] = 0

        # Breakout after sufficient squeeze
        was_in_squeeze = squeeze_count >= min_squeeze_bars
        long_entries = was_in_squeeze & (close > bb_upper)
        short_entries = was_in_squeeze & (close < bb_lower)

        entries = long_entries | short_entries
        direction = long_entries
        exits = np.zeros(n, dtype=bool)

        return entries, exits, direction
