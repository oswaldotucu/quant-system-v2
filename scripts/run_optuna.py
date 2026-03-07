#!/usr/bin/env python3
"""Standalone Optuna runner — no DB required.

Usage:
    uv run python scripts/run_optuna.py [--strategy ema_rsi] [--tickers MNQ MES MGC]
                                        [--tf 15m] [--trials 500]
                                        [--min-is-trades 10] [--min-is-pf 0.0]

Runs IS optimization (2020-2023) and immediately evaluates OOS (2024-present).
Results are cross-validated: MNQ best params applied unchanged to MES and MGC.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any

# src/ layout
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import optuna

optuna.logging.set_verbosity(optuna.logging.WARNING)
logging.basicConfig(level=logging.WARNING)

# Force unbuffered output so progress is visible when piped
sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]

DATA_DIR = Path(__file__).parent.parent / "data" / "raw"


def build_local_objective(
    strategy_cls: Any,
    is_data: Any,
    ticker: str,
    min_is_train_trades: int,
    min_is_train_pf: float,
    min_is_val_trades: int,
    min_is_val_pf: float,
) -> Any:
    """Build an Optuna objective with configurable prune thresholds.

    Objective: IS-val Sharpe (2023 data). Never touches OOS.
    """
    from quant.data.splitter import is_train, is_val
    from quant.engine.backtest import run_backtest
    from quant.optimizer.param_space import get_param_space

    train_data = is_train(is_data)
    val_data = is_val(is_data)
    param_space = get_param_space(strategy_cls.name)

    def objective(trial: optuna.Trial) -> float:
        params: dict[str, Any] = {}
        for name, spec in param_space.items():
            if spec["type"] == "int":
                params[name] = trial.suggest_int(name, spec["low"], spec["high"],
                                                  step=spec.get("step", 1))
            else:
                params[name] = trial.suggest_float(name, spec["low"], spec["high"],
                                                   step=spec.get("step"))

        # IS-train: fast reject clearly broken params
        tr = run_backtest(strategy_cls, train_data, params, ticker)
        if tr.trades < min_is_train_trades or tr.pf < min_is_train_pf:
            return 0.0

        # IS-val: objective
        vr = run_backtest(strategy_cls, val_data, params, ticker)
        if vr.trades < min_is_val_trades or vr.pf < min_is_val_pf:
            return 0.0

        trial.set_user_attr("is_train_pf", tr.pf)
        trial.set_user_attr("is_train_trades", tr.trades)
        trial.set_user_attr("is_val_pf", vr.pf)
        trial.set_user_attr("is_val_trades", vr.trades)
        trial.set_user_attr("is_val_wr", vr.win_rate)

        # Return raw Sharpe (can be negative) so Optuna learns gradient direction.
        # Positive = profitable, negative = losing but Optuna still improves toward 0.
        return vr.sharpe

    return objective


def run_study(
    strategy_cls: Any,
    ticker: str,
    timeframe: str,
    n_trials: int,
    min_is_train_trades: int,
    min_is_train_pf: float,
    min_is_val_trades: int,
    min_is_val_pf: float,
) -> tuple[dict, float, float, float]:
    """Return (best_params, is_val_sharpe, is_train_pf, is_val_pf)."""
    from quant.data.loader import load_ohlcv
    from quant.data.splitter import is_full, is_train, is_val
    from quant.engine.backtest import run_backtest

    full_data = load_ohlcv(ticker, timeframe, DATA_DIR)
    is_data = is_full(full_data)   # IS_TRAIN + IS_VAL only, NO OOS

    train_data = is_train(is_data)
    val_data = is_val(is_data)

    print(f"  IS_TRAIN: {train_data.index[0].date()} to {train_data.index[-1].date()}"
          f"  ({len(train_data):,} bars)")
    print(f"  IS_VAL:   {val_data.index[0].date()} to {val_data.index[-1].date()}"
          f"  ({len(val_data):,} bars)")
    print(f"  Prune: IS_TRAIN trades>={min_is_train_trades} PF>={min_is_train_pf:.1f}"
          f"  |  IS_VAL trades>={min_is_val_trades} PF>={min_is_val_pf:.1f}")

    objective = build_local_objective(
        strategy_cls, is_data, ticker,
        min_is_train_trades, min_is_train_pf,
        min_is_val_trades, min_is_val_pf,
    )

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42),
        pruner=optuna.pruners.MedianPruner(n_warmup_steps=30),
    )

    best_so_far = float("-inf")
    no_improve = 0
    early_stop_n = max(150, n_trials // 3)

    def callback(study: optuna.Study, trial: optuna.FrozenTrial) -> None:
        nonlocal best_so_far, no_improve
        val = trial.value or 0.0
        if val > best_so_far:
            best_so_far = val
            no_improve = 0
        else:
            no_improve += 1
        if no_improve >= early_stop_n:
            study.stop()

    t0 = time.time()
    study.optimize(objective, n_trials=n_trials, callbacks=[callback],
                   show_progress_bar=True)
    elapsed = time.time() - t0

    complete = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    positive = [t for t in complete if (t.value or float("-inf")) > 0]

    print(f"\n  Done in {elapsed:.0f}s | {len(study.trials)} trials"
          f" | {len(complete)} complete | {len(positive)} profitable (sharpe > 0)"
          f" | early_stop={no_improve >= early_stop_n}")

    if not complete:
        print("  WARNING: 0 complete trials.")
        return {}, 0.0, 0.0, 0.0

    # Report best even if Sharpe is negative — still useful for understanding the space
    best_params = study.best_params
    best_is_sharpe = study.best_value or 0.0
    if best_is_sharpe <= 0:
        print(f"  NOTE: Best IS-val Sharpe is {best_is_sharpe:.3f} (negative) — "
              f"strategy may not have IS edge. OOS result shown for reference only.")

    # Re-run best params to get detailed IS metrics
    tr = run_backtest(strategy_cls, train_data, best_params, ticker)
    vr = run_backtest(strategy_cls, val_data, best_params, ticker)

    return best_params, best_is_sharpe, tr.pf, vr.pf


def run_oos(
    strategy_cls: Any,
    ticker: str,
    timeframe: str,
    params: dict,
) -> Any:
    from quant.data.loader import load_ohlcv
    from quant.data.splitter import oos
    from quant.engine.backtest import run_backtest
    full_data = load_ohlcv(ticker, timeframe, DATA_DIR)
    return run_backtest(strategy_cls, oos(full_data), params, ticker)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", default="ema_rsi")
    parser.add_argument("--tickers", nargs="+", default=["MNQ", "MES", "MGC"])
    parser.add_argument("--tf", default="15m")
    parser.add_argument("--trials", type=int, default=500)
    parser.add_argument("--min-is-train-trades", type=int, default=10,
                        help="Min trades in IS_TRAIN to pass prune (default: 10)")
    parser.add_argument("--min-is-train-pf", type=float, default=0.8,
                        help="Min PF in IS_TRAIN to pass prune (default: 0.8)")
    parser.add_argument("--min-is-val-trades", type=int, default=5,
                        help="Min trades in IS_VAL to pass prune (default: 5)")
    parser.add_argument("--min-is-val-pf", type=float, default=0.0,
                        help="Min PF in IS_VAL (default: 0.0 — objective handles it)")
    args = parser.parse_args()

    from quant.strategies.registry import get_strategy
    strategy_cls = get_strategy(args.strategy)

    print(f"\n{'='*65}")
    print(f"Optuna: {args.strategy} | {args.tickers} | {args.tf} | {args.trials} trials")
    print(f"IS_TRAIN: 2020-2022 | IS_VAL: 2023 | OOS: 2024-present")
    print(f"{'='*65}")

    all_results: dict[str, tuple] = {}

    for ticker in args.tickers:
        print(f"\n[{ticker}] Running IS optimization...")
        best_params, is_sharpe, is_train_pf, is_val_pf = run_study(
            strategy_cls, ticker, args.tf, args.trials,
            args.min_is_train_trades, args.min_is_train_pf,
            args.min_is_val_trades, args.min_is_val_pf,
        )
        all_results[ticker] = (best_params, is_sharpe, is_train_pf, is_val_pf)

        if best_params:
            print(f"\n  Best params:")
            for k, v in best_params.items():
                print(f"    {k}: {v}")
            print(f"  IS_TRAIN PF: {is_train_pf:.3f}"
                  f"  |  IS_VAL PF: {is_val_pf:.3f}"
                  f"  |  IS_VAL Sharpe: {is_sharpe:.3f}")

    # OOS evaluation — per-ticker best params
    print(f"\n\n{'='*65}")
    print("OOS RESULTS (2024-present) — per-ticker best params applied")
    print(f"{'='*65}")
    print(f"{'Ticker':<6} {'Trades':>7} {'OOS PF':>8} {'WR':>7} "
          f"{'$/day':>8} {'Sharpe':>7} {'MaxDD':>10}")
    print("-" * 60)

    for ticker in args.tickers:
        best_params, is_sharpe, is_train_pf, is_val_pf = all_results[ticker]
        if not best_params:
            print(f"{ticker:<6}  NO VALID PARAMS FOUND")
            continue
        r = run_oos(strategy_cls, ticker, args.tf, best_params)
        print(f"{ticker:<6} {r.trades:>7} {r.pf:>8.3f} {r.win_rate:>7.1%}"
              f" {r.daily_pnl:>8.2f} {r.sharpe:>7.3f} {r.max_dd_usd:>10.0f}")

    # Cross-validation: apply anchor ticker's best params to all others
    anchor = args.tickers[0]
    if len(args.tickers) > 1 and all_results[anchor][0]:
        anchor_params = all_results[anchor][0]
        others = [t for t in args.tickers if t != anchor]
        print(f"\n\n{'='*65}")
        print(f"CROSS-VALIDATION — {anchor} best params applied unchanged to {others}")
        print(f"{'='*65}")
        print(f"{'Ticker':<6} {'Trades':>7} {'OOS PF':>8} {'WR':>7} {'$/day':>8}")
        print("-" * 42)
        for ticker in [anchor] + others:
            r = run_oos(strategy_cls, ticker, args.tf, anchor_params)
            print(f"{ticker:<6} {r.trades:>7} {r.pf:>8.3f} {r.win_rate:>7.1%}"
                  f" {r.daily_pnl:>8.2f}")

    print("\n")
    print("Threshold for a VALID strategy: OOS PF >= 1.5 | trades >= 100")
    print("Threshold for a STRONG strategy: OOS PF >= 2.0 | trades >= 150")
    print()


if __name__ == "__main__":
    main()
