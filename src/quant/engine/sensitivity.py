"""Parameter sensitivity analysis.

If nudging one parameter by 1 step collapses OOS PF, the strategy is curve-fit.
A robust strategy maintains OOS PF >= 1.2 across all 1-step neighbors.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import pandas as pd

from quant.engine.backtest import run_backtest

log = logging.getLogger(__name__)

FRAGILE_PF_THRESHOLD = 1.2  # neighbor OOS PF must stay above this


@dataclass(frozen=True)
class NeighborResult:
    param_name: str
    delta: int | float  # +step or -step
    params: dict[str, Any]
    pf: float


@dataclass(frozen=True)
class SensResult:
    base_pf: float
    min_neighbor_pf: float
    max_pf_drop: float
    neighbors: list[NeighborResult]
    passed: bool  # min_neighbor_pf >= FRAGILE_PF_THRESHOLD


def parameter_sensitivity(
    strategy: Any,
    oos_data: pd.DataFrame,
    best_params: dict[str, Any],
    param_space: dict[str, Any],
    ticker: str = "MNQ",
) -> SensResult:
    """Test OOS PF at +/-1 step for each parameter.

    Args:
        strategy:    Strategy class
        oos_data:    OOS slice of OHLCV data
        best_params: Best params from IS_OPT
        param_space: Optuna param space dict (needs 'low', 'high', 'step' per param)
        ticker:      For CONTRACT_MULT lookup

    Returns:
        SensResult with per-neighbor PF and min_neighbor_pf
    """
    base_result = run_backtest(strategy, oos_data, best_params, ticker)
    base_pf = base_result.pf

    neighbors: list[NeighborResult] = []

    for param_name, space in param_space.items():
        if param_name not in best_params:
            continue
        step = space.get("step", 1)
        low = space.get("low", None)
        high = space.get("high", None)

        for delta in [-step, +step]:
            new_val = best_params[param_name] + delta
            if low is not None and new_val < low:
                continue
            if high is not None and new_val > high:
                continue

            nudged = {**best_params, param_name: new_val}
            try:
                r = run_backtest(strategy, oos_data, nudged, ticker)
                neighbors.append(
                    NeighborResult(
                        param_name=param_name,
                        delta=delta,
                        params=nudged,
                        pf=r.pf,
                    )
                )
            except Exception as e:
                log.error("Sensitivity %s=%s failed: %s", param_name, new_val, e)
                neighbors.append(
                    NeighborResult(param_name=param_name, delta=delta, params=nudged, pf=0.0)
                )

    if not neighbors:
        return SensResult(
            base_pf=base_pf,
            min_neighbor_pf=base_pf,
            max_pf_drop=0.0,
            neighbors=[],
            passed=True,
        )

    pfs = [n.pf for n in neighbors]
    min_pf = min(pfs)
    return SensResult(
        base_pf=base_pf,
        min_neighbor_pf=min_pf,
        max_pf_drop=base_pf - min_pf,
        neighbors=neighbors,
        passed=min_pf >= FRAGILE_PF_THRESHOLD,
    )
