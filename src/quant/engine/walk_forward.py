"""Walk-forward validation.

Tests strategy robustness across 4 anchored time windows.
Params are NOT re-optimized per window — same params tested cold.

A robust strategy is profitable in >= 3 of 4 windows (pass_threshold).
If it only works in 1-2 windows, the edge is regime-specific, not durable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import pandas as pd

from quant.engine.backtest import run_backtest

log = logging.getLogger(__name__)

# Anchored walk-forward windows: (is_start, is_end, oos_start, oos_end)
WF_WINDOWS = [
    ("2020-01-01", "2020-12-31", "2021-01-01", "2021-12-31"),
    ("2020-01-01", "2021-12-31", "2022-01-01", "2022-12-31"),
    ("2020-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
    ("2020-01-01", "2023-12-31", "2024-01-01", "2025-12-31"),
]

MIN_TRADES_PER_WINDOW = 20  # window must have at least this many trades to count


@dataclass(frozen=True)
class WFWindow:
    oos_start: str
    oos_end: str
    pf: float
    trades: int
    profitable: bool


@dataclass(frozen=True)
class WFResult:
    windows: list[WFWindow]
    profitable_windows: int
    total_windows: int
    passed: bool  # profitable_windows >= pass_threshold


def walk_forward(
    strategy: Any,
    data: pd.DataFrame,
    params: dict[str, Any],
    ticker: str = "MNQ",
    pass_threshold: int = 3,
) -> WFResult:
    """Run walk-forward validation across 4 fixed windows.

    Args:
        strategy:        Strategy class
        data:            Full OHLCV data (must cover 2020-2025)
        params:          Best params from IS_OPT (NOT re-optimized per window)
        ticker:          For CONTRACT_MULT lookup
        pass_threshold:  Number of profitable windows required to pass

    Returns:
        WFResult with per-window metrics and pass/fail status
    """
    window_results: list[WFWindow] = []

    for _is_start, _is_end, oos_start, oos_end in WF_WINDOWS:
        oos_slice = data.loc[oos_start:oos_end]

        if len(oos_slice) < 50:
            log.warning(
                "Walk-forward window %s-%s has only %d bars -- skipping",
                oos_start,
                oos_end,
                len(oos_slice),
            )
            continue

        try:
            result = run_backtest(strategy, oos_slice, params, ticker)
            profitable = result.pf > 1.0 and result.trades >= MIN_TRADES_PER_WINDOW
            window_results.append(
                WFWindow(
                    oos_start=oos_start,
                    oos_end=oos_end,
                    pf=result.pf,
                    trades=result.trades,
                    profitable=profitable,
                )
            )
        except Exception as e:
            log.error("Walk-forward window %s-%s failed: %s", oos_start, oos_end, e)
            window_results.append(
                WFWindow(
                    oos_start=oos_start,
                    oos_end=oos_end,
                    pf=0.0,
                    trades=0,
                    profitable=False,
                )
            )

    profitable_count = sum(1 for w in window_results if w.profitable)
    return WFResult(
        windows=window_results,
        profitable_windows=profitable_count,
        total_windows=len(window_results),
        passed=profitable_count >= pass_threshold,
    )
