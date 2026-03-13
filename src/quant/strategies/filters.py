"""Directional filters for level-based breakout strategies.

Each filter returns an int8 array: +1 (bullish), -1 (bearish), 0 (neutral).
Filters are used ALONGSIDE level breakout entries to confirm direction.

From Sentinel research:
- MACD(5,13,5) is the strongest single filter (73% of portfolio PnL)
- Keltner Channel and Bollinger Band filters provide diversification
- EMA trend filter is simpler but effective
- Consensus filter (MACD + KC agree) has highest precision but fewer signals
"""

from __future__ import annotations

import logging

import numpy as np

from quant.strategies.indicators import atr_wilder, ema, rolling_std, sma

log = logging.getLogger(__name__)


def macd_filter(
    close: np.ndarray,
    fast: int = 5,
    slow: int = 13,
    signal: int = 5,
) -> np.ndarray:
    """MACD directional filter.

    Bullish (+1): MACD line > signal line AND MACD > 0
    Bearish (-1): MACD line < signal line AND MACD < 0
    Neutral (0): otherwise (MACD and signal disagree, or MACD near zero)

    Args:
        close: close price array
        fast: fast EMA period (default 5 from Sentinel)
        slow: slow EMA period (default 13 from Sentinel)
        signal: signal EMA period (default 5 from Sentinel)

    Returns:
        np.ndarray of int8: +1, -1, or 0 per bar
    """
    n = len(close)
    result = np.zeros(n, dtype=np.int8)

    if n < slow + signal:
        return result

    fast_ema = ema(close, fast)
    slow_ema = ema(close, slow)
    macd_line = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)

    bullish = (macd_line > signal_line) & (macd_line > 0)
    bearish = (macd_line < signal_line) & (macd_line < 0)

    result[bullish] = 1
    result[bearish] = -1

    # Warmup guard
    warmup = slow + signal
    result[:warmup] = 0

    return result


def bb_filter(
    close: np.ndarray,
    period: int = 20,
    num_std: float = 2.0,
) -> np.ndarray:
    """Bollinger Band directional filter.

    Bullish (+1): close > upper band (strong upward momentum)
    Bearish (-1): close < lower band (strong downward momentum)
    Neutral (0): close within bands

    Args:
        close: close price array
        period: SMA period
        num_std: number of standard deviations

    Returns:
        np.ndarray of int8: +1, -1, or 0 per bar
    """
    n = len(close)
    result = np.zeros(n, dtype=np.int8)

    if n < period:
        return result

    mid = sma(close, period)
    std = rolling_std(close, period)
    upper = mid + num_std * std
    lower = mid - num_std * std

    result[close > upper] = 1
    result[close < lower] = -1

    # Warmup
    result[:period] = 0

    return result


def kc_filter(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    ema_period: int = 20,
    atr_period: int = 14,
    multiplier: float = 1.5,
) -> np.ndarray:
    """Keltner Channel directional filter.

    Bullish (+1): close > upper KC (EMA + multiplier * ATR)
    Bearish (-1): close < lower KC (EMA - multiplier * ATR)
    Neutral (0): close within channel

    Args:
        high: high price array
        low: low price array
        close: close price array
        ema_period: EMA period for midline
        atr_period: ATR period for channel width
        multiplier: ATR multiplier

    Returns:
        np.ndarray of int8: +1, -1, or 0 per bar
    """
    n = len(close)
    result = np.zeros(n, dtype=np.int8)

    warmup = max(ema_period, atr_period)
    if n < warmup:
        return result

    mid = ema(close, ema_period)
    atr = atr_wilder(high, low, close, atr_period)
    upper = mid + multiplier * atr
    lower = mid - multiplier * atr

    result[close > upper] = 1
    result[close < lower] = -1
    result[:warmup] = 0

    return result


def ema_trend_filter(
    close: np.ndarray,
    period: int = 50,
) -> np.ndarray:
    """EMA trend filter.

    Bullish (+1): close > EMA AND EMA is rising (current > previous)
    Bearish (-1): close < EMA AND EMA is falling
    Neutral (0): EMA flat or close near EMA

    Args:
        close: close price array
        period: EMA period (default 50)

    Returns:
        np.ndarray of int8: +1, -1, or 0 per bar
    """
    n = len(close)
    result = np.zeros(n, dtype=np.int8)

    if n < period + 1:
        return result

    ema_vals = ema(close, period)
    ema_rising = np.zeros(n, dtype=bool)
    ema_falling = np.zeros(n, dtype=bool)
    ema_rising[1:] = ema_vals[1:] > ema_vals[:-1]
    ema_falling[1:] = ema_vals[1:] < ema_vals[:-1]

    bullish = (close > ema_vals) & ema_rising
    bearish = (close < ema_vals) & ema_falling

    result[bullish] = 1
    result[bearish] = -1
    result[:period] = 0

    return result


def consensus_filter(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    macd_fast: int = 5,
    macd_slow: int = 13,
    macd_signal: int = 5,
    kc_ema_period: int = 20,
    kc_atr_period: int = 14,
    kc_multiplier: float = 1.5,
) -> np.ndarray:
    """Consensus filter: MACD + KC must agree on direction.

    Bullish (+1): BOTH MACD and KC are bullish
    Bearish (-1): BOTH MACD and KC are bearish
    Neutral (0): disagree or either is neutral

    Highest precision but fewest signals.

    Args:
        high: high price array
        low: low price array
        close: close price array
        macd_fast: MACD fast EMA period
        macd_slow: MACD slow EMA period
        macd_signal: MACD signal EMA period
        kc_ema_period: Keltner Channel EMA period
        kc_atr_period: Keltner Channel ATR period
        kc_multiplier: Keltner Channel ATR multiplier

    Returns:
        np.ndarray of int8: +1, -1, or 0 per bar
    """
    macd = macd_filter(close, macd_fast, macd_slow, macd_signal)
    kc = kc_filter(high, low, close, kc_ema_period, kc_atr_period, kc_multiplier)

    n = len(close)
    result = np.zeros(n, dtype=np.int8)

    result[(macd == 1) & (kc == 1)] = 1
    result[(macd == -1) & (kc == -1)] = -1

    return result
