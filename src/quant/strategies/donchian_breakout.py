"""Donchian Channel Breakout strategy.

Classic Turtle Trader system — buy on new N-period highs, sell on new N-period lows.
Trend-following with channel breakouts, optionally filtered by EMA direction.

Entry:
  Long:  close crosses above the highest high of the last `entry_period` bars
  Short: close crosses below the lowest low of the last `entry_period` bars
  Optional: Only trade in the direction of a `trend_ema`-period EMA

Exit: pct-based TP/SL via backtest engine.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from quant.strategies.indicators import ema

log = logging.getLogger(__name__)


class DonchianBreakoutStrategy:
    name = "donchian_breakout"
    family = "trend_following"

    @staticmethod
    def default_params() -> dict[str, Any]:
        """Starting-point defaults for 15m micro-futures.

        entry_period = 20: classic 20-bar Donchian channel
        trend_ema = 50: 50-bar EMA for optional trend filter
        use_trend_filter = 1: trend filter ON by default
        tp_pct / sl_pct: intraday scale for micro-futures
        """
        return {
            "entry_period": 20,
            "trend_ema": 50,
            "use_trend_filter": 1,  # 1 = on, 0 = off (int for Optuna suggest_int)
            "tp_pct": 0.15,
            "sl_pct": 0.3,
        }

    @staticmethod
    def generate(
        data: pd.DataFrame,
        params: dict[str, Any],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Generate entry signals on Donchian channel breakouts.

        Returns:
            (entries, exits, direction) — boolean arrays, same length as data.
            direction: True = long, False = short.
        """
        close = data["close"].values
        high = data["high"].values
        low = data["low"].values
        n = len(close)

        entry_period: int = params["entry_period"]
        trend_ema_period: int = params["trend_ema"]
        use_trend_filter: bool = bool(params["use_trend_filter"])

        # Short-circuit: not enough data for any signal
        if n < entry_period + 1:
            zeros = np.zeros(n, dtype=bool)
            return zeros.copy(), zeros.copy(), zeros.copy()

        # ----- Donchian channels (rolling highest high / lowest low) -----
        # .shift(1) excludes the current bar — channel is from the prior entry_period bars
        upper_channel = pd.Series(high).rolling(entry_period).max().shift(1).values
        lower_channel = pd.Series(low).rolling(entry_period).min().shift(1).values

        # ----- Breakout signals (vectorized; NaN comparisons return False) -----
        long_entries = close > upper_channel
        short_entries = close < lower_channel

        # ----- Optional trend filter -----
        if use_trend_filter:
            ema_vals = ema(close, trend_ema_period)
            # Long only when price is above EMA; short only when below
            long_entries = long_entries & (close > ema_vals)
            short_entries = short_entries & (close < ema_vals)

        entries = long_entries | short_entries
        direction = long_entries  # True = long, False = short (where entries is True)

        # Exits: handled by TP/SL in backtest engine; emit no explicit exit signals
        exits = np.zeros(n, dtype=bool)

        return entries, exits, direction
