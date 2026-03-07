"""Session Momentum strategy — opening range breakout with time bounds.

Theory: The first 30-60 minutes of RTH (9:30 ET) establish the day's
directional bias. A breakout from this opening range, if the range is
large enough, tends to continue. Restricting trades to a window after
the range avoids overnight chop.

Differs from rejected `opening_range_breakout`: adds time bounds
(trade_window) and minimum range size filter (min_range_pct).

Logic:
- Identify RTH open (9:30 ET) from DatetimeIndex
- Track high/low of first range_bars after open
- Long:  close > opening_high AND range >= min_range_pct
- Short: close < opening_low AND range >= min_range_pct
- Only signal within trade_window bars after the range closes
- Exit: TP/SL handled by backtest engine
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

RTH_OPEN_HOUR = 9
RTH_OPEN_MINUTE = 30


class SessionMomentumStrategy:
    name = "session_momentum"
    family = "event_driven"

    @staticmethod
    def default_params() -> dict[str, Any]:
        return {
            "range_bars": 4,
            "trade_window": 16,
            "min_range_pct": 0.1,
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
        n = len(close)

        range_bars: int = params["range_bars"]
        trade_window: int = params["trade_window"]
        min_range_pct: float = params["min_range_pct"]

        if n < range_bars + 1:
            zeros = np.zeros(n, dtype=bool)
            return zeros.copy(), zeros.copy(), zeros.copy()

        long_entries = np.zeros(n, dtype=bool)
        short_entries = np.zeros(n, dtype=bool)

        # Identify session open bars (9:30 ET)
        idx = data.index
        is_session_open = (idx.hour == RTH_OPEN_HOUR) & (idx.minute == RTH_OPEN_MINUTE)
        session_open_indices = np.where(is_session_open)[0]

        for open_idx in session_open_indices:
            range_end = open_idx + range_bars
            if range_end >= n:
                continue

            # Opening range: high/low of first range_bars
            range_high = high[open_idx:range_end].max()
            range_low = low[open_idx:range_end].min()

            # Range size filter
            mid = (range_high + range_low) / 2
            if mid == 0:
                continue
            range_pct = (range_high - range_low) / mid * 100
            if range_pct < min_range_pct:
                continue

            # Trade window: from range_end to range_end + trade_window
            window_end = min(range_end + trade_window, n)
            for i in range(range_end, window_end):
                if close[i] > range_high:
                    long_entries[i] = True
                elif close[i] < range_low:
                    short_entries[i] = True

        entries = long_entries | short_entries
        direction = long_entries
        exits = np.zeros(n, dtype=bool)

        return entries, exits, direction
