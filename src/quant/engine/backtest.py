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

from config.instruments import CONTRACT_MULT
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

    # Strategy returns either 3 or 4 arrays. Level strategies return entry_prices.
    result = strategy.generate(data, params)
    if len(result) == 4:
        entries, exits, direction, entry_prices = result
    else:
        entries, exits, direction = result
        entry_prices = None

    if len(entries) != len(data) or len(exits) != len(data) or len(direction) != len(data):
        raise ValueError(
            f"Strategy output length mismatch: entries={len(entries)}, exits={len(exits)}, "
            f"direction={len(direction)}, data={len(data)}"
        )
    if entry_prices is not None and len(entry_prices) != len(data):
        raise ValueError(f"entry_prices length {len(entry_prices)} != data length {len(data)}")

    # -- Session, DOW, and time-exit filters --
    from quant.data.session import make_dow_mask, make_session_mask, make_time_exit_mask

    cfg = get_settings()
    idx = pd.DatetimeIndex(data.index)

    if cfg.time_exit and not cfg.session_filter:
        log.warning(
            "time_exit=True without session_filter=True: entries outside session hours "
            "will be force-closed at %d:00 ET",
            cfg.exit_time_et,
        )

    if cfg.session_filter:
        session_mask = make_session_mask(idx, cfg.session_start_et, cfg.session_end_et)
        entries = entries & session_mask

    if cfg.dow_filter:
        allowed = tuple(int(d) for d in cfg.dow_allowed_days.split(","))
        dow_mask = make_dow_mask(idx, allowed_days=allowed)
        entries = entries & dow_mask

    # -- Time-based forced exit: close positions at exit_time_et --
    if cfg.time_exit:
        time_exit_mask = make_time_exit_mask(idx, cfg.exit_time_et)
        exits = exits | time_exit_mask

    # Separate long and short signals
    long_entries = entries & direction
    short_entries = entries & ~direction

    # -- Build execution price array for stop-order fill simulation --
    # Level strategies return entry_prices: the price at which a stop order fills.
    # We use vectorbt's `price` param to set fill price, and `stop_entry_price`
    # = FillPrice so TP/SL are calculated relative to the actual fill price.
    if entry_prices is not None:
        from vectorbt.portfolio.enums import StopEntryPrice

        exec_price = np.full(len(data), np.inf, dtype=np.float64)  # inf = use close
        entry_mask = long_entries | short_entries
        # Only use level price where we actually have entries AND level is not NaN
        valid_entry = entry_mask & ~np.isnan(entry_prices)
        exec_price[valid_entry] = entry_prices[valid_entry]
        # Guard: remove entries with no valid fill price (still inf)
        invalid_fill = entry_mask & np.isinf(exec_price)
        if invalid_fill.any():
            log.warning("Removing %d entries with no valid fill price", invalid_fill.sum())
            long_entries = long_entries & ~invalid_fill
            short_entries = short_entries & ~invalid_fill

        exec_price_series: pd.Series | None = pd.Series(exec_price, index=data.index)
        stop_entry_price = StopEntryPrice.FillPrice
    else:
        exec_price_series = None
        stop_entry_price = None

    mult = CONTRACT_MULT.get(ticker, 1.0)
    commission_per_side = cfg.commission_rt / 2  # vectorbt charges per side

    median_price = data["close"].median()
    if np.isnan(median_price) or median_price == 0:
        raise ValueError(
            f"Cannot compute fees: median close price is {median_price}. "
            "Data may be corrupt (all NaN or zero prices)."
        )

    pf_kwargs: dict[str, Any] = dict(
        entries=long_entries,
        exits=exits,
        short_entries=short_entries,
        short_exits=exits,
        tp_stop=params.get("tp_pct", 1.0) / 100,
        sl_stop=params.get("sl_pct", 2.8) / 100,
        fees=commission_per_side / median_price,
        freq="1min",  # vectorbt needs freq for time-based metrics
        size=1.0,
        size_type="amount",
    )

    if exec_price_series is not None:
        pf_kwargs["price"] = exec_price_series
    if stop_entry_price is not None:
        pf_kwargs["stop_entry_price"] = stop_entry_price

    pf_vbt = vbt.Portfolio.from_signals(
        data["close"],
        **pf_kwargs,
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
    # Calculate trading period in years for annualized return
    if len(data) > 1:
        trading_days = (data.index[-1] - data.index[0]).days
        years = max(trading_days / 365.25, 1 / 365.25)  # at least 1 day
    else:
        years = 1.0

    # Return-on-drawdown for Calmar calculation
    return_on_dd_pct = (sum(trade_pnl) / max(abs(dd_usd), 1)) * 100 if dd_usd != 0 else 0.0
    annual_ret_pct = return_on_dd_pct / years
    cal = calmar(annual_ret_pct, abs(dd_pct))
    d_pnl = daily_pnl_usd(trade_pnl, oos_start, oos_end)

    # Quarterly win rate
    if "Exit Timestamp" in trades.columns:
        qwr = quarterly_win_rate(
            pd.DataFrame({"exit_time": trades["Exit Timestamp"], "pnl": raw_pnl})
        )
    else:
        qwr = {}

    # Total return as percentage of initial notional value
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
        pf=0.0,
        trades=0,
        win_rate=0.0,
        sharpe=0.0,
        sortino=0.0,
        calmar=0.0,
        max_dd_usd=0.0,
        max_dd_pct=0.0,
        daily_pnl=0.0,
        trade_pnl=[],
        quarterly_wr={},
        total_return_pct=0.0,
        avg_trade_duration=0.0,
    )


def _equity_to_daily(equity_series: pd.Series) -> list[float]:
    """Convert equity series to daily P&L list."""
    daily = equity_series.resample("1D").last().dropna()
    return daily.diff().dropna().tolist()
