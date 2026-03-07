"""ADX + EMA Trend Strategy.

Only take EMA crossover signals when ADX confirms a trending regime.
ADX < threshold = choppy market = no trade.
ADX >= threshold = trending = take EMA cross signal.

Entry:
  Long:  EMA_fast crosses above EMA_slow AND ADX >= threshold
  Short: EMA_fast crosses below EMA_slow AND ADX >= threshold

Exit: pct-based TP/SL via backtest engine.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from quant.strategies.ema_rsi import _ema
from quant.strategies.indicators import true_range, wilders_smooth


def _adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    """Wilder's ADX. Valid from index 2*period onward; 0.0 before."""
    n = len(close)
    tr = true_range(high, low, close)
    dm_plus = np.zeros(n)
    dm_minus = np.zeros(n)

    for i in range(1, n):
        h_diff = high[i] - high[i - 1]
        l_diff = low[i - 1] - low[i]
        dm_plus[i] = max(h_diff, 0.0) if h_diff > l_diff else 0.0
        dm_minus[i] = max(l_diff, 0.0) if l_diff > h_diff else 0.0

    # Wilder's smoothed ATR, +DM, -DM
    atr_s = wilders_smooth(tr, period)
    dm_plus_s = wilders_smooth(dm_plus, period)
    dm_minus_s = wilders_smooth(dm_minus, period)

    # +DI, -DI, DX
    with np.errstate(divide="ignore", invalid="ignore"):
        di_plus = np.where(atr_s > 0, 100.0 * dm_plus_s / atr_s, 0.0)
        di_minus = np.where(atr_s > 0, 100.0 * dm_minus_s / atr_s, 0.0)
        di_sum = di_plus + di_minus
        dx = np.where(di_sum > 0, 100.0 * np.abs(di_plus - di_minus) / di_sum, 0.0)

    # ADX = Wilder's smooth of DX, seeded at 2*period
    adx = np.zeros(n)
    start = 2 * period
    if start >= n:
        return adx
    # Seed: average of DX values from period..start-1
    valid_dx = dx[period:start]
    adx[start - 1] = valid_dx.mean() if len(valid_dx) > 0 else 0.0
    for i in range(start, n):
        adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period

    return adx


class AdxEmaStrategy:
    name = "adx_ema"
    family = "trend"

    @staticmethod
    def default_params() -> dict[str, Any]:
        return {
            "ema_fast": 9,
            "ema_slow": 21,
            "adx_period": 14,
            "adx_threshold": 15,  # lower = more signals (25 too strict for 15m)
            "tp_pct": 0.15,       # ~37 pts MNQ, ~9 pts MES (intraday scale)
            "sl_pct": 0.3,        # 2:1 risk vs TP
        }

    @staticmethod
    def generate(
        data: pd.DataFrame,
        params: dict[str, Any],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Generate EMA crossover signals gated by ADX trend strength."""
        close = data["close"].values
        high = data["high"].values
        low = data["low"].values
        n = len(close)

        fast = _ema(close, params["ema_fast"])
        slow = _ema(close, params["ema_slow"])
        adx = _adx(high, low, close, params["adx_period"])

        threshold = params["adx_threshold"]

        # EMA crossover: fast crosses slow
        cross_up = (fast[1:] > slow[1:]) & (fast[:-1] <= slow[:-1])
        cross_down = (fast[1:] < slow[1:]) & (fast[:-1] >= slow[:-1])

        # ADX gate: only trade when trending
        adx_ok = adx[1:] >= threshold

        long_entries = cross_up & adx_ok
        short_entries = cross_down & adx_ok

        entries = np.concatenate([[False], long_entries | short_entries])
        direction = np.concatenate([[True], long_entries])
        exits = np.zeros(n, dtype=bool)

        return entries, exits, direction
