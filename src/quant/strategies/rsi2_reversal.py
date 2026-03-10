"""RSI(2) Mean Reversion with Trend Filter.

Ultra-short RSI(2) detects extreme overbought/oversold conditions.
Trend EMA ensures we only fade pullbacks, not counter-trend moves.
Based on Larry Connors' RSI(2) methodology adapted for futures.

Entry:
  Long:  RSI(rsi_period) < rsi_os AND close > trend_ema (pullback in uptrend)
  Short: RSI(rsi_period) > rsi_ob AND close < trend_ema (rally in downtrend)

Exit: pct-based TP/SL via backtest engine.

Note: RSI period 2-5 gives very sensitive signals (crosses extreme levels often).
      Trend EMA 50-200 controls directionality of trades.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from quant.strategies.indicators import ema, rsi


class Rsi2ReversalStrategy:
    name = "rsi2_reversal"
    family = "mean_reversion"

    @staticmethod
    def default_params() -> dict[str, Any]:
        return {
            "rsi_period": 2,
            "rsi_os": 10,
            "rsi_ob": 90,
            "trend_ema": 50,  # 100 too slow for 15m
            "tp_pct": 0.15,  # ~37 pts MNQ (intraday scale)
            "sl_pct": 0.3,  # 2:1 risk vs TP
        }

    @staticmethod
    def generate(
        data: pd.DataFrame,
        params: dict[str, Any],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Enter when RSI hits extreme AND price is on right side of trend EMA."""
        close = data["close"].values
        n = len(close)

        rsi_vals = rsi(close, params["rsi_period"])
        trend = ema(close, params["trend_ema"])

        rsi_os = params["rsi_os"]
        rsi_ob = params["rsi_ob"]

        # Long: RSI crosses UP through oversold level (exits oversold) AND price above trend
        long_entries = (rsi_vals[1:] >= rsi_os) & (rsi_vals[:-1] < rsi_os) & (close[1:] > trend[1:])
        # Short: RSI crosses DOWN through overbought (exits overbought) AND price below trend
        short_entries = (
            (rsi_vals[1:] <= rsi_ob) & (rsi_vals[:-1] > rsi_ob) & (close[1:] < trend[1:])
        )

        entries = np.concatenate([[False], long_entries | short_entries])
        direction = np.concatenate([[True], long_entries])

        # Warmup guard: trend EMA needs convergence period
        warmup = max(params["rsi_period"], params["trend_ema"])
        valid = np.zeros(n, dtype=bool)
        valid[warmup:] = True
        entries = entries & valid

        exits = np.zeros(n, dtype=bool)

        return entries, exits, direction
