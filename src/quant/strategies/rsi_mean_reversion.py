"""RSI Mean Reversion strategy — REJECTED (no IS edge in V2 Optuna sweep).

Tested 2026-03-09: all Optuna trials returned 0. Warmup guard confirmed
functional but strategy lacks sufficient signal density for IS-train PF >= 1.1.

Not in STRATEGY_REGISTRY. Kept as reference implementation.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from quant.strategies.indicators import rsi


class RsiMeanReversionStrategy:
    name = "rsi_mean_reversion"
    family = "mean_reversion"

    @staticmethod
    def default_params() -> dict[str, Any]:
        """Params from V1 Optuna — NOT yet OOS validated."""
        return {
            "rsi_period": 14,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "tp_pct": 0.15,  # ~37 pts MNQ (intraday scale)
            "sl_pct": 0.3,  # 2:1 risk vs TP
        }

    @staticmethod
    def generate(
        data: pd.DataFrame,
        params: dict[str, Any],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Generate RSI reversion entry signals."""
        close = data["close"].values
        n = len(close)

        rsi_vals = rsi(close, params["rsi_period"])

        # Long: RSI was below oversold, now crosses back above
        long_entries = (rsi_vals[1:] >= params["rsi_oversold"]) & (
            rsi_vals[:-1] < params["rsi_oversold"]
        )
        long_entries = np.concatenate([[False], long_entries])

        # Short: RSI was above overbought, now crosses back below
        short_entries = (rsi_vals[1:] <= params["rsi_overbought"]) & (
            rsi_vals[:-1] > params["rsi_overbought"]
        )
        short_entries = np.concatenate([[False], short_entries])

        # Warmup guard: RSI fills with synthetic 50.0 during warmup
        warmup = params["rsi_period"]
        valid = np.zeros(n, dtype=bool)
        valid[warmup:] = True

        entries = (long_entries | short_entries) & valid
        direction = long_entries
        exits = np.zeros(n, dtype=bool)

        return entries, exits, direction
