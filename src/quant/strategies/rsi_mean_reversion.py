"""RSI Mean Reversion strategy — CANDIDATE (testing in V1 Optuna).

DO NOT USE until OOS PF >= 1.5 is confirmed. NOT in STRATEGY_REGISTRY yet.

Logic:
- Long:  RSI drops below rsi_oversold, next bar RSI crosses back up above it
- Short: RSI rises above rsi_overbought, next bar RSI crosses back below it
- TP/SL: pct-based, handled by backtest engine
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from quant.strategies.ema_rsi import _ema, _rsi  # noqa: F401 -- shared helpers


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
            "tp_pct": 0.15,      # ~37 pts MNQ (intraday scale)
            "sl_pct": 0.3,       # 2:1 risk vs TP
        }

    @staticmethod
    def generate(
        data: pd.DataFrame,
        params: dict[str, Any],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Generate RSI reversion entry signals."""
        close = data["close"].values
        n = len(close)

        rsi = _rsi(close, params["rsi_period"])

        # Long: RSI was below oversold, now crosses back above
        long_entries = (
            (rsi[1:] >= params["rsi_oversold"]) & (rsi[:-1] < params["rsi_oversold"])
        )
        long_entries = np.concatenate([[False], long_entries])

        # Short: RSI was above overbought, now crosses back below
        short_entries = (
            (rsi[1:] <= params["rsi_overbought"]) & (rsi[:-1] > params["rsi_overbought"])
        )
        short_entries = np.concatenate([[False], short_entries])

        entries = long_entries | short_entries
        direction = long_entries
        exits = np.zeros(n, dtype=bool)

        return entries, exits, direction
