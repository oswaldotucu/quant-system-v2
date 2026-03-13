"""Tests for correlation-aware portfolio optimizer."""

from __future__ import annotations

import numpy as np
import pytest

from quant.portfolio.optimizer import (
    StrategyCandidate,
    _correlation,
    _daily_equity_from_trades,
    _max_drawdown_pct,
    _monte_carlo_portfolio,
    _sharpe_ratio,
    optimize_portfolio,
)


def _make_candidate(
    exp_id: int,
    name: str = "test",
    n_trades: int = 50,
    avg_pnl: float = 10.0,
    sharpe: float = 2.0,
    seed: int = 42,
) -> StrategyCandidate:
    """Create a test candidate with random trade PnL."""
    rng = np.random.default_rng(seed)
    trade_pnl = (rng.normal(avg_pnl, abs(avg_pnl) * 2, n_trades)).tolist()
    daily_pnl = sum(trade_pnl) / 252
    return StrategyCandidate(
        exp_id=exp_id,
        name=name,
        trade_pnl=trade_pnl,
        daily_pnl=daily_pnl,
        trades=n_trades,
        sharpe=sharpe,
    )


class TestHelperFunctions:
    def test_daily_equity_shape(self) -> None:
        daily = _daily_equity_from_trades([10, -5, 20, -3], n_days=10)
        assert len(daily) == 10

    def test_daily_equity_preserves_total(self) -> None:
        trades = [10.0, -5.0, 20.0, -3.0]
        daily = _daily_equity_from_trades(trades, n_days=10)
        assert daily.sum() == pytest.approx(sum(trades), abs=0.01)

    def test_daily_equity_empty(self) -> None:
        daily = _daily_equity_from_trades([], n_days=10)
        assert len(daily) == 10
        assert daily.sum() == 0.0

    def test_sharpe_positive(self) -> None:
        rng = np.random.default_rng(42)
        daily = rng.normal(10.0, 5.0, 252)  # positive mean, some variance
        s = _sharpe_ratio(daily)
        assert s > 0

    def test_sharpe_zero_std(self) -> None:
        daily = np.zeros(252)
        assert _sharpe_ratio(daily) == 0.0

    def test_sharpe_empty(self) -> None:
        daily = np.array([])
        assert _sharpe_ratio(daily) == 0.0

    def test_correlation_identical(self) -> None:
        a = np.random.default_rng(42).normal(0, 1, 100)
        assert _correlation(a, a) == pytest.approx(1.0, abs=0.001)

    def test_correlation_uncorrelated(self) -> None:
        rng = np.random.default_rng(42)
        a = rng.normal(0, 1, 10000)
        b = rng.normal(0, 1, 10000)
        corr = _correlation(a, b)
        assert abs(corr) < 0.1

    def test_correlation_mismatched_length(self) -> None:
        a = np.array([1.0, 2.0, 3.0])
        b = np.array([1.0, 2.0])
        assert _correlation(a, b) == 0.0

    def test_correlation_zero_std(self) -> None:
        a = np.ones(10)
        b = np.random.default_rng(42).normal(0, 1, 10)
        assert _correlation(a, b) == 1.0  # zero-variance = no diversification value

    def test_max_drawdown_no_drawdown(self) -> None:
        daily = np.array([10.0] * 10)
        dd = _max_drawdown_pct(daily)
        assert dd == 0.0

    def test_max_drawdown_with_loss(self) -> None:
        daily = np.array([100.0, -50.0, -50.0, 10.0])
        dd = _max_drawdown_pct(daily)
        assert dd > 0

    def test_max_drawdown_empty(self) -> None:
        daily = np.array([])
        assert _max_drawdown_pct(daily) == 0.0

    def test_monte_carlo_positive_portfolio(self) -> None:
        rng = np.random.default_rng(42)
        daily = rng.normal(10.0, 3.0, 252)  # strongly positive mean
        p_pos, p_ruin = _monte_carlo_portfolio(daily, n_simulations=100)
        assert p_pos > 0.9

    def test_monte_carlo_empty(self) -> None:
        daily = np.array([])
        p_pos, p_ruin = _monte_carlo_portfolio(daily)
        assert p_pos == 0.0
        assert p_ruin == 1.0


