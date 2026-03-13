"""Tests for directional filter module."""

from __future__ import annotations

import numpy as np

from quant.strategies.filters import (
    bb_filter,
    consensus_filter,
    ema_trend_filter,
    kc_filter,
    macd_filter,
)


def _trending_up(n: int = 500, start: float = 18000.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Create strongly trending-up price data."""
    rng = np.random.default_rng(42)
    close = start + np.cumsum(np.abs(rng.normal(0.5, 0.3, n)))
    high = close + rng.uniform(1, 5, n)
    low = close - rng.uniform(1, 5, n)
    return high, low, close


def _trending_down(
    n: int = 500,
    start: float = 20000.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Create strongly trending-down price data."""
    rng = np.random.default_rng(42)
    close = start - np.cumsum(np.abs(rng.normal(0.5, 0.3, n)))
    high = close + rng.uniform(1, 5, n)
    low = close - rng.uniform(1, 5, n)
    return high, low, close


def _flat(n: int = 500, price: float = 18000.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Create flat/choppy price data."""
    rng = np.random.default_rng(42)
    close = price + rng.normal(0, 2, n)
    high = close + rng.uniform(1, 3, n)
    low = close - rng.uniform(1, 3, n)
    return high, low, close


class TestMacdFilter:
    def test_output_shape_and_dtype(self) -> None:
        _, _, close = _trending_up()
        result = macd_filter(close)
        assert result.shape == close.shape
        assert result.dtype == np.int8

    def test_values_in_valid_range(self) -> None:
        _, _, close = _trending_up()
        result = macd_filter(close)
        assert set(np.unique(result)).issubset({-1, 0, 1})

    def test_bullish_in_uptrend(self) -> None:
        _, _, close = _trending_up()
        result = macd_filter(close)
        # In a strong uptrend, the later bars should be mostly bullish
        assert (result[-100:] == 1).sum() > 50

    def test_bearish_in_downtrend(self) -> None:
        _, _, close = _trending_down()
        result = macd_filter(close)
        assert (result[-100:] == -1).sum() > 50

    def test_warmup_is_zero(self) -> None:
        _, _, close = _trending_up()
        result = macd_filter(close, fast=5, slow=13, signal=5)
        # First slow + signal bars should be 0
        assert np.all(result[:18] == 0)

    def test_short_data(self) -> None:
        close = np.array([100.0, 101.0, 102.0])
        result = macd_filter(close)
        assert np.all(result == 0)

    def test_empty_data(self) -> None:
        close = np.array([], dtype=float)
        result = macd_filter(close)
        assert len(result) == 0


class TestBbFilter:
    def test_output_shape(self) -> None:
        _, _, close = _trending_up()
        result = bb_filter(close)
        assert result.shape == close.shape

    def test_bullish_in_strong_uptrend(self) -> None:
        _, _, close = _trending_up()
        result = bb_filter(close)
        assert (result == 1).sum() > 0

    def test_warmup_is_zero(self) -> None:
        _, _, close = _trending_up()
        result = bb_filter(close, period=20)
        assert np.all(result[:20] == 0)


class TestKcFilter:
    def test_output_shape(self) -> None:
        high, low, close = _trending_up()
        result = kc_filter(high, low, close)
        assert result.shape == close.shape

    def test_bullish_in_strong_uptrend(self) -> None:
        # KC with Wilder ATR produces wide channels (~1.5 * period * mean_TR).
        # Use a very steep trend and smaller multiplier to ensure breakout.
        rng = np.random.default_rng(42)
        n = 500
        close = 18000.0 + np.cumsum(np.abs(rng.normal(15.0, 2.0, n)))
        high = close + rng.uniform(0.5, 1.5, n)
        low = close - rng.uniform(0.5, 1.5, n)
        result = kc_filter(high, low, close, multiplier=0.5)
        assert (result == 1).sum() > 0

    def test_warmup_is_zero(self) -> None:
        high, low, close = _trending_up()
        result = kc_filter(high, low, close, ema_period=20, atr_period=14)
        assert np.all(result[:20] == 0)


class TestEmaTrendFilter:
    def test_output_shape(self) -> None:
        _, _, close = _trending_up()
        result = ema_trend_filter(close)
        assert result.shape == close.shape

    def test_bullish_in_uptrend(self) -> None:
        _, _, close = _trending_up()
        result = ema_trend_filter(close)
        assert (result[-100:] == 1).sum() > 50

    def test_bearish_in_downtrend(self) -> None:
        _, _, close = _trending_down()
        result = ema_trend_filter(close)
        assert (result[-100:] == -1).sum() > 50


class TestConsensusFilter:
    def test_output_shape(self) -> None:
        high, low, close = _trending_up()
        result = consensus_filter(high, low, close)
        assert result.shape == close.shape

    def test_consensus_is_subset_of_individual(self) -> None:
        """Consensus should have fewer or equal signals than either individual filter."""
        high, low, close = _trending_up()
        macd = macd_filter(close)
        kc = kc_filter(high, low, close)
        cons = consensus_filter(high, low, close)

        # Consensus bullish count <= min(macd bullish, kc bullish)
        assert (cons == 1).sum() <= min((macd == 1).sum(), (kc == 1).sum())
        assert (cons == -1).sum() <= min((macd == -1).sum(), (kc == -1).sum())

    def test_flat_market_mostly_neutral(self) -> None:
        high, low, close = _flat()
        result = consensus_filter(high, low, close)
        neutral_pct = (result == 0).sum() / len(result)
        assert neutral_pct > 0.7
