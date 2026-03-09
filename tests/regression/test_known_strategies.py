"""Regression tests for the backtest engine using ema_rsi as reference strategy.

PURPOSE: Verify the engine is not broken. Tests that ema_rsi on correct data
produces a profitable result (PF > 1.0) with sufficient trade count.

IMPORTANT: These tests do NOT assert specific OOS PF values from prior research.
The V2 pipeline has not run yet. Once it does, update KNOWN_OOS_PF below with
the values produced by the first clean run. Until then, only sanity checks run.

If any test in this file fails, STOP and investigate — the engine may be broken.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

EMA_RSI_PROVEN_PARAMS = {
    "ema_fast": 5,
    "ema_slow": 21,
    "rsi_period": 9,
    "rsi_os": 35,
    "rsi_ob": 65,
    "tp_pct": 1.0,
    "sl_pct": 2.8,
}

# OOS PF targets from V1 research (2024-01-01 to present).
# These are REFERENCE values only — V2 has not confirmed them yet.
# Once V2's first clean pipeline run completes, verify these match within 5%.
KNOWN_OOS_PF = {
    ("ema_rsi", "MNQ", "15m"): 2.405,
    ("ema_rsi", "MES", "15m"): 6.132,
    ("ema_rsi", "MGC", "15m"): 2.604,
}
TOLERANCE = 0.05  # 5%

# Skip if real data not available (CI without CSVs)
DATA_DIR = Path(os.environ.get("DATA_DIR", "./data/raw"))
requires_real_data = pytest.mark.skipif(
    not (DATA_DIR / "MNQ_15m.csv").exists(),
    reason="Real CSV data not available. Place CSVs in data/raw/ first.",
)


@requires_real_data
@pytest.mark.parametrize("ticker", ["MNQ", "MES", "MGC"])
def test_ema_rsi_engine_sanity(ticker: str) -> None:
    """ema_rsi must produce >= 50 OOS trades and PF > 1.0 on real data.

    This catches a broken engine (wrong signals, wrong commission, wrong dates).
    Does NOT assert specific PF values — those are established by the pipeline.
    """
    from quant.data.cache import get_ohlcv
    from quant.data.splitter import oos
    from quant.engine.backtest import run_backtest
    from quant.strategies.registry import get_strategy

    strategy_cls = get_strategy("ema_rsi")
    data = get_ohlcv(ticker, "15m", DATA_DIR)
    oos_data = oos(data)

    result = run_backtest(strategy_cls, oos_data, EMA_RSI_PROVEN_PARAMS, ticker)

    assert result.trades >= 50, (
        f"ema_rsi {ticker} 15m: only {result.trades} OOS trades. "
        f"Expected >= 50. Engine or data may be broken."
    )
    assert result.pf > 1.0, (
        f"ema_rsi {ticker} 15m: OOS PF={result.pf:.3f} < 1.0. Engine or data may be broken."
    )


@requires_real_data
@pytest.mark.parametrize("ticker", ["MNQ", "MES", "MGC"])
@pytest.mark.slow
def test_ema_rsi_matches_v1_reference(ticker: str) -> None:
    """Once V2 data is confirmed correct, OOS PF must be within 5% of V1 reference.

    SKIP this test until the first clean V2 pipeline run has been completed
    and the V1 reference values in KNOWN_OOS_PF above have been verified.
    Run with: pytest -m slow tests/regression/
    """
    from quant.data.cache import get_ohlcv
    from quant.data.splitter import oos
    from quant.engine.backtest import run_backtest
    from quant.strategies.registry import get_strategy

    strategy_cls = get_strategy("ema_rsi")
    data = get_ohlcv(ticker, "15m", DATA_DIR)
    oos_data = oos(data)

    result = run_backtest(strategy_cls, oos_data, EMA_RSI_PROVEN_PARAMS, ticker)

    known_pf = KNOWN_OOS_PF[("ema_rsi", ticker, "15m")]
    tolerance_pf = known_pf * TOLERANCE

    assert result.trades >= 100, (
        f"ema_rsi {ticker} 15m: only {result.trades} OOS trades (need >= 100). "
        f"Data may be incomplete."
    )
    assert abs(result.pf - known_pf) <= tolerance_pf, (
        f"ema_rsi {ticker} 15m: OOS PF={result.pf:.3f} "
        f"expected {known_pf:.3f} +/-{tolerance_pf:.3f}. "
        f"Either data differs from V1 or the engine has a regression."
    )