class TestOptimizePortfolio:
    def test_empty_candidates(self) -> None:
        result = optimize_portfolio([])
        assert result.n_strategies == 0
        assert result.portfolio_sharpe == 0.0
        assert result.mc_p_ruin == 1.0

    def test_single_viable_candidate(self) -> None:
        c = _make_candidate(exp_id=1, name="strat1", n_trades=50, avg_pnl=10.0)
        result = optimize_portfolio([c], min_dpd=0.1, min_trades=10)
        assert result.n_strategies == 1
        assert result.selected_ids == [1]
        assert result.selected_names == ["strat1"]

    def test_filters_by_min_trades(self) -> None:
        c = _make_candidate(exp_id=1, n_trades=5, avg_pnl=10.0)
        result = optimize_portfolio([c], min_trades=20)
        assert result.n_strategies == 0

    def test_filters_by_min_dpd(self) -> None:
        c = _make_candidate(exp_id=1, n_trades=50, avg_pnl=-100.0)
        result = optimize_portfolio([c], min_dpd=5.0)
        assert result.n_strategies == 0

    def test_correlated_strategies_rejected(self) -> None:
        """Two identical strategies should not both be selected."""
        c1 = _make_candidate(exp_id=1, name="s1", seed=42, sharpe=3.0)
        c2 = _make_candidate(exp_id=2, name="s2", seed=42, sharpe=2.9)  # same PnL
        result = optimize_portfolio([c1, c2], max_corr=0.85, min_dpd=0.0, min_trades=1)
        assert result.n_strategies == 1  # one rejected due to correlation

    def test_uncorrelated_strategies_accepted(self) -> None:
        """Two uncorrelated strategies should both be selected."""
        c1 = _make_candidate(exp_id=1, name="s1", seed=42, sharpe=3.0)
        c2 = _make_candidate(exp_id=2, name="s2", seed=99, sharpe=2.5)
        result = optimize_portfolio([c1, c2], max_corr=0.85, min_dpd=0.0, min_trades=1)
        assert result.n_strategies == 2

    def test_portfolio_sharpe_positive(self) -> None:
        """Portfolio of uncorrelated strategies should have positive Sharpe."""
        candidates = [
            _make_candidate(exp_id=i, name=f"s{i}", seed=i * 10, sharpe=2.0 + i * 0.1)
            for i in range(5)
        ]
        result = optimize_portfolio(candidates, max_corr=0.95, min_dpd=0.0, min_trades=1)
        if result.n_strategies > 1:
            assert result.portfolio_sharpe > 0

    def test_result_has_correlation_matrix(self) -> None:
        c1 = _make_candidate(exp_id=1, seed=42, sharpe=3.0)
        c2 = _make_candidate(exp_id=2, seed=99, sharpe=2.5)
        result = optimize_portfolio([c1, c2], max_corr=0.95, min_dpd=0.0, min_trades=1)
        if result.n_strategies == 2:
            assert len(result.correlation_matrix) == 2
            assert len(result.correlation_matrix[0]) == 2
            # Diagonal should be 1.0
            assert result.correlation_matrix[0][0] == pytest.approx(1.0)
            assert result.correlation_matrix[1][1] == pytest.approx(1.0)

    def test_monte_carlo_fields_populated(self) -> None:
        c = _make_candidate(exp_id=1, n_trades=100, avg_pnl=20.0, sharpe=3.0)
        result = optimize_portfolio([c], min_dpd=0.0, min_trades=1)
        assert 0.0 <= result.mc_p_positive <= 1.0
        assert 0.0 <= result.mc_p_ruin <= 1.0

    def test_greedy_selects_best_sharpe_first(self) -> None:
        """The first selected strategy should be the one with highest Sharpe."""
        c1 = _make_candidate(exp_id=1, name="low", seed=42, sharpe=1.0)
        c2 = _make_candidate(exp_id=2, name="high", seed=99, sharpe=5.0)
        result = optimize_portfolio([c1, c2], max_corr=0.99, min_dpd=0.0, min_trades=1)
        assert result.selected_ids[0] == 2  # highest Sharpe first
