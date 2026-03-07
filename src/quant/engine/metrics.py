"""Backtest performance metrics.

All functions operate on raw data (trade PnL lists, daily PnL series, equity curves).
No dependencies on pandas beyond what's needed for computation.

RULE: Never expose magic numbers. All thresholds are in config/settings.py.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BacktestResult:
    """Immutable result of a single backtest run."""
    pf: float
    trades: int
    win_rate: float
    sharpe: float
    sortino: float
    calmar: float
    max_dd_usd: float
    max_dd_pct: float
    daily_pnl: float           # average $/day net of commission
    trade_pnl: list[float]     # individual trade P&Ls for Monte Carlo
    quarterly_wr: dict[str, float]
    total_return_pct: float
    avg_trade_duration: float  # in bars


def pf(trades: list[float]) -> float:
    """Profit factor: sum(wins) / abs(sum(losses)). Returns 0 if no trades."""
    if not trades:
        return 0.0
    wins = sum(t for t in trades if t > 0)
    losses = abs(sum(t for t in trades if t < 0))
    return wins / losses if losses > 0 else (float("inf") if wins > 0 else 0.0)


def win_rate(trades: list[float]) -> float:
    """Fraction of trades that are profitable."""
    if not trades:
        return 0.0
    return sum(1 for t in trades if t > 0) / len(trades)


def sharpe(daily_returns: list[float] | np.ndarray, risk_free: float = 0.0) -> float:
    """Annualized Sharpe ratio on daily P&L series. Returns 0 if insufficient data."""
    arr = np.array(daily_returns, dtype=float)
    if len(arr) < 2:
        return 0.0
    excess = arr - risk_free / 252
    std = np.std(excess, ddof=1)
    if std == 0:
        return 0.0
    return float(np.mean(excess) / std * math.sqrt(252))


def sortino(daily_returns: list[float] | np.ndarray, risk_free: float = 0.0) -> float:
    """Annualized Sortino ratio (penalizes downside volatility only)."""
    arr = np.array(daily_returns, dtype=float)
    if len(arr) < 2:
        return 0.0
    excess = arr - risk_free / 252
    downside = arr[arr < 0]
    if len(downside) == 0:
        return float("inf")
    downside_std = np.std(downside, ddof=1)
    if downside_std == 0:
        return 0.0
    return float(np.mean(excess) / downside_std * math.sqrt(252))


def max_drawdown(equity_curve: list[float] | np.ndarray) -> tuple[float, float]:
    """Return (max_dd_usd, max_dd_pct) from equity curve.

    equity_curve: cumulative P&L series (starts at 0 or initial capital).
    """
    arr = np.array(equity_curve, dtype=float)
    if len(arr) < 2:
        return 0.0, 0.0
    peak = np.maximum.accumulate(arr)
    dd = arr - peak
    max_dd_usd = float(dd.min())
    # pct relative to peak value
    with np.errstate(invalid="ignore", divide="ignore"):
        dd_pct = np.where(peak > 0, dd / peak * 100, 0.0)
    max_dd_pct = float(dd_pct.min())
    return max_dd_usd, max_dd_pct


def calmar(annual_return_pct: float, max_dd_pct_abs: float) -> float:
    """Calmar ratio: annual_return% / |max_dd%|. Target > 3.0."""
    if max_dd_pct_abs == 0:
        return 0.0
    return annual_return_pct / abs(max_dd_pct_abs)


def daily_pnl_usd(
    trade_pnl: list[float],
    oos_start: str,
    oos_end: str,
) -> float:
    """Average net $/day over the OOS period. Commission already baked into trade_pnl."""
    if not trade_pnl:
        return 0.0
    total = sum(trade_pnl)
    days = (pd.Timestamp(oos_end) - pd.Timestamp(oos_start)).days
    trading_days = days * (5 / 7)  # approximate 24/5 trading days
    if trading_days <= 0:
        return 0.0
    return total / trading_days


def quarterly_win_rate(trades_df: pd.DataFrame) -> dict[str, float]:
    """Win rate per quarter.

    trades_df must have columns: ['exit_time', 'pnl']
    Returns e.g. {'2024Q1': 0.82, '2024Q2': 0.79, ...}
    """
    if trades_df.empty:
        return {}
    df = trades_df.copy()
    df["exit_time"] = pd.to_datetime(df["exit_time"])
    df["quarter"] = df["exit_time"].dt.to_period("Q").astype(str)
    result: dict[str, float] = {}
    for q, group in df.groupby("quarter"):
        if len(group) > 0:
            result[str(q)] = float((group["pnl"] > 0).sum() / len(group))
    return result


def max_consecutive_losses(trade_pnl: list[float]) -> int:
    """Count longest streak of consecutive losing trades."""
    max_streak = 0
    current = 0
    for t in trade_pnl:
        if t < 0:
            current += 1
            max_streak = max(max_streak, current)
        else:
            current = 0
    return max_streak
