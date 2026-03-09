"""SuperTrend Strategy.

ATR-based trailing stop that determines trend direction.
Enter on SuperTrend flip (bullish/bearish reversal).
Very popular among micro-futures retail traders.

Entry:
  Long:  SuperTrend flips from bearish to bullish (price closes above upper band)
  Short: SuperTrend flips from bullish to bearish (price closes below lower band)

Exit: pct-based TP/SL via backtest engine.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from quant.strategies.indicators import atr_wilder


def _supertrend(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    period: int,
    multiplier: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute SuperTrend indicator.

    Returns:
        (supertrend_line, is_bullish) both shape (n,).
        is_bullish[i] = True means price is above SuperTrend (bullish regime).
        Valid from index `period` onward.
    """
    n = len(close)

    atr = atr_wilder(high, low, close, period)

    hl2 = (high + low) / 2.0
    raw_upper = hl2 + multiplier * atr
    raw_lower = hl2 - multiplier * atr

    final_upper = np.zeros(n)
    final_lower = np.zeros(n)
    is_bullish = np.zeros(n, dtype=bool)
    supertrend = np.zeros(n)

    # Seed
    final_upper[period] = raw_upper[period]
    final_lower[period] = raw_lower[period]
    is_bullish[period] = True  # default bullish
    supertrend[period] = final_lower[period]

    for i in range(period + 1, n):
        # Upper band: only tighten (move down) when price was below it
        if close[i - 1] <= final_upper[i - 1]:
            final_upper[i] = min(raw_upper[i], final_upper[i - 1])
        else:
            final_upper[i] = raw_upper[i]

        # Lower band: only tighten (move up) when price was above it
        if close[i - 1] >= final_lower[i - 1]:
            final_lower[i] = max(raw_lower[i], final_lower[i - 1])
        else:
            final_lower[i] = raw_lower[i]

        # Trend: was bearish → bullish if price closes above upper band
        if not is_bullish[i - 1]:
            is_bullish[i] = close[i] > final_upper[i]
        # Was bullish → bearish if price closes below lower band
        else:
            is_bullish[i] = close[i] >= final_lower[i]

        supertrend[i] = final_lower[i] if is_bullish[i] else final_upper[i]

    return supertrend, is_bullish


class SupertrendStrategy:
    name = "supertrend"
    family = "trend"

    @staticmethod
    def default_params() -> dict[str, Any]:
        return {
            "atr_period": 7,
            "multiplier": 1.5,  # tighter bands = more flips on 15m
            "tp_pct": 0.15,  # ~37 pts MNQ (intraday scale)
            "sl_pct": 0.3,  # 2:1 risk vs TP
        }

    @staticmethod
    def generate(
        data: pd.DataFrame,
        params: dict[str, Any],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Enter on SuperTrend direction flip."""
        close = data["close"].values
        high = data["high"].values
        low = data["low"].values
        n = len(close)

        _, is_bullish = _supertrend(
            high,
            low,
            close,
            params["atr_period"],
            params["multiplier"],
        )

        # Flip: bearish→bullish = long entry; bullish→bearish = short entry
        long_flip = ~is_bullish[:-1] & is_bullish[1:]
        short_flip = is_bullish[:-1] & ~is_bullish[1:]

        entries = np.concatenate([[False], long_flip | short_flip])
        direction = np.concatenate([[True], long_flip])

        # Warmup guard: prevents synthetic flip from zero-init at bar atr_period
        warmup = params["atr_period"] + 1
        valid = np.zeros(n, dtype=bool)
        valid[warmup:] = True
        entries = entries & valid

        exits = np.zeros(n, dtype=bool)

        return entries, exits, direction
