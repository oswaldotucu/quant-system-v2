"""Monte Carlo permutation test.

Shuffles trade PnL list N times to compute:
- P(ruin): probability of hitting -30% drawdown (default threshold)
- P(positive): probability of positive total return after 1 year

A real edge should have P(ruin) < 1% and P(positive) > 95%.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)

RUIN_THRESHOLD = -0.30  # -30% drawdown = ruin event (as fraction of initial capital)


@dataclass(frozen=True)
class MCResult:
    p_ruin: float  # P(cumsum hits RUIN_THRESHOLD at any point in simulation)
    p_positive: float  # P(total sum > 0 at end of simulation)
    n_simulations: int
    median_return: float
    pct_5: float  # 5th percentile return (downside scenario)
    pct_95: float  # 95th percentile return (upside scenario)


def monte_carlo(
    trade_pnl: list[float],
    n: int = 10_000,
    initial_capital: float = 100_000.0,
) -> MCResult:
    """Run Monte Carlo permutation test on a trade PnL list.

    Args:
        trade_pnl:       List of individual trade P&Ls (net of commission)
        n:               Number of simulations
        initial_capital: Starting capital for ruin calculation

    Returns:
        MCResult with P(ruin), P(positive), and percentile returns
    """
    if len(trade_pnl) == 0:
        return MCResult(p_ruin=1.0, p_positive=0.0, n_simulations=0,
                        median_return=0.0, pct_5=0.0, pct_95=0.0)

    if len(trade_pnl) < 10:
        log.warning("Monte Carlo: only %d trades — results unreliable", len(trade_pnl))

    trades = np.array(trade_pnl, dtype=float)
    ruin_level = initial_capital * RUIN_THRESHOLD

    ruin_count = 0
    positive_count = 0
    total_returns: list[float] = []

    rng = np.random.default_rng(seed=42)

    for _ in range(n):
        shuffled = rng.permutation(trades)
        equity = np.cumsum(shuffled)
        total = float(equity[-1])
        min_equity = float(equity.min())

        total_returns.append(total)
        if min_equity <= ruin_level:
            ruin_count += 1
        if total > 0:
            positive_count += 1

    returns_arr = np.array(total_returns)
    return MCResult(
        p_ruin=ruin_count / n,
        p_positive=positive_count / n,
        n_simulations=n,
        median_return=float(np.median(returns_arr)),
        pct_5=float(np.percentile(returns_arr, 5)),
        pct_95=float(np.percentile(returns_arr, 95)),
    )
