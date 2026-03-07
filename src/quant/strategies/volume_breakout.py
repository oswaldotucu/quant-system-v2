"""Volume Breakout strategy — high-volume breaks of session highs/lows.

Theory: Volume confirms price conviction. When price breaks a session
high/low on significantly above-average volume, the move is more likely
to continue than to reverse.

Logic:
- Compute rolling average volume over vol_period bars
- Compute rolling session high/low over session_lookback bars
- Long:  close > session high AND volume > vol_multiplier * avg_volume
- Short: close < session low AND volume > vol_multiplier * avg_volume
- Exit:  TP/SL handled by backtest engine
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


class VolumeBreakoutStrategy:
    name = "volume_breakout"
    family = "price_action"

    @staticmethod
    def default_params() -> dict[str, Any]:
        return {
            "vol_period": 20,
            "vol_multiplier": 2.0,
            "session_lookback": 16,
            "tp_pct": 0.15,
            "sl_pct": 0.3,
        }

    @staticmethod
    def generate(
        data: pd.DataFrame,
        params: dict[str, Any],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        close = data["close"].values
        high = data["high"].values
        low = data["low"].values
        volume = data["volume"].values.astype(float)
        n = len(close)

        vol_period: int = params["vol_period"]
        vol_multiplier: float = params["vol_multiplier"]
        session_lookback: int = params["session_lookback"]

        warmup = max(vol_period, session_lookback)
        if n < warmup + 1:
            zeros = np.zeros(n, dtype=bool)
            return zeros.copy(), zeros.copy(), zeros.copy()

        # Rolling average volume
        avg_vol = pd.Series(volume).rolling(vol_period).mean().values

        # Session high/low (rolling window, shifted to exclude current bar)
        session_high = pd.Series(high).rolling(session_lookback).max().shift(1).values
        session_low = pd.Series(low).rolling(session_lookback).min().shift(1).values

        # Volume spike filter
        vol_spike = volume > (vol_multiplier * avg_vol)

        # Warmup guard
        valid = np.zeros(n, dtype=bool)
        valid[warmup:] = True

        # Signals (NaN comparisons return False, safe for warmup)
        long_entries = (close > session_high) & vol_spike & valid
        short_entries = (close < session_low) & vol_spike & valid

        entries = long_entries | short_entries
        direction = long_entries
        exits = np.zeros(n, dtype=bool)

        return entries, exits, direction
