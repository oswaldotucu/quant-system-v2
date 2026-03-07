"""Optuna objective function.

Objective: IS-val Sharpe (2023 data). NOT IS PF.
Rationale: IS PF is anti-correlated with OOS PF (proven over 155K runs in V1).

Pruning:
- IS-train prune: PF < 1.1 OR trades < 15 -> return 0.0 (fast rejection)
- IS-val prune:   PF < 1.2 OR trades < 10 OR win_rate < 30% -> return 0.0

RULE: OOS data is NEVER touched in this function. Only IS_TRAIN and IS_VAL slices.
"""

from __future__ import annotations

import logging
from typing import Any

import optuna
import pandas as pd

from config.settings import get_settings
from quant.data.splitter import is_train, is_val, validate_no_oos_leak
from quant.engine.backtest import run_backtest
from quant.optimizer.param_space import get_param_space

log = logging.getLogger(__name__)

# IS-train prune thresholds
IS_TRAIN_MIN_PF = 1.1
IS_TRAIN_MIN_TRADES = 15

# IS-val prune thresholds
IS_VAL_MIN_PF = 1.2
IS_VAL_MIN_TRADES = 10
IS_VAL_MIN_WIN_RATE = 0.30


def build_objective(
    strategy: Any,
    data: pd.DataFrame,
    ticker: str,
    exp_id: int,
) -> Any:
    """Return a closure that Optuna calls on each trial.

    Args:
        strategy:  Strategy class
        data:      Full OHLCV data (IS period only — OOS must NOT be in here)
        ticker:    For CONTRACT_MULT lookup
        exp_id:    Experiment ID (for storing trial results to DB)

    Returns:
        objective function: (trial) -> float (IS-val Sharpe, 0 if pruned)
    """
    # Guard: verify no OOS data leaked in
    validate_no_oos_leak(data, context=f"IS_OPT exp_id={exp_id}")

    train_data = is_train(data)
    val_data = is_val(data)
    param_space = get_param_space(strategy.name)

    def objective(trial: optuna.Trial) -> float:
        params = _suggest_params(trial, param_space)

        # -- IS-train: fast prune -----------------------------------------------
        try:
            train_result = run_backtest(strategy, train_data, params, ticker)
        except Exception as e:
            log.debug("IS-train backtest failed: %s", e)
            return 0.0

        trial.set_user_attr("is_train_pf", train_result.pf)

        if train_result.pf < IS_TRAIN_MIN_PF or train_result.trades < IS_TRAIN_MIN_TRADES:
            return 0.0

        # -- IS-val: objective computation --------------------------------------
        try:
            val_result = run_backtest(strategy, val_data, params, ticker)
        except Exception as e:
            log.debug("IS-val backtest failed: %s", e)
            return 0.0

        trial.set_user_attr("is_val_pf", val_result.pf)

        if (val_result.pf < IS_VAL_MIN_PF
                or val_result.trades < IS_VAL_MIN_TRADES
                or val_result.win_rate < IS_VAL_MIN_WIN_RATE):
            return 0.0

        return val_result.sharpe  # <-- THE OBJECTIVE: IS-val Sharpe, NOT PF

    return objective


def _suggest_params(trial: optuna.Trial, param_space: dict[str, Any]) -> dict[str, Any]:
    """Suggest parameter values from Optuna trial."""
    params: dict[str, Any] = {}
    for name, spec in param_space.items():
        if spec["type"] == "int":
            params[name] = trial.suggest_int(
                name, spec["low"], spec["high"], step=spec.get("step", 1)
            )
        elif spec["type"] == "float":
            params[name] = trial.suggest_float(
                name, spec["low"], spec["high"], step=spec.get("step", None)
            )
    return params
