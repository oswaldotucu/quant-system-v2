"""Keltner Channel momentum strategy.

ATR-based channel around an EMA. When price closes outside the channel,
it signals strong momentum. Direction confirmed by EMA slope.

Entry:
  Middle line = EMA(close, kc_period)
  Upper band  = middle + multiplier * ATR(atr_period)
  Lower band  = middle - multiplier * ATR(atr_period)

  Long:  close > upper band AND EMA is rising (current > previous)
  Short: close < lower band AND EMA is falling (current < previous)

Exit: pct-based TP/SL via backtest engine.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from quant.strategies.indicators import atr_wilder, ema

log = logging.getLogger(__name__)


class KeltnerChannelStrategy:
    name = "keltner_channel"
    family = "trend_following"

    @staticmethod
    def default_params() -> dict[str, Any]:
        """Default params tuned for 15m micro-futures intraday scale."""
        return {
            "kc_period": 20,  # EMA period for the middle line
            "atr_period": 14,  # ATR period for channel width
            "multiplier": 1.5,  # ATR multiplier for band distance
            "tp_pct": 0.15,  # take-profit % (~37 pts MNQ)
            "sl_pct": 0.3,  # stop-loss %
        }

    @staticmethod
    def generate(
        data: pd.DataFrame,
        params: dict[str, Any],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Generate entry signals on Keltner Channel breakout with EMA slope confirmation.

        Returns:
            (entries, exits, direction) — boolean numpy arrays, same length as data.
            entries:   True on bars where a trade should be entered.
            exits:     Always False (TP/SL handled by the backtest engine).
            direction: True = long, False = short (meaningful only where entries is True).
        """
        close: np.ndarray = np.asarray(data["close"].values)
        high: np.ndarray = np.asarray(data["high"].values)
        low: np.ndarray = np.asarray(data["low"].values)
        n = len(close)

        # Early return: need at least warmup bars for indicators to converge
        warmup = max(params["kc_period"], params["atr_period"])
        if n <= warmup:
            zeros = np.zeros(n, dtype=bool)
            return zeros, zeros.copy(), zeros.copy()

        # Indicators
        middle = ema(close, params["kc_period"])
        atr = atr_wilder(high, low, close, params["atr_period"])

        upper_band = middle + params["multiplier"] * atr
        lower_band = middle - params["multiplier"] * atr

        # EMA slope: rising if current > previous bar
        ema_rising = np.zeros(n, dtype=bool)
        ema_falling = np.zeros(n, dtype=bool)
        ema_rising[1:] = middle[1:] > middle[:-1]
        ema_falling[1:] = middle[1:] < middle[:-1]

        # Warmup guard: EMA and ATR need convergence period
        valid = np.zeros(n, dtype=bool)
        valid[warmup:] = True

        # Breakout signals
        long_entries = (close > upper_band) & ema_rising & valid
        short_entries = (close < lower_band) & ema_falling & valid

        entries = long_entries | short_entries
        direction = long_entries  # True = long, False = short (where entries is True)

        # Exits: handled by TP/SL in backtest engine; no explicit exit signals
        exits = np.zeros(n, dtype=bool)

        return entries, exits, direction
