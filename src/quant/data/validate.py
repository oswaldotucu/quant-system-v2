"""Pre-backtest data sanity checks."""

from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)

MIN_ROWS = 100  # minimum bars required to run any backtest


def validate_ohlcv(data: pd.DataFrame, context: str = "") -> list[str]:
    """Return list of validation errors. Empty list means data is clean."""
    errors: list[str] = []
    prefix = f"[{context}] " if context else ""

    if data.empty:
        return [f"{prefix}DataFrame is empty"]

    if len(data) < MIN_ROWS:
        errors.append(f"{prefix}Only {len(data)} rows — need at least {MIN_ROWS}")

    required = {"open", "high", "low", "close", "volume"}
    cols = {c.lower() for c in data.columns}
    missing = required - cols
    if missing:
        errors.append(f"{prefix}Missing columns: {missing}")

    if not errors:
        nan_counts = data[list(required & cols)].isna().sum()
        bad = nan_counts[nan_counts > 0]
        if not bad.empty:
            errors.append(f"{prefix}NaN values: {bad.to_dict()}")

    return errors


def require_clean(data: pd.DataFrame, context: str = "") -> None:
    """Raise ValueError if data fails validation."""
    errors = validate_ohlcv(data, context)
    if errors:
        raise ValueError("\n".join(errors))
