"""RSI + Bollinger Band mean-reversion with ATR regime filter.

Theory: Mean-reversion signals (RSI extreme + Bollinger touch) work well
in ranging markets but get destroyed in trending markets. An ATR-based
regime filter restricts entries to low-volatility periods where
mean-reversion has higher probability.

Differs from rejected `rsi_mean_reversion` and `stoch_rsi`:
ATR regime filter prevents trading into trends.

Logic:
- Compute RSI, Bollinger Bands, and ATR percentile
- Low-ATR regime only (percentile <= threshold)
- Long:  RSI < oversold AND close < lower BB
- Short: RSI > overbought AND close > upper BB
- Exit:  TP/SL handled by backtest engine
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from quant.strategies.bollinger_squeeze import _sma, _rolling_std
from quant.strategies.ema_rsi import _rsi
from quant.strategies.indicators import atr_wilder

log = logging.getLogger(__name__)


class RsiBollingerFilteredStrategy:
    name = "rsi_bollinger_filtered"
    family = "mean_reversion"

    @staticmethod
    def default_params() -> dict[str, Any]:
        return {
            "rsi_period": 14,
            "rsi_os": 30,
            "rsi_ob": 70,
            "bb_period": 20,
            "bb_std": 2.0,
            "atr_period": 14,
            "atr_lookback": 100,
            "regime_threshold": 50,
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

        rsi_period: int = params["rsi_period"]
        rsi_os: float = params["rsi_os"]
        rsi_ob: float = params["rsi_ob"]
        bb_period: int = params["bb_period"]
        bb_std: float = params["bb_std"]
        atr_period: int = params["atr_period"]
        atr_lookback: int = params["atr_lookback"]
        regime_threshold: float = params["regime_threshold"]

        warmup = max(bb_period, atr_lookback)
        if n < warmup + 1:
            zeros = np.zeros(n, dtype=bool)
            return zeros.copy(), zeros.copy(), zeros.copy()

        # --- Indicators ---
        rsi = _rsi(close, rsi_period)
        sma = _sma(close, bb_period)
        std = _rolling_std(close, bb_period)
        bb_upper = sma + bb_std * std
        bb_lower = sma - bb_std * std

        # --- Regime filter (ATR percentile) ---
        atr = atr_wilder(high, low, close, atr_period)
        atr_pctl = pd.Series(atr).rolling(atr_lookback).rank(pct=True).values * 100
        low_atr = atr_pctl <= regime_threshold

        # --- Signals ---
        valid = np.zeros(n, dtype=bool)
        valid[warmup:] = True

        long_entries = (rsi < rsi_os) & (close < bb_lower) & low_atr & valid
        short_entries = (rsi > rsi_ob) & (close > bb_upper) & low_atr & valid

        entries = long_entries | short_entries
        direction = long_entries
        exits = np.zeros(n, dtype=bool)

        return entries, exits, direction
