"""Shared technical indicators used across multiple strategies.

Keep pure functions only — no I/O, no pandas, no state.
Looping indicators are JIT-compiled with numba for near-native speed.
"""

from __future__ import annotations

import numba
import numpy as np
import pandas as pd


@numba.njit(cache=True)
def ema(close: np.ndarray, period: int) -> np.ndarray:  # noqa: ANN001
    """Exponential moving average."""
    alpha = 2.0 / (period + 1)
    result = np.empty_like(close)
    result[0] = close[0]
    for i in range(1, len(close)):
        result[i] = alpha * close[i] + (1 - alpha) * result[i - 1]
    return result


@numba.njit(cache=True)
def rsi(close: np.ndarray, period: int) -> np.ndarray:  # noqa: ANN001
    """RSI using Wilder's smoothing (result always in [0, 100])."""
    n = len(close)
    rsi_arr = np.full(n, 50.0)  # neutral until enough bars

    if n <= period:
        return rsi_arr

    delta = np.diff(close)  # length n-1
    gains = np.maximum(delta, 0.0)
    losses = np.maximum(-delta, 0.0)

    # Seed: simple average of the first `period` bars
    avg_gain = gains[:period].mean()
    avg_loss = losses[:period].mean()

    # First valid RSI value (at index `period`)
    if avg_loss == 0.0:
        rsi_arr[period] = 100.0
    else:
        rsi_arr[period] = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)

    # Wilder's smoothing for the rest
    for i in range(period, n - 1):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0.0:
            rsi_arr[i + 1] = 100.0
        else:
            rsi_arr[i + 1] = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)

    return rsi_arr


def sma(arr: np.ndarray, period: int) -> np.ndarray:
    """Simple moving average. First (period-1) values are NaN-filled with 0."""
    n = len(arr)
    result = np.zeros(n)
    if n < period:
        return result
    # Cumulative sum trick for O(n) SMA
    cumsum = np.cumsum(arr)
    result[period - 1] = cumsum[period - 1] / period
    result[period:] = (cumsum[period:] - cumsum[:-period]) / period
    return result


def rolling_std(arr: np.ndarray, period: int) -> np.ndarray:
    """Rolling standard deviation (ddof=1). First (period-1) values are 0."""
    n = len(arr)
    result = np.zeros(n)
    if n < period:
        return result
    # Use pandas for correctness on rolling std with ddof=1
    s = pd.Series(arr)
    rolling_vals: np.ndarray = np.asarray(s.rolling(period).std(ddof=1).values)
    # Replace NaN with 0 for the warmup period
    result[:] = np.nan_to_num(rolling_vals, nan=0.0)
    return result


@numba.njit(cache=True)
def wilders_smooth(arr: np.ndarray, period: int) -> np.ndarray:  # noqa: ANN001
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
    """True Range. tr[0] = 0, valid from index 1 onward. Fully vectorized."""
    n = len(high)
    tr = np.zeros(n)
    tr1 = high[1:] - low[1:]
    tr2 = np.abs(high[1:] - close[:-1])
    tr3 = np.abs(low[1:] - close[:-1])
    tr[1:] = np.maximum(tr1, np.maximum(tr2, tr3))
    return tr


def atr_wilder(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    """Wilder's smoothed ATR. Seed = mean of first `period` TR values."""
    tr = true_range(high, low, close)
    return wilders_smooth(tr, period)
