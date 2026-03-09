"""Multi-Timeframe EMA Alignment — 15m crossover confirmed by 1h trend.

Theory: Short-timeframe signals are more reliable when they agree with
longer-timeframe trend direction. Reduces false crossovers in choppy markets.

Logic:
- Resample 15m data -> 1h internally (no protocol change)
- Fast/slow EMA crossover on 15m as entry trigger
- 1h EMA slope (current > previous) as trend confirmation
- Long:  15m fast EMA crosses above slow EMA AND 1h EMA rising
- Short: 15m fast EMA crosses below slow EMA AND 1h EMA falling
- Exit:  TP/SL handled by backtest engine
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from quant.strategies.ema_rsi import _ema

log = logging.getLogger(__name__)


class MtfEmaAlignmentStrategy:
    name = "mtf_ema_alignment"
    family = "multi_timeframe"

    @staticmethod
    def default_params() -> dict[str, Any]:
        return {
            "fast_ema": 8,
            "slow_ema": 21,
            "htf_ema": 20,
            "tp_pct": 0.15,
            "sl_pct": 0.3,
        }

    @staticmethod
    def generate(
        data: pd.DataFrame,
        params: dict[str, Any],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        close = data["close"].values
        n = len(close)

        fast_period: int = params["fast_ema"]
        slow_period: int = params["slow_ema"]
        htf_period: int = params["htf_ema"]

        warmup = slow_period
        if n < warmup + 1:
            zeros = np.zeros(n, dtype=bool)
            return zeros.copy(), zeros.copy(), zeros.copy()

        # --- 15m EMAs ---
        fast_ema = _ema(close, fast_period)
        slow_ema = _ema(close, slow_period)

        # EMA crossover: fast crosses above/below slow
        fast_above = fast_ema > slow_ema
        cross_up = np.zeros(n, dtype=bool)
        cross_down = np.zeros(n, dtype=bool)
        cross_up[1:] = fast_above[1:] & ~fast_above[:-1]
        cross_down[1:] = ~fast_above[1:] & fast_above[:-1]

        # --- 1h EMA (resampled from 15m) ---
        htf_close = data["close"].resample("1h").last().dropna()
        if len(htf_close) < htf_period + 2:
            zeros = np.zeros(n, dtype=bool)
            return zeros.copy(), zeros.copy(), zeros.copy()

        htf_ema_vals = _ema(htf_close.values, htf_period)
        htf_ema_series = pd.Series(htf_ema_vals, index=htf_close.index)

        # Slope: current 1h EMA > previous 1h EMA
        htf_slope = pd.Series(np.zeros(len(htf_ema_vals)), index=htf_close.index)
        htf_slope.iloc[1:] = np.where(htf_ema_vals[1:] > htf_ema_vals[:-1], 1.0, -1.0)

        # Shift by 1 hour before forward-filling to 15m index.
        # Without shift, resample("1h").last() labels the [10:00,11:00) bin
        # at 10:00 using the 10:45 close — giving 10:00/10:15/10:30 bars
        # access to future data (look-ahead bias). Shifting ensures each
        # hour's EMA is only visible after the hour fully closes.
        _htf_ema_15m = htf_ema_series.shift(1).reindex(data.index, method="ffill")  # noqa: F841
        htf_slope_15m = htf_slope.shift(1).reindex(data.index, method="ffill")

        slope_up = htf_slope_15m.values > 0
        slope_down = htf_slope_15m.values < 0

        # Warmup guard
        valid = np.zeros(n, dtype=bool)
        valid[warmup:] = True

        long_entries = cross_up & slope_up & valid
        short_entries = cross_down & slope_down & valid

        entries = long_entries | short_entries
        direction = long_entries
        exits = np.zeros(n, dtype=bool)

        return entries, exits, direction
