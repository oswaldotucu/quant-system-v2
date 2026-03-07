"""Unit tests for engine/monte_carlo.py."""

from __future__ import annotations

from quant.engine.monte_carlo import monte_carlo


def test_all_winning_trades_low_ruin() -> None:
    """All positive trades -> P(ruin) should be ~0."""
    trades = [100.0] * 100
    result = monte_carlo(trades, n=1_000)
    assert result.p_ruin < 0.01
    assert result.p_positive > 0.99


def test_all_losing_trades_high_ruin() -> None:
    """All negative trades -> P(ruin) should be ~1.

    Use initial_capital=1_000 so 30% ruin = -$300.
    100 trades of -$100 each will always hit that within 3 trades.
    """
    trades = [-100.0] * 100
    result = monte_carlo(trades, n=1_000, initial_capital=1_000)
    assert result.p_ruin > 0.95
    assert result.p_positive < 0.05


def test_returns_correct_structure() -> None:
    """Structure check: all fields present and in valid ranges."""
    # Use varied trades so shuffles produce different sequence profiles
    trades = [100, -50, 200, -30, 150, -80, 300, -20, 50, -100]
    result = monte_carlo(trades, n=500)
    assert result.n_simulations == 500
    assert 0.0 <= result.p_ruin <= 1.0
    assert 0.0 <= result.p_positive <= 1.0
    # Total sum is same for all shuffles; percentiles differ by path (for ruin check)
    assert result.pct_5 <= result.median_return <= result.pct_95
