"""Strategy Protocol — the interface all strategies must implement.

A strategy is a pure function: (data, params) -> (entries, exits, direction)
No I/O, no DB access, no side effects.
"""

from __future__ import annotations

from typing import Any, Protocol

import numpy as np
import pandas as pd


class Strategy(Protocol):
    """Protocol for strategy signal generators.

    Implementations must be importable and instantiation-free:
        signals = MyStrategy.generate(data, params)
    """

    name: str
    family: str  # e.g. 'trend_following', 'mean_reversion'

    @staticmethod
    def generate(
        data: pd.DataFrame,
        params: dict[str, Any],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Generate entry/exit signals from OHLCV data.

        Args:
            data: OHLCV DataFrame with DatetimeIndex
            params: strategy hyperparameters

        Returns:
            (entries, exits, direction) — all boolean numpy arrays, same length as data
            entries: True on bars to enter a trade
            exits:   True on bars to exit a trade
            direction: True = long, False = short
        """
        ...

    @staticmethod
    def default_params() -> dict[str, Any]:
        """Return default/proven parameters for this strategy."""
        ...
