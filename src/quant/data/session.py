"""Session time filters for micro-futures trading.

Sentinel research proved entries 9-14 ET produce all edge;
overnight/premarket entries are noise. DOW filter (Thu/Fri only)
doubles Calmar ratio.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


def make_session_mask(
    index: pd.DatetimeIndex,
    start_et: int = 9,
    end_et: int = 14,
) -> np.ndarray:
    """Return bool mask: True for bars in [start_et, end_et) Eastern Time.

    The index must be tz-aware in America/New_York (our loader ensures this).
    If tz-naive, we assume it's already ET.

    Args:
        index: DatetimeIndex of the OHLCV data
        start_et: Start hour in ET (inclusive), default 9
        end_et: End hour in ET (exclusive), default 14

    Returns:
        np.ndarray of bool, same length as index
    """
    hours = index.hour  # pyright: ignore[reportAttributeAccessIssue]
    return np.array((hours >= start_et) & (hours < end_et), dtype=bool)


def make_time_exit_mask(
    index: pd.DatetimeIndex,
    exit_hour_et: int = 15,
) -> np.ndarray:
    """Return bool mask: True for bars at or after exit_hour_et.

    Used to force-close intraday positions before the session ends.
    vectorbt will close any open position at the first True exit after entry.

    Args:
        index: DatetimeIndex of the OHLCV data
        exit_hour_et: Hour in ET at which to force exit (default 15 = 3pm)

    Returns:
        np.ndarray of bool
    """
    return np.array(index.hour >= exit_hour_et, dtype=bool)  # pyright: ignore[reportAttributeAccessIssue]


def make_dow_mask(
    index: pd.DatetimeIndex,
    allowed_days: tuple[int, ...] = (3, 4),
) -> np.ndarray:
    """Return bool mask: True for bars on allowed weekdays.

    Default: Thu=3, Fri=4 (Sentinel found Mon/Tue/Wed structurally negative).

    Args:
        index: DatetimeIndex
        allowed_days: tuple of weekday ints (Mon=0, Sun=6)

    Returns:
        np.ndarray of bool
    """
    return np.isin(index.dayofweek, allowed_days)  # pyright: ignore[reportAttributeAccessIssue]
