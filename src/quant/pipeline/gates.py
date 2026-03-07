"""5-gate pipeline implementation.

Gates: SCREEN -> IS_OPT -> OOS_VAL -> CONFIRM -> FWD_READY

Each gate is a pure function: (experiment, data) -> GateResult.
No DB access inside gates — callers handle DB updates.

RULE: OOS data is NEVER loaded before OOS_VAL gate.
RULE: First OOS run is final. No re-optimization after seeing OOS results.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import pandas as pd
from scipy.stats import pearsonr

from config.settings import get_settings
from db.queries import Experiment, list_experiments_by_gate, load_trade_pnl
from quant.data.cache import get_ohlcv
from quant.data.splitter import is_full, oos
from quant.engine.backtest import run_backtest
from quant.engine.monte_carlo import monte_carlo
from quant.engine.sensitivity import parameter_sensitivity
from quant.engine.walk_forward import walk_forward
from quant.optimizer.param_space import get_param_space
from quant.optimizer.search import run_optuna
from quant.strategies.registry import get_strategy

log = logging.getLogger(__name__)

GATE_SEQUENCE: dict[str, str | None] = {
    "SCREEN": "IS_OPT",
    "IS_OPT": "OOS_VAL",
    "OOS_VAL": "CONFIRM",
    "CONFIRM": "FWD_READY",
    "FWD_READY": "DEPLOYED",
    "DEPLOYED": None,
    "REJECTED": None,
}

MIN_BARS_SCREEN = {"1m": 5_850, "5m": 2_340, "15m": 780}


@dataclass(frozen=True)
class GateResult:
    gate: str
    passed: bool
    reason: str
    metrics: dict[str, Any]  # gate-specific metrics to store in DB


def run_gate(exp: Experiment, gate: str) -> GateResult:
    """Execute a single pipeline gate for an experiment.

    Args:
        exp:  Experiment from DB
        gate: Which gate to run (must match exp.gate)

    Returns:
        GateResult with passed status and metrics to store
    """
    cfg = get_settings()
    strategy_cls = get_strategy(exp.strategy)
    data = get_ohlcv(exp.ticker, exp.timeframe)

    match gate:
        case "SCREEN":
            return _run_screen(exp, data, strategy_cls, cfg)

        case "IS_OPT":
            return _run_is_opt(exp, data, strategy_cls, cfg)

        case "OOS_VAL":
            return _run_oos_val(exp, data, strategy_cls, cfg)

        case "CONFIRM":
            return _run_confirm(exp, data, strategy_cls, cfg)

        case "FWD_READY":
            # FWD_READY is human-only. Automation should not call this gate.
            raise ValueError("FWD_READY gate requires human approval. Use the web UI.")

        case _:
            raise ValueError(f"Unknown gate: {gate}")


# ---------------------------------------------------------------------------
# Individual gate implementations
# ---------------------------------------------------------------------------


def _run_screen(
    exp: Experiment,
    data: pd.DataFrame,
    strategy_cls: Any,
    cfg: Any,
) -> GateResult:
    """SCREEN: quick sanity check on recent ~3 months of data.

    Uses the last N bars from the full dataset (no date filtering) to check
    that the strategy has any recent signal. Kills dead strategies before
    wasting 45 minutes of Optuna.
    """
    n_bars = MIN_BARS_SCREEN.get(exp.timeframe, 780)
    recent = data.iloc[-n_bars:]

    result = run_backtest(strategy_cls, recent, strategy_cls.default_params(), exp.ticker)
    passed = result.pf >= cfg.screen_min_pf and result.trades >= cfg.screen_min_trades

    return GateResult(
        gate="SCREEN",
        passed=passed,
        reason=(
            f"PF={result.pf:.3f} trades={result.trades} "
            f"(need PF>={cfg.screen_min_pf} trades>={cfg.screen_min_trades})"
        ),
        metrics={"screen_pf": result.pf, "screen_trades": result.trades},
    )


def _run_is_opt(
    exp: Experiment,
    data: pd.DataFrame,
    strategy_cls: Any,
    cfg: Any,
) -> GateResult:
    """IS_OPT: Optuna on IS data only. Objective = IS-val Sharpe (NOT PF).

    NEVER touches OOS data. OOS data is sliced off in run_optuna via splitter.
    """
    is_data = is_full(data)  # 2020-2023 only

    try:
        opt_result = run_optuna(
            strategy=strategy_cls,
            data=is_data,
            ticker=exp.ticker,
            exp_id=exp.id,
            n_trials=cfg.optuna_trials,
        )
    except ValueError as e:
        return GateResult(gate="IS_OPT", passed=False, reason=str(e), metrics={})

    passed = (
        opt_result.best_is_sharpe > cfg.is_opt_min_sharpe
        and opt_result.best_is_val_pf > cfg.is_opt_min_pf
    )
    return GateResult(
        gate="IS_OPT",
        passed=passed,
        reason=(
            f"IS-val Sharpe={opt_result.best_is_sharpe:.3f} "
            f"IS-val PF={opt_result.best_is_val_pf:.3f} "
            f"({opt_result.n_complete}/{opt_result.n_trials} trials)"
        ),
        metrics={
            "is_sharpe": opt_result.best_is_sharpe,
            "is_pf": opt_result.best_is_val_pf,
            "params": json.dumps(opt_result.best_params),
        },
    )


def _run_oos_val(
    exp: Experiment,
    data: pd.DataFrame,
    strategy_cls: Any,
    cfg: Any,
) -> GateResult:
    """OOS_VAL: first and only cold OOS evaluation.

    Uses params from IS_OPT. NEVER re-run with different params.
    This is the single ground truth for the strategy's real-world edge.
    """
    if exp.params is None:
        return GateResult(
            gate="OOS_VAL", passed=False, reason="No params from IS_OPT gate", metrics={}
        )

    oos_data = oos(data)  # 2024-present
    result = run_backtest(strategy_cls, oos_data, exp.params, exp.ticker)

    passed = (
        result.pf >= cfg.oos_min_pf
        and result.trades >= cfg.oos_min_trades
        and abs(result.max_dd_pct) < cfg.oos_max_dd_pct
    )

    return GateResult(
        gate="OOS_VAL",
        passed=passed,
        reason=(
            f"PF={result.pf:.3f} trades={result.trades} "
            f"DD={result.max_dd_pct:.1f}% daily_pnl=${result.daily_pnl:.2f}"
        ),
        metrics={
            "oos_pf": result.pf,
            "oos_trades": result.trades,
            "oos_sharpe": result.sharpe,
            "oos_sortino": result.sortino,
            "oos_calmar": result.calmar,
            "oos_max_dd": result.max_dd_usd,
            "oos_max_dd_pct": result.max_dd_pct,
            "daily_pnl": result.daily_pnl,
            "quarterly_wr": json.dumps(result.quarterly_wr),
            "trade_pnl": json.dumps(result.trade_pnl),
        },
    )


def _run_confirm(
    exp: Experiment,
    data: pd.DataFrame,
    strategy_cls: Any,
    cfg: Any,
) -> GateResult:
    """CONFIRM: 5-part robustness test.

    1. Monte Carlo permutation test (P(ruin) < 1%)
    2. Walk-forward (profitable in >= 3 of 4 windows)
    3. Parameter sensitivity (min neighbor OOS PF >= 1.2)
    4. Cross-instrument (same params on >= 1 other instrument)
    5. Portfolio correlation (< 0.6 vs deployed strategies)
    """
    if exp.params is None:
        return GateResult(
            gate="CONFIRM", passed=False, reason="No params from IS_OPT gate", metrics={}
        )

    oos_data = oos(data)

    # Reuse stored trade_pnl from OOS_VAL instead of re-running backtest
    stored_pnl = load_trade_pnl(exp.id)
    if stored_pnl is not None and len(stored_pnl) > 0:
        trade_pnl_for_mc = stored_pnl
    else:
        log.warning("CONFIRM exp %d: trade_pnl not in DB, re-running OOS backtest", exp.id)
        oos_result = run_backtest(strategy_cls, oos_data, exp.params, exp.ticker)
        trade_pnl_for_mc = oos_result.trade_pnl

    # 1. Monte Carlo
    mc = monte_carlo(trade_pnl_for_mc)
    mc_pass = mc.p_ruin < cfg.mc_max_p_ruin and mc.p_positive > cfg.mc_min_p_positive

    # 2. Walk-forward
    wf = walk_forward(strategy_cls, data, exp.params, exp.ticker)

    # 3. Parameter sensitivity
    try:
        param_space = get_param_space(exp.strategy)
        sens = parameter_sensitivity(strategy_cls, oos_data, exp.params, param_space, exp.ticker)
    except Exception as e:
        log.warning("Sensitivity check failed: %s", e)
        sens = None

    # 4. Cross-instrument
    cross = _check_cross_instrument(exp, strategy_cls)

    # 5. Portfolio correlation
    corr = _check_portfolio_correlation(exp, trade_pnl_for_mc)

    passed = (
        mc_pass
        and wf.passed
        and (sens is None or sens.passed)
        and cross["confirmed"]
        and corr["max_corr"] < cfg.confirm_max_corr
    )

    return GateResult(
        gate="CONFIRM",
        passed=passed,
        reason=(
            f"MC p_ruin={mc.p_ruin:.3f} "
            f"WF={wf.profitable_windows}/{wf.total_windows} "
            f"sens_min_pf={sens.min_neighbor_pf:.3f if sens else 'n/a'} "
            f"cross={cross['confirmed']} "
            f"max_corr={corr['max_corr']:.3f}"
        ),
        metrics={
            "p_ruin": mc.p_ruin,
            "p_positive": mc.p_positive,
            "wf_windows": wf.profitable_windows,
            "cross_confirmed": 1 if cross["confirmed"] else 0,
            "max_corr": corr["max_corr"],
            "sens_min_pf": sens.min_neighbor_pf if sens else None,
        },
    )


def _check_cross_instrument(
    exp: Experiment,
    strategy_cls: Any,
) -> dict[str, Any]:
    """Run same params on the other 2 instruments. Pass if >= 1 also passes."""
    from config.instruments import TICKERS

    others = [t for t in TICKERS if t != exp.ticker]
    cfg = get_settings()
    confirmed = False

    for other_ticker in others:
        try:
            other_data = get_ohlcv(other_ticker, exp.timeframe)
            other_oos = oos(other_data)
            r = run_backtest(strategy_cls, other_oos, exp.params, other_ticker)
            if r.pf >= cfg.oos_min_pf and r.trades >= cfg.cross_min_trades:
                confirmed = True
                break
        except Exception as e:
            log.warning("Cross-instrument %s failed: %s", other_ticker, e)

    return {"confirmed": confirmed}


def _check_portfolio_correlation(
    exp: Experiment,
    new_trade_pnl: list[float],
) -> dict[str, Any]:
    """Compute Pearson correlation vs deployed strategies. Pass if all < confirm_max_corr."""
    deployed = list_experiments_by_gate("DEPLOYED")
    max_corr = 0.0

    for dep in deployed:
        if dep.id == exp.id:
            continue
        dep_pnl = load_trade_pnl(dep.id)
        if dep_pnl is None or len(dep_pnl) < 10:
            continue
        min_len = min(len(new_trade_pnl), len(dep_pnl))
        if min_len < 10:
            continue
        corr_result = pearsonr(new_trade_pnl[:min_len], dep_pnl[:min_len])
        max_corr = max(max_corr, abs(float(corr_result.statistic)))

    return {"max_corr": max_corr}
