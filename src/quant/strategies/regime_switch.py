"""Regime Switch strategy — adapts signal logic to volatility regime.

Theory: Markets alternate between trending and ranging regimes. Using a
trend-following strategy in ranging markets (or mean-reversion in trending
markets) causes losses. ATR percentile classifies the regime; each regime
gets its own signal generator.

Logic:
- ATR(14) rolling percentile over 100 bars classifies regime
- High-ATR (trending): EMA crossover (fast/slow)
- Low-ATR (ranging): RSI extreme + Bollinger Band confirmation
- Exit: TP/SL handled by backtest engine
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from quant.strategies.bollinger_squeeze import _rolling_std, _sma
from quant.strategies.ema_rsi import _ema, _rsi
from quant.strategies.indicators import atr_wilder

log = logging.getLogger(__name__)


class RegimeSwitchStrategy:
    name = "regime_switch"
    family = "regime_aware"

    @staticmethod
    def default_params() -> dict[str, Any]:
        return {
            "atr_period": 14,
            "atr_lookback": 100,
            "regime_threshold": 60,
            "trend_fast_ema": 8,
            "trend_slow_ema": 21,
            "rev_rsi_period": 14,
            "rev_rsi_os": 30,
            "rev_rsi_ob": 70,
            "rev_bb_period": 20,
            "rev_bb_std": 2.0,
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

        atr_period: int = params["atr_period"]
        atr_lookback: int = params["atr_lookback"]
        regime_threshold: float = params["regime_threshold"]
        trend_fast: int = params["trend_fast_ema"]
        trend_slow: int = params["trend_slow_ema"]
        rev_rsi_period: int = params["rev_rsi_period"]
        rev_rsi_os: float = params["rev_rsi_os"]
        rev_rsi_ob: float = params["rev_rsi_ob"]
        rev_bb_period: int = params["rev_bb_period"]
        rev_bb_std: float = params["rev_bb_std"]

        warmup = max(atr_lookback, rev_bb_period, trend_slow)
        if n < warmup + 1:
            zeros = np.zeros(n, dtype=bool)
            return zeros.copy(), zeros.copy(), zeros.copy()

        # --- Regime classification ---
        atr = atr_wilder(high, low, close, atr_period)
        atr_pctl = pd.Series(atr).rolling(atr_lookback).rank(pct=True).values * 100
        high_atr = atr_pctl > regime_threshold
        low_atr = ~high_atr

        # --- Trend signals (EMA crossover) ---
        fast_ema = _ema(close, trend_fast)
        slow_ema = _ema(close, trend_slow)

        trend_long = np.zeros(n, dtype=bool)
        trend_short = np.zeros(n, dtype=bool)
        fast_above = fast_ema > slow_ema
        trend_long[1:] = fast_above[1:] & ~fast_above[:-1]
        trend_short[1:] = ~fast_above[1:] & fast_above[:-1]

        # --- Reversion signals (RSI + Bollinger Band) ---
        rsi = _rsi(close, rev_rsi_period)
        sma = _sma(close, rev_bb_period)
        std = _rolling_std(close, rev_bb_period)
        bb_lower = sma - rev_bb_std * std
        bb_upper = sma + rev_bb_std * std

        rev_long = (rsi < rev_rsi_os) & (close < bb_lower)
        rev_short = (rsi > rev_rsi_ob) & (close > bb_upper)

        # --- Combine by regime ---
        valid = np.zeros(n, dtype=bool)
        valid[warmup:] = True

        long_entries = ((high_atr & trend_long) | (low_atr & rev_long)) & valid
        short_entries = ((high_atr & trend_short) | (low_atr & rev_short)) & valid

        entries = long_entries | short_entries
        direction = long_entries
        exits = np.zeros(n, dtype=bool)

        return entries, exits, direction
