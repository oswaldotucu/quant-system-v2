"""EMA + RSI trend-following strategy.

V1 RESEARCH REFERENCE: OOS PF 2.405 (MNQ), 6.132 (MES), 2.604 (MGC) on 15m.
V2 must validate these independently through its pipeline once data is loaded.
Params are the starting point. Do NOT change without re-running OOS_VAL gate.

Logic:
- Long:  EMA(fast) > EMA(slow) AND RSI crosses from oversold (< rsi_os) back above it
- Short: EMA(fast) < EMA(slow) AND RSI crosses from overbought (> rsi_ob) back below it
- Exit:  TP = entry + tp_pct% OR SL = entry - sl_pct% (handled in backtest engine)
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


class EmaRsiStrategy:
    name = "ema_rsi"
    family = "trend_following"

    @staticmethod
    def default_params() -> dict[str, Any]:
        """Starting-point defaults for 15m micro-futures.

        Wider RSI bands (45/55) and tight TP/SL for intraday resolution.
        Optuna will optimize from here.
        """
        return {
            "ema_fast": 5,
            "ema_slow": 13,
            "rsi_period": 9,
            "rsi_os": 45,    # oversold threshold (wider = more signals)
            "rsi_ob": 55,    # overbought threshold
            "tp_pct": 0.15,  # take-profit % (~37 pts MNQ, ~9 pts MES)
            "sl_pct": 0.3,   # stop-loss %
        }

    @staticmethod
    def generate(
        data: pd.DataFrame,
        params: dict[str, Any],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return (long_entries, short_entries, long_exits, short_exits) signals.

        Note: returns 6 arrays for vectorbt portfolio.from_signals() call:
            entries_long, entries_short, exits_long, exits_short
        Packed as (entries, exits, direction) per base Protocol, where:
            entries   = entries_long | entries_short
            exits     = exits_long | exits_short
            direction = True where long, False where short
        """
        close = data["close"].values
        n = len(close)

        ema_fast = _ema(close, params["ema_fast"])
        ema_slow = _ema(close, params["ema_slow"])
        rsi = _rsi(close, params["rsi_period"])

        trend_up = ema_fast > ema_slow
        trend_dn = ema_fast < ema_slow

        # RSI crosses: was below threshold, now above (for longs)
        rsi_cross_up = (rsi[1:] >= params["rsi_os"]) & (rsi[:-1] < params["rsi_os"])
        rsi_cross_up = np.concatenate([[False], rsi_cross_up])

        rsi_cross_dn = (rsi[1:] <= params["rsi_ob"]) & (rsi[:-1] > params["rsi_ob"])
        rsi_cross_dn = np.concatenate([[False], rsi_cross_dn])

        long_entries = trend_up & rsi_cross_up
        short_entries = trend_dn & rsi_cross_dn

        entries = long_entries | short_entries
        direction = long_entries  # True = long, False = short (where entries is True)

        # Exits: handled by TP/SL in backtest engine; emit no explicit exit signals
        exits = np.zeros(n, dtype=bool)

        return entries, exits, direction


# ---------------------------------------------------------------------------
# Technical indicator helpers (dependency-free, use only numpy)
# ---------------------------------------------------------------------------

def _ema(close: np.ndarray, period: int) -> np.ndarray:
    """Exponential moving average."""
    alpha = 2.0 / (period + 1)
    result = np.empty_like(close)
    result[0] = close[0]
    for i in range(1, len(close)):
        result[i] = alpha * close[i] + (1 - alpha) * result[i - 1]
    return result


def _rsi(close: np.ndarray, period: int) -> np.ndarray:
    """RSI using Wilder's smoothing (result always in [0, 100])."""
    n = len(close)
    rsi = np.full(n, 50.0)  # neutral until enough bars

    if n <= period:
        return rsi

    delta = np.diff(close)                     # length n-1
    gains = np.maximum(delta, 0.0)
    losses = np.maximum(-delta, 0.0)

    # Seed: simple average of the first `period` bars
    avg_gain = gains[:period].mean()
    avg_loss = losses[:period].mean()

    # First valid RSI value (at index `period`)
    if avg_loss == 0.0:
        rsi[period] = 100.0
    else:
        rsi[period] = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)

    # Wilder's smoothing for the rest
    for i in range(period, n - 1):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0.0:
            rsi[i + 1] = 100.0
        else:
            rsi[i + 1] = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)

    return rsi
