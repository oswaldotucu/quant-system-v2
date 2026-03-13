"""Correlation-aware greedy portfolio optimizer.

Selects an uncorrelated subset of strategies that maximizes portfolio Sharpe.
Follows Sentinel's proven methodology:
- Greedy forward selection: add strategy with highest marginal Sharpe improvement
- Correlation filter: reject if max pairwise correlation > threshold
- Minimum viability: each strategy must have min daily PnL and min trades
- Monte Carlo bootstrap: validate final portfolio's robustness

From Sentinel (walk-forward validated, $4909/day MNQ portfolio, Sharpe 11.23):
- max_corr = 0.85
- min_dpd = $5 (minimum daily P&L)
- min_trades = 20
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)


@dataclass
class StrategyCandidate:
    """A strategy candidate for portfolio selection."""

    exp_id: int
    name: str
    trade_pnl: list[float]
    daily_pnl: float
    trades: int
    sharpe: float


@dataclass
class PortfolioResult:
    """Result of portfolio optimization."""

    selected_ids: list[int]
    selected_names: list[str]
    portfolio_sharpe: float
    portfolio_daily_pnl: float
    portfolio_max_dd_pct: float
    n_strategies: int
    correlation_matrix: list[list[float]]  # pairwise correlations of selected
    mc_p_positive: float  # Monte Carlo probability of positive terminal value
    mc_p_ruin: float  # Monte Carlo probability of ruin


def _daily_equity_from_trades(trade_pnl: list[float], n_days: int = 252) -> np.ndarray:
    """Convert trade PnL list to approximate daily equity curve.

    Distributes trades evenly across n_days trading days.
    Returns daily P&L array.
    """
    n = len(trade_pnl)
    if n == 0:
        return np.zeros(n_days)

    daily = np.zeros(n_days)
    # Distribute trades across days proportionally
    trades_per_day = max(n / n_days, 0.001)
    for i, pnl in enumerate(trade_pnl):
        day_idx = min(int(i / trades_per_day), n_days - 1)
        daily[day_idx] += pnl

    return daily


def _sharpe_ratio(daily_pnl: np.ndarray) -> float:
    """Annualized Sharpe ratio from daily P&L array."""
    if len(daily_pnl) < 2:
        return 0.0
    mean = daily_pnl.mean()
    std = daily_pnl.std(ddof=1)
    if std == 0:
        if mean > 0:
            return 99.0  # effectively infinite Sharpe, capped for numerical stability
        elif mean < 0:
            return -99.0
        return 0.0
    return float(mean / std * np.sqrt(252))


def _max_drawdown_pct(daily_pnl: np.ndarray) -> float:
    """Maximum drawdown as percentage of peak equity."""
    equity = np.cumsum(daily_pnl)
    if len(equity) == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    dd = peak - equity
    peak_max = peak.max()
    if peak_max == 0:
        return 0.0
    return float(dd.max() / max(peak_max, 1.0) * 100)


def _correlation(a: np.ndarray, b: np.ndarray) -> float:
    """Pearson correlation between two daily P&L arrays."""
    if len(a) != len(b) or len(a) < 2:
        return 0.0
    std_a = a.std()
    std_b = b.std()
    if std_a == 0 or std_b == 0:
        return 1.0  # zero-variance = no diversification value
    return float(np.corrcoef(a, b)[0, 1])


def _monte_carlo_portfolio(
    daily_pnl: np.ndarray,
    n_simulations: int = 1000,
    ruin_threshold: float = 0.30,
) -> tuple[float, float]:
    """Monte Carlo bootstrap on portfolio daily P&L.

    Shuffles daily P&L to generate random equity paths.

    Returns:
        (p_positive, p_ruin) -- probability of positive terminal value,
        probability of ruin (drawdown > ruin_threshold of peak).
    """
    rng = np.random.default_rng(42)
    n_days = len(daily_pnl)

    if n_days == 0:
        return 0.0, 1.0

    positive_count = 0
    ruin_count = 0

    for _ in range(n_simulations):
        shuffled = rng.permutation(daily_pnl)
        equity = np.cumsum(shuffled)

        # Terminal value check
        if equity[-1] > 0:
            positive_count += 1

        # Ruin check: max drawdown > threshold of peak equity
        peak = np.maximum.accumulate(equity)
        dd = peak - equity
        peak_max = float(peak.max())
        initial_capital = peak_max if peak_max != 0 else 1.0
        if dd.max() > ruin_threshold * initial_capital:
            ruin_count += 1

    return positive_count / n_simulations, ruin_count / n_simulations


def optimize_portfolio(
    candidates: list[StrategyCandidate],
    max_corr: float = 0.85,
    min_dpd: float = 5.0,
    min_trades: int = 20,
    n_days: int = 252,
) -> PortfolioResult:
    """Greedy forward selection maximizing portfolio Sharpe.

    Algorithm:
    1. Filter candidates by min_dpd and min_trades
    2. Sort by individual Sharpe (descending)
    3. Greedily add strategy if:
       a) Max pairwise correlation with existing portfolio < max_corr
       b) Adding it improves portfolio Sharpe
    4. Run Monte Carlo on final portfolio

    Args:
        candidates: List of strategy candidates with trade_pnl
        max_corr: Maximum allowed pairwise correlation (default 0.85)
        min_dpd: Minimum daily P&L in USD (default $5)
        min_trades: Minimum number of trades (default 20)
        n_days: Number of trading days for equity curve approximation

    Returns:
        PortfolioResult with selected strategies and portfolio metrics
    """
    # Step 1: Filter by viability thresholds
    viable = [c for c in candidates if c.daily_pnl >= min_dpd and c.trades >= min_trades]

    if not viable:
        log.warning(
            "No viable candidates (min_dpd=%.1f, min_trades=%d)",
            min_dpd,
            min_trades,
        )
        return _empty_portfolio_result()

    log.info(
        "Portfolio optimizer: %d/%d candidates pass viability filter",
        len(viable),
        len(candidates),
    )

    # Step 2: Compute daily equity curves
    daily_curves: dict[int, np.ndarray] = {}
    for c in viable:
        daily_curves[c.exp_id] = _daily_equity_from_trades(c.trade_pnl, n_days)

    # Sort by individual Sharpe (best first)
    viable.sort(key=lambda c: c.sharpe, reverse=True)

    # Step 3: Greedy forward selection
    selected: list[StrategyCandidate] = []
    selected_daily: list[np.ndarray] = []

    for candidate in viable:
        curve = daily_curves[candidate.exp_id]

        # Check correlation with all already-selected strategies
        too_correlated = False
        for existing_curve in selected_daily:
            corr = _correlation(curve, existing_curve)
            if abs(corr) > max_corr:
                too_correlated = True
                log.debug(
                    "Rejected %s (exp %d): corr=%.3f > %.3f",
                    candidate.name,
                    candidate.exp_id,
                    corr,
                    max_corr,
                )
                break

        if too_correlated:
            continue

        # Check if adding improves portfolio Sharpe
        test_portfolio: np.ndarray
        if selected_daily:
            test_portfolio = np.sum(selected_daily + [curve], axis=0)
        else:
            test_portfolio = curve
        new_sharpe = _sharpe_ratio(test_portfolio)

        if selected:
            current_portfolio = np.sum(selected_daily, axis=0)
            current_sharpe = _sharpe_ratio(current_portfolio)
            if new_sharpe <= current_sharpe:
                log.debug(
                    "Rejected %s: portfolio Sharpe would decrease (%.3f -> %.3f)",
                    candidate.name,
                    current_sharpe,
                    new_sharpe,
                )
                continue

        selected.append(candidate)
        selected_daily.append(curve)
        log.info(
            "Selected %s (exp %d): Sharpe=%.3f, portfolio Sharpe=%.3f",
            candidate.name,
            candidate.exp_id,
            candidate.sharpe,
            new_sharpe,
        )

    if not selected:
        log.warning("No strategies selected after correlation filter")
        return _empty_portfolio_result()

    # Step 4: Compute portfolio metrics
    portfolio_daily = np.sum(selected_daily, axis=0)
    portfolio_sharpe = _sharpe_ratio(portfolio_daily)
    portfolio_dpd = float(portfolio_daily.mean())
    portfolio_dd = _max_drawdown_pct(portfolio_daily)

    # Correlation matrix
    n_sel = len(selected)
    corr_matrix = np.eye(n_sel)
    for i in range(n_sel):
        for j in range(i + 1, n_sel):
            c = _correlation(selected_daily[i], selected_daily[j])
            corr_matrix[i, j] = c
            corr_matrix[j, i] = c

    # Monte Carlo validation
    mc_p_positive, mc_p_ruin = _monte_carlo_portfolio(portfolio_daily)

    log.info(
        "Portfolio: %d strategies, Sharpe=%.3f, daily=%.1f, DD=%.1f%%, MC p_pos=%.3f",
        len(selected),
        portfolio_sharpe,
        portfolio_dpd,
        portfolio_dd,
        mc_p_positive,
    )

    return PortfolioResult(
        selected_ids=[s.exp_id for s in selected],
        selected_names=[s.name for s in selected],
        portfolio_sharpe=portfolio_sharpe,
        portfolio_daily_pnl=portfolio_dpd,
        portfolio_max_dd_pct=portfolio_dd,
        n_strategies=len(selected),
        correlation_matrix=corr_matrix.tolist(),
        mc_p_positive=mc_p_positive,
        mc_p_ruin=mc_p_ruin,
    )


def _empty_portfolio_result() -> PortfolioResult:
    return PortfolioResult(
        selected_ids=[],
        selected_names=[],
        portfolio_sharpe=0.0,
        portfolio_daily_pnl=0.0,
        portfolio_max_dd_pct=0.0,
        n_strategies=0,
        correlation_matrix=[],
        mc_p_positive=0.0,
        mc_p_ruin=1.0,
    )
