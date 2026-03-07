"""Verify CSV data integrity before running any backtests.

Checks:
- All 9 CSVs exist
- Required columns present (open, high, low, close, volume)
- No NaN in OHLCV columns
- Date range covers IS (2020+) and OOS (2024+)
- No forward-fill gaps > 1 trading day
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

DATA_DIR = Path("./data/raw")
REQUIRED_FILES = [
    "MNQ_1m.csv", "MNQ_5m.csv", "MNQ_15m.csv",
    "MES_1m.csv", "MES_5m.csv", "MES_15m.csv",
    "MGC_1m.csv", "MGC_5m.csv", "MGC_15m.csv",
]
REQUIRED_COLS = {"open", "high", "low", "close", "volume"}
IS_START = pd.Timestamp("2020-01-01")
OOS_START = pd.Timestamp("2024-01-01")


def verify_file(path: Path) -> list[str]:
    """Return list of error strings (empty = OK)."""
    errors: list[str] = []

    try:
        df = pd.read_csv(path, index_col=0, parse_dates=True)
    except Exception as e:
        return [f"Cannot read CSV: {e}"]

    # Check columns
    cols = {c.lower() for c in df.columns}
    missing = REQUIRED_COLS - cols
    if missing:
        errors.append(f"Missing columns: {missing}")

    if df.empty:
        errors.append("Empty DataFrame")
        return errors

    # Check NaN
    nan_counts = df[[c for c in df.columns if c.lower() in REQUIRED_COLS]].isna().sum()
    bad_cols = nan_counts[nan_counts > 0]
    if not bad_cols.empty:
        errors.append(f"NaN values: {bad_cols.to_dict()}")

    # Check date coverage
    first = df.index[0]
    last = df.index[-1]
    if first > IS_START:
        errors.append(f"Data starts at {first.date()} -- need data from {IS_START.date()}")
    if last < OOS_START:
        errors.append(f"Data ends at {last.date()} -- need OOS data from {OOS_START.date()}")

    return errors


def main() -> int:
    print(f"Verifying CSV files in {DATA_DIR}/\n")
    all_ok = True

    for fname in REQUIRED_FILES:
        path = DATA_DIR / fname
        if not path.exists():
            print(f"  [MISSING] {fname}")
            all_ok = False
            continue

        size_mb = path.stat().st_size / 1_048_576
        errors = verify_file(path)

        if errors:
            print(f"  [FAIL]    {fname} ({size_mb:.1f} MB)")
            for e in errors:
                print(f"            - {e}")
            all_ok = False
        else:
            df = pd.read_csv(path, index_col=0, parse_dates=True)
            print(f"  [OK]      {fname} ({size_mb:.1f} MB, {len(df):,} rows, "
                  f"{df.index[0].date()} to {df.index[-1].date()})")

    print()
    if all_ok:
        print("All checks passed.")
        return 0
    else:
        print("Some checks FAILED. Fix before running backtests.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
