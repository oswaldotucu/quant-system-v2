"""SL x Exit Time grid expander for portfolio diversification.

After Optuna finds optimal params for a base strategy, this module generates
variant experiments with different SL and exit_time values. At portfolio level,
these variants are uncorrelated because different SL levels capture different
trade profiles.

From Sentinel research:
- SL grid: [0.3, 0.4, 0.5, 0.7, 1.0, 1.5, 2.0] (% of price)
- EXIT grid: [12, 13, 14, 15] (ET hours for forced exit)
- Total: 28 variants per base strategy
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

# Sentinel's proven grids
SL_GRID: list[float] = [0.3, 0.4, 0.5, 0.7, 1.0, 1.5, 2.0]
EXIT_GRID: list[int] = [12, 13, 14, 15]


@dataclass
class GridVariant:
    """A single SL x exit_time variant of a base strategy."""

    base_exp_id: int
    sl_pct: float
    exit_time_et: int
    params: dict[str, Any]


def expand_grid(
    base_exp_id: int,
    base_params: dict[str, Any],
    sl_grid: list[float] | None = None,
    exit_grid: list[int] | None = None,
) -> list[GridVariant]:
    """Expand base params into SL x exit_time grid variants.

    Args:
        base_exp_id: DB id of the base (Optuna-optimized) experiment
        base_params: Best params from Optuna
        sl_grid: SL values to test (default: Sentinel grid)
        exit_grid: Exit time hours ET (default: Sentinel grid)

    Returns:
        List of GridVariant objects, one per SL x exit combination.
        Excludes the combination that matches the base params (already tested).
    """
    if sl_grid is None:
        sl_grid = SL_GRID
    if exit_grid is None:
        exit_grid = EXIT_GRID

    variants: list[GridVariant] = []
    base_sl = base_params.get("sl_pct")
    base_exit = base_params.get("exit_time_et")

    for sl in sl_grid:
        for exit_time in exit_grid:
            # Skip the exact base combination (already tested by Optuna)
            if sl == base_sl and exit_time == base_exit:
                continue

            variant_params = copy.deepcopy(base_params)
            variant_params["sl_pct"] = sl
            variant_params["exit_time_et"] = exit_time

            variants.append(
                GridVariant(
                    base_exp_id=base_exp_id,
                    sl_pct=sl,
                    exit_time_et=exit_time,
                    params=variant_params,
                )
            )

    log.info(
        "Expanded exp %d into %d grid variants (SL=%d x EXIT=%d - 1 base)",
        base_exp_id,
        len(variants),
        len(sl_grid),
        len(exit_grid),
    )
    return variants
