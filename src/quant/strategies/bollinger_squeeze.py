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

from quant.strategies.indicators import rolling_std, sma

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
            "tp_pct": 0.15,  # ~37 pts MNQ, ~9 pts MES (intraday scale)
            "sl_pct": 0.3,  # 2:1 risk vs TP
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
                n,
                bb_period,
                squeeze_lookback,
            )
            zeros = np.zeros(n, dtype=bool)
            return zeros.copy(), zeros.copy(), zeros.copy()

        # --- Bollinger Bands ---
        sma_vals = sma(close, bb_period)
        std = rolling_std(close, bb_period)

        upper_raw = sma_vals + bb_std * std
        lower_raw = sma_vals - bb_std * std

        # Shift bands by 1 bar so breakout signals compare close[i] against
        # the PREVIOUS bar's band — avoids self-referential bias where a large
        # bar move both pushes the band AND exceeds it.
        upper = np.roll(upper_raw, 1)
        upper[0] = np.nan
        lower = np.roll(lower_raw, 1)
        lower[0] = np.nan

        # Bandwidth uses unshifted bands — measures current bar's volatility state.
        # Avoid division by zero where SMA is 0 (shouldn't happen with real prices)
        with np.errstate(divide="ignore", invalid="ignore"):
            bandwidth = np.where(sma_vals != 0.0, (upper_raw - lower_raw) / sma_vals, 0.0)

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
