"""Price level computations for level-based breakout strategies.

All levels use PREVIOUS period data only — NO look-ahead.
Each function returns two arrays (level_high, level_low) of the same length as the input.

Sentinel research proved these levels drive 70%+ of portfolio PnL:
- Annual/Semiannual H/L: strongest alpha (unfiltered MNQ annual = $876/day in Sentinel)
- Quarterly/Monthly H/L: proven contributors
- PDH/PDL: Previous Day High/Low
- OR30: Opening Range first 30 minutes

RULES:
- Level at bar i uses ONLY data from bars 0..i-1 (previous periods)
- shift(1) before forward-fill to prevent look-ahead
- NaN-filled until the first complete period
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


def compute_pdhl(data: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Previous Day High/Low.

    Returns (pdh, pdl) arrays same length as data.
    pdh[i] = highest high of the PREVIOUS calendar day.
    pdl[i] = lowest low of the PREVIOUS calendar day.
    NaN until the second trading day.
    """
    n = len(data)
    pdh = np.full(n, np.nan)
    pdl = np.full(n, np.nan)

    if n == 0:
        return pdh, pdl

    # Resample to daily to get one H/L value per calendar day
    daily_h = data["high"].resample("1D").max().dropna()
    daily_l = data["low"].resample("1D").min().dropna()

    # Shift by 1 day BEFORE reindexing (prevents look-ahead)
    pdh_daily = daily_h.shift(1)
    pdl_daily = daily_l.shift(1)

    # Forward-fill to original index
    pdh_series = pdh_daily.reindex(data.index, method="ffill")
    pdl_series = pdl_daily.reindex(data.index, method="ffill")

    pdh = pdh_series.values
    pdl = pdl_series.values

    return pdh, pdl


def compute_or30(
    data: pd.DataFrame,
    rth_start_hour: int = 9,
    rth_start_minute: int = 30,
) -> tuple[np.ndarray, np.ndarray]:
    """Opening Range 30-minute High/Low.

    OR30 = High/Low of first 30 minutes after RTH open (9:30-10:00 ET).
    Level is valid AFTER 10:00 ET each day (when the 30-min window completes).
    NaN before first complete OR window.

    Args:
        data: OHLCV DataFrame with ET-localized DatetimeIndex
        rth_start_hour: RTH open hour (default 9)
        rth_start_minute: RTH open minute (default 30)
    """
    n = len(data)
    or_high = np.full(n, np.nan)
    or_low = np.full(n, np.nan)

    if n == 0:
        return or_high, or_low

    idx = pd.DatetimeIndex(data.index)
    hours = idx.hour  # pyright: ignore[reportAttributeAccessIssue]
    minutes = idx.minute  # pyright: ignore[reportAttributeAccessIssue]
    dates = idx.date  # pyright: ignore[reportAttributeAccessIssue]

    # Identify OR window: 9:30 to 10:00 ET
    or_end_minute = rth_start_minute + 30
    or_end_hour = rth_start_hour + (or_end_minute // 60)
    or_end_minute = or_end_minute % 60

    in_or_window = ((hours == rth_start_hour) & (minutes >= rth_start_minute)) | (
        (hours == or_end_hour) & (minutes < or_end_minute) & (or_end_hour > rth_start_hour)
    )

    # Extract price arrays once (loop-invariant)
    high_vals: np.ndarray = np.asarray(data["high"].values)
    low_vals: np.ndarray = np.asarray(data["low"].values)

    # For each day, compute OR30 H/L
    unique_dates = np.unique(dates)

    for d in unique_dates:
        day_mask = dates == d
        day_indices = np.where(day_mask)[0]

        or_mask = in_or_window[day_indices]
        or_indices = day_indices[or_mask]

        if len(or_indices) == 0:
            continue

        day_or_h = high_vals[or_indices].max()
        day_or_l = low_vals[or_indices].min()

        # OR level becomes valid AFTER the OR window closes
        # Find first bar after OR window on this day
        after_or = day_indices[~or_mask]
        post_or = after_or[after_or > or_indices[-1]]

        if len(post_or) > 0:
            # Deliberate overshoot: set from post_or[0] to end of array.
            # Each subsequent day's iteration overwrites its own range,
            # so only the final day's OR persists beyond that day.
            # This correctly forward-fills the most recent completed OR.
            or_high[post_or[0] :] = day_or_h
            or_low[post_or[0] :] = day_or_l

    return or_high, or_low


def _compute_periodic_hl(
    data: pd.DataFrame,
    freq: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Generic: compute PREVIOUS period high/low for a given frequency.

    Used by monthly, quarterly, semiannual, annual computations.

    Args:
        data: OHLCV DataFrame
        freq: pandas offset alias -- 'ME' for monthly, 'QE' for quarterly, etc.
    """
    n = len(data)
    level_h = np.full(n, np.nan)
    level_l = np.full(n, np.nan)

    if n == 0:
        return level_h, level_l

    # Resample to period
    period_h = data["high"].resample(freq).max().dropna()
    period_l = data["low"].resample(freq).min().dropna()

    # Shift by 1 period BEFORE reindexing (prevents look-ahead)
    prev_h = period_h.shift(1)
    prev_l = period_l.shift(1)

    # Forward-fill to original index
    level_h_series = prev_h.reindex(data.index, method="ffill")
    level_l_series = prev_l.reindex(data.index, method="ffill")

    return level_h_series.values, level_l_series.values


def compute_monthly_hl(data: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Previous Month High/Low."""
    return _compute_periodic_hl(data, "ME")


def compute_quarterly_hl(data: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Previous Quarter High/Low."""
    return _compute_periodic_hl(data, "QE")


def compute_semiannual_hl(data: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Previous Half-Year High/Low."""
    return _compute_periodic_hl(data, "6ME")


def compute_annual_hl(data: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Previous Calendar Year High/Low."""
    return _compute_periodic_hl(data, "YE")
