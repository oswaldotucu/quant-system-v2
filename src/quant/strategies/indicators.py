"""Shared technical indicators used across multiple strategies.

Keep pure functions only — no I/O, no pandas, no state.
"""

from __future__ import annotations

import numpy as np


def wilders_smooth(arr: np.ndarray, period: int) -> np.ndarray:
    """Wilder's smoothing (exponential moving average variant).

    Seed = mean of arr[1:period+1]. Then:
        s[i] = s[i-1] - s[i-1]/period + arr[i]

    Used for ATR, +DM, -DM, and other Wilder-family indicators.
    """
    n = len(arr)
    s = np.zeros(n)
    if n <= period:
        return s
    s[period] = arr[1 : period + 1].mean()
    for i in range(period + 1, n):
        s[i] = s[i - 1] - s[i - 1] / period + arr[i]
    return s


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """True Range. tr[0] = 0, valid from index 1 onward."""
    n = len(close)
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        )
    return tr


def atr_wilder(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    """Wilder's smoothed ATR. Seed = mean of first `period` TR values."""
    tr = true_range(high, low, close)
    return wilders_smooth(tr, period)
