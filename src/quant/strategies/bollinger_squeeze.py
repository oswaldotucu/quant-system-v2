"""Bollinger Band Squeeze strategy — breakout from low-volatility compression.

Theory: When Bollinger Band width contracts below a threshold (low volatility),
a breakout is imminent. Enter when price breaks out of the compressed bands.

Logic:
- Compute Bollinger Bands (SMA + N*stddev)
- Compute bandwidth: (upper - lower) / middle
- Squeeze detected when bandwidth < squeeze_threshold for squeeze_lookback bars
- Long:  squeeze was active AND price closes above upper band
- Short: squeeze was active AND price closes below lower band
- Exit:  TP/SL handled by backtest engine
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


class BollingerSqueezeStrategy:
    name = "bollinger_squeeze"
    family = "breakout"

    @staticmethod
    def default_params() -> dict[str, Any]:
        """Starting-point defaults for 15m micro-futures.

        Bandwidth-based squeeze (not relative to rolling avg width).
        Tight TP/SL for intraday resolution.
        """
        return {
            "bb_period": 20,
            "bb_std": 2.0,
            "squeeze_threshold": 0.02,
            "squeeze_lookback": 5,
            "tp_pct": 0.15,   # ~37 pts MNQ, ~9 pts MES (intraday scale)
            "sl_pct": 0.3,    # 2:1 risk vs TP
        }

    @staticmethod
    def generate(
        data: pd.DataFrame,
        params: dict[str, Any],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Generate breakout signals from Bollinger Band squeezes.

        Args:
            data: OHLCV DataFrame with DatetimeIndex
            params: strategy hyperparameters

        Returns:
            (entries, exits, direction) — boolean numpy arrays, same length as data
        """
        close: np.ndarray = np.asarray(data["close"].values)
        n = len(close)

        bb_period: int = params["bb_period"]
        bb_std: float = params["bb_std"]
        squeeze_threshold: float = params["squeeze_threshold"]
        squeeze_lookback: int = params["squeeze_lookback"]

        # Guard: not enough data for indicators
        min_bars = bb_period + squeeze_lookback
        if n < min_bars:
            log.warning(
                "Insufficient bars (%d) for bb_period=%d + squeeze_lookback=%d",
                n, bb_period, squeeze_lookback,
            )
            zeros = np.zeros(n, dtype=bool)
            return zeros.copy(), zeros.copy(), zeros.copy()

        # --- Bollinger Bands ---
        sma = _sma(close, bb_period)
        std = _rolling_std(close, bb_period)

        upper = sma + bb_std * std
        lower = sma - bb_std * std

        # Bandwidth: (upper - lower) / middle
        # Avoid division by zero where SMA is 0 (shouldn't happen with real prices)
        with np.errstate(divide="ignore", invalid="ignore"):
            bandwidth = np.where(sma != 0.0, (upper - lower) / sma, 0.0)

        # --- Squeeze detection ---
        # A bar is "in squeeze" when bandwidth < squeeze_threshold
        in_squeeze = bandwidth < squeeze_threshold

        # Count consecutive squeeze bars
        squeeze_count = np.zeros(n, dtype=int)
        for i in range(1, n):
            if in_squeeze[i]:
                squeeze_count[i] = squeeze_count[i - 1] + 1
            else:
                squeeze_count[i] = 0

        # Squeeze is "active" when we've had enough consecutive squeeze bars
        # Use the previous bar's squeeze count to avoid look-ahead:
        # the squeeze must have been established BEFORE the breakout bar
        squeeze_active = np.zeros(n, dtype=bool)
        squeeze_active[1:] = squeeze_count[:-1] >= squeeze_lookback

        # --- Breakout signals ---
        # Mask out warmup bars where SMA/std are zero (would create false squeezes)
        valid = np.zeros(n, dtype=bool)
        valid[bb_period:] = True
        long_entries = squeeze_active & (close > upper) & valid
        short_entries = squeeze_active & (close < lower) & valid

        entries = long_entries | short_entries
        direction = long_entries  # True = long, False = short (where entries is True)

        # Exits handled by TP/SL in backtest engine
        exits = np.zeros(n, dtype=bool)

        return entries, exits, direction


# ---------------------------------------------------------------------------
# Internal helper functions (pure numpy, no pandas)
# ---------------------------------------------------------------------------

def _sma(arr: np.ndarray, period: int) -> np.ndarray:
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


def _rolling_std(arr: np.ndarray, period: int) -> np.ndarray:
    """Rolling standard deviation (ddof=1). First (period-1) values are 0."""
    n = len(arr)
    result = np.zeros(n)
    if n < period:
        return result
    # Use pandas for correctness on rolling std with ddof=1
    s = pd.Series(arr)
    rolling: np.ndarray = np.asarray(s.rolling(period).std(ddof=1).values)
    # Replace NaN with 0 for the warmup period
    result[:] = np.nan_to_num(rolling, nan=0.0)
    return result
