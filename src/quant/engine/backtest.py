"""vectorbt backtest runner.

Wraps vectorbt Portfolio.from_signals() to produce a typed BacktestResult.
TP/SL are enforced as pct-based stops on entry price.

RULE: All backtest results must use BacktestResult (from metrics.py). No raw dicts.
RULE: commission_rt already includes both sides (round-trip). Never double-count.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from config.instruments import COMMISSION_RT, CONTRACT_MULT
from config.settings import get_settings
from quant.engine.metrics import (
    BacktestResult,
    calmar,
    daily_pnl_usd,
    max_drawdown,
    pf,
    quarterly_win_rate,
    sharpe,
    sortino,
    win_rate,
    max_consecutive_losses,
)

log = logging.getLogger(__name__)

try:
    import vectorbt as vbt
    _VBT_AVAILABLE = True
except ImportError:
    _VBT_AVAILABLE = False
    log.warning("vectorbt not installed -- backtest.run_backtest() will raise")


def run_backtest(
    strategy: Any,
    data: pd.DataFrame,
    params: dict[str, Any],
    ticker: str = "MNQ",
) -> BacktestResult:
    """Run a single backtest using vectorbt.

    Args:
        strategy:  Strategy class (from quant.strategies.*)
        data:      OHLCV DataFrame (pre-sliced to desired date range)
        params:    Strategy hyperparameters
        ticker:    Instrument name for CONTRACT_MULT lookup

    Returns:
        BacktestResult with all metrics pre-computed
    """
    if not _VBT_AVAILABLE:
        raise RuntimeError("vectorbt is required for backtesting. Run: uv sync")

    entries, exits, direction = strategy.generate(data, params)

    # Separate long and short signals
    long_entries = entries & direction
    short_entries = entries & ~direction

    mult = CONTRACT_MULT.get(ticker, 1.0)
    commission_per_side = COMMISSION_RT / 2  # vectorbt charges per side

    pf_vbt = vbt.Portfolio.from_signals(
        data["close"],
        entries=long_entries,
        exits=exits,
        short_entries=short_entries,
        short_exits=exits,
        tp_stop=params.get("tp_pct", 1.0) / 100,
        sl_stop=params.get("sl_pct", 2.8) / 100,
        fees=commission_per_side / data["close"].median(),  # as fraction of median price
        freq="1min",  # vectorbt needs freq for time-based metrics
        size=1.0,
        size_type="amount",
    )

    trades = pf_vbt.trades.records_readable
    n_trades = len(trades)

    if n_trades == 0:
        return _empty_result()

    # Convert vectorbt trade PnL to USD
    raw_pnl = trades["PnL"].values * mult
    trade_pnl = raw_pnl.tolist()

    equity = (pf_vbt.value() * mult).values.tolist()
    daily = _equity_to_daily(pf_vbt.value() * mult)
    oos_start = str(data.index[0].date())
    oos_end = str(data.index[-1].date())

    dd_usd, dd_pct = max_drawdown(equity)
    win_r = win_rate(trade_pnl)
    pf_val = pf(trade_pnl)
    sh = sharpe(daily)
    so = sortino(daily)
    annual_ret_pct = (sum(trade_pnl) / max(abs(dd_usd), 1)) * 100 if dd_usd != 0 else 0.0
    cal = calmar(annual_ret_pct, abs(dd_pct))
    d_pnl = daily_pnl_usd(trade_pnl, oos_start, oos_end)

    # Quarterly win rate
    if "Exit Timestamp" in trades.columns:
        qwr = quarterly_win_rate(
            pd.DataFrame({"exit_time": trades["Exit Timestamp"], "pnl": raw_pnl})
        )
    else:
        qwr = {}

    total_ret_pct = sum(trade_pnl) / (data["close"].iloc[0] * mult) * 100

    return BacktestResult(
        pf=pf_val,
        trades=n_trades,
        win_rate=win_r,
        sharpe=sh,
        sortino=so,
        calmar=cal,
        max_dd_usd=dd_usd,
        max_dd_pct=dd_pct,
        daily_pnl=d_pnl,
        trade_pnl=trade_pnl,
        quarterly_wr=qwr,
        total_return_pct=total_ret_pct,
        avg_trade_duration=0.0,  # TODO: compute from trade entry/exit timestamps
    )


def _empty_result() -> BacktestResult:
    return BacktestResult(
        pf=0.0, trades=0, win_rate=0.0, sharpe=0.0, sortino=0.0,
        calmar=0.0, max_dd_usd=0.0, max_dd_pct=0.0, daily_pnl=0.0,
        trade_pnl=[], quarterly_wr={}, total_return_pct=0.0, avg_trade_duration=0.0,
    )


def _equity_to_daily(equity_series: pd.Series) -> list[float]:
    """Convert equity series to daily P&L list."""
    daily = equity_series.resample("1D").last().dropna()
    return daily.diff().dropna().tolist()
