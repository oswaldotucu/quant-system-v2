"""MACD + EMA Trend Filter Strategy.

MACD crossover signals gated by a slow EMA trend direction.
Only go long when price is above the trend EMA; only short when below.

Entry:
  Long:  MACD line crosses above signal line AND close > trend_ema
  Short: MACD line crosses below signal line AND close < trend_ema

Exit: pct-based TP/SL via backtest engine.

MACD settings from Optimus Futures recommendations for intraday futures:
  5-minute: (3, 10, 16) or (5, 13, 8)
  15-minute: (5, 15, 9) or (5, 34, 1)
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from quant.strategies.ema_rsi import _ema


class MacdTrendStrategy:
    name = "macd_trend"
    family = "trend"

    @staticmethod
    def default_params() -> dict[str, Any]:
        return {
            "macd_fast": 5,
            "macd_slow": 13,
            "macd_signal": 8,
            "trend_ema": 50,     # 100 too slow for 15m (lags ~25 hours)
            "tp_pct": 0.15,      # ~37 pts MNQ (intraday scale)
            "sl_pct": 0.3,       # 2:1 risk vs TP
        }

    @staticmethod
    def generate(
        data: pd.DataFrame,
        params: dict[str, Any],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Generate MACD crossover signals filtered by trend EMA."""
        close = data["close"].values
        n = len(close)

        macd_fast = params["macd_fast"]
        macd_slow = params["macd_slow"]
        macd_sig = params["macd_signal"]
        trend_period = params["trend_ema"]

        ema_fast = _ema(close, macd_fast)
        ema_slow = _ema(close, macd_slow)
        macd_line = ema_fast - ema_slow
        signal_line = _ema(macd_line, macd_sig)
        trend_ema = _ema(close, trend_period)

        # MACD crossovers
        cross_up = (macd_line[1:] > signal_line[1:]) & (macd_line[:-1] <= signal_line[:-1])
        cross_down = (macd_line[1:] < signal_line[1:]) & (macd_line[:-1] >= signal_line[:-1])

        # Trend gate
        above_trend = close[1:] > trend_ema[1:]
        below_trend = close[1:] < trend_ema[1:]

        long_entries = cross_up & above_trend
        short_entries = cross_down & below_trend

        entries = np.concatenate([[False], long_entries | short_entries])
        direction = np.concatenate([[True], long_entries])
        exits = np.zeros(n, dtype=bool)

        return entries, exits, direction
