"""IS/OOS data splitter.

These date constants are IMMUTABLE. Changing them invalidates all existing results.
See config/settings.py for the actual values (loaded from .env).

RULE: ALL backtests must use these functions to slice data.
RULE: OOS data must NEVER be touched before the OOS_VAL gate.
"""

from __future__ import annotations

import pandas as pd

from config.settings import get_settings


def is_train(data: pd.DataFrame) -> pd.DataFrame:
    """Return IS-train slice: 2020-01-01 to 2022-12-31."""
    cfg = get_settings()
    return data.loc[cfg.is_start : cfg.is_train_end]


def is_val(data: pd.DataFrame) -> pd.DataFrame:
    """Return IS-val slice: 2023-01-01 to 2023-12-31 (Optuna objective)."""
    cfg = get_settings()
    # IS_TRAIN_END + 1 day to IS_VAL_END
    val_start = (pd.Timestamp(cfg.is_train_end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    return data.loc[val_start : cfg.is_val_end]


def oos(data: pd.DataFrame) -> pd.DataFrame:
    """Return OOS slice: 2024-01-01 to present.

    NEVER call this before the OOS_VAL gate. It is a bug to use this in IS_OPT.
    """
    cfg = get_settings()
    return data.loc[cfg.oos_start :]


def is_full(data: pd.DataFrame) -> pd.DataFrame:
    """Return full IS period: IS-train + IS-val (2020-2023)."""
    cfg = get_settings()
    return data.loc[cfg.is_start : cfg.is_val_end]


def validate_no_oos_leak(data: pd.DataFrame, context: str = "") -> None:
    """Raise ValueError if data contains any OOS rows.

    Call this inside IS_OPT gate to guard against accidental leakage.
    """
    cfg = get_settings()
    oos_rows = data.loc[cfg.oos_start :]
    if not oos_rows.empty:
        raise ValueError(
            f"OOS DATA LEAK in {context}: data contains rows from {cfg.oos_start}. "
            "This is a bug — never pass OOS data to IS optimization."
        )
