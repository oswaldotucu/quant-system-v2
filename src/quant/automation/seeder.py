"""Experiment seeder — creates DB rows for new strategy/ticker/timeframe combinations.

Called from the web UI (Strategies page) or programmatically.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from config.instruments import TICKERS, TIMEFRAMES
from db.queries import (
    get_strategy,
    list_strategies,
    seed_experiment,
    upsert_strategy,
    Experiment,
)
from quant.optimizer.param_space import get_param_space

log = logging.getLogger(__name__)


@dataclass
class SeedResult:
    strategy: str
    ticker: str
    timeframe: str
    exp_id: int
    status: str  # 'seeded' | 'already_exists'


def seed(
    strategy_name: str,
    tickers: list[str],
    timeframes: list[str],
    priority: int = 0,
) -> list[SeedResult]:
    """Seed experiments for a strategy across tickers and timeframes.

    Args:
        strategy_name: must be in STRATEGY_REGISTRY
        tickers:       list of ticker symbols (e.g. ['MNQ', 'MES'])
        timeframes:    list of timeframes (e.g. ['15m'])
        priority:      higher = runs first in automation

    Returns:
        List of SeedResult for each ticker/timeframe combo
    """
    from quant.strategies.registry import get_strategy as get_strategy_cls

    # Validate strategy exists
    strategy_cls = get_strategy_cls(strategy_name)
    param_space = get_param_space(strategy_name)

    # Ensure strategy is registered in DB
    strat = get_strategy(strategy_name)
    if strat is None:
        upsert_strategy(
            name=strategy_name,
            family=strategy_cls.family,
            description=None,
            param_space=param_space,
        )

    results: list[SeedResult] = []

    for ticker in tickers:
        if ticker not in TICKERS:
            log.warning("Unknown ticker %s -- skipping", ticker)
            continue

        for tf in timeframes:
            if tf not in TIMEFRAMES:
                log.warning("Unknown timeframe %s -- skipping", tf)
                continue

            try:
                exp_id = seed_experiment(strategy_name, ticker, tf, priority)
                log.info("Seeded %s/%s/%s (exp_id=%d)", strategy_name, ticker, tf, exp_id)
                results.append(SeedResult(
                    strategy=strategy_name, ticker=ticker, timeframe=tf,
                    exp_id=exp_id, status="seeded",
                ))
            except Exception as e:
                if "UNIQUE constraint" in str(e):
                    results.append(SeedResult(
                        strategy=strategy_name, ticker=ticker, timeframe=tf,
                        exp_id=-1, status="already_exists",
                    ))
                else:
                    log.error("Seed failed for %s/%s/%s: %s", strategy_name, ticker, tf, e)
                    raise

    return results
