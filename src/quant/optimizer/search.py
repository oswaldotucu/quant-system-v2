"""Optuna study runner.

Runs IS_OPT gate: optimizes strategy params on IS data, records trials to DB.
Returns best params (by IS-val Sharpe) for OOS_VAL gate.

RULE: OOS data is NEVER used here. Only is_train() + is_val() slices.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import optuna
import pandas as pd

from config.settings import get_settings
from db.queries import insert_trial
from quant.optimizer.objective import build_objective

log = logging.getLogger(__name__)

# Silence Optuna's noisy INFO logs
optuna.logging.set_verbosity(optuna.logging.WARNING)


@dataclass
class OptimizationResult:
    best_params: dict[str, Any]
    best_is_sharpe: float
    best_is_train_pf: float
    best_is_val_pf: float
    n_trials: int
    n_complete: int


def run_optuna(
    strategy: Any,
    data: pd.DataFrame,
    ticker: str,
    exp_id: int,
    n_trials: int | None = None,
    early_stop: int | None = None,
) -> OptimizationResult:
    """Run Optuna optimization for IS_OPT gate.

    Args:
        strategy:    Strategy class
        data:        Full OHLCV data (IS period — no OOS)
        ticker:      For CONTRACT_MULT lookup
        exp_id:      DB experiment ID (trials are stored here)
        n_trials:    Override settings.optuna_trials
        early_stop:  Stop if no improvement after N consecutive trials

    Returns:
        OptimizationResult with best_params and diagnostics
    """
    cfg = get_settings()
    n_trials = n_trials or cfg.optuna_trials
    early_stop = early_stop or cfg.optuna_early_stop

    objective = build_objective(strategy, data, ticker, exp_id)

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42),
        pruner=optuna.pruners.MedianPruner(n_warmup_steps=20),
    )

    trials_without_improvement = 0
    best_so_far = float("-inf")

    def callback(study: optuna.Study, trial: optuna.FrozenTrial) -> None:
        nonlocal trials_without_improvement, best_so_far

        if trial.value is not None and trial.value > best_so_far:
            best_so_far = trial.value
            trials_without_improvement = 0
        else:
            trials_without_improvement += 1

        # Progress logging every 50 trials
        trial_num = trial.number + 1
        if trial_num % 50 == 0 or trial_num == n_trials:
            n_pruned = len([t for t in study.trials if t.state == optuna.trial.TrialState.PRUNED])
            n_done = len([t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE])
            log.info(
                "Optuna exp %d: trial %d/%d complete=%d pruned=%d best=%.3f",
                exp_id,
                trial_num,
                n_trials,
                n_done,
                n_pruned,
                best_so_far if best_so_far > float("-inf") else 0.0,
            )

        # Store trial to DB
        try:
            insert_trial(
                exp_id=exp_id,
                trial_num=trial.number,
                params=trial.params,
                is_sharpe=trial.value or 0.0,
                is_train_pf=trial.user_attrs.get("is_train_pf", 0.0),
                is_val_pf=trial.user_attrs.get("is_val_pf", 0.0),
                state="complete" if trial.state == optuna.trial.TrialState.COMPLETE else "pruned",
            )
        except Exception as e:
            log.warning("Failed to store trial %d: %s", trial.number, e)

        # Early stopping
        if trials_without_improvement >= early_stop:
            study.stop()
            log.info("Early stop: no improvement in %d trials", early_stop)

    study.optimize(objective, n_trials=n_trials, callbacks=[callback])

    if study.best_trial is None or study.best_value is None or study.best_value <= 0:
        raise ValueError(
            f"No valid trials found for {strategy.name}/{ticker}. Strategy has no IS edge."
        )

    return OptimizationResult(
        best_params=study.best_params,
        best_is_sharpe=study.best_value,
        best_is_train_pf=study.best_trial.user_attrs.get("is_train_pf", 0.0),
        best_is_val_pf=study.best_trial.user_attrs.get("is_val_pf", 0.0),
        n_trials=len(study.trials),
        n_complete=len([t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]),
    )
