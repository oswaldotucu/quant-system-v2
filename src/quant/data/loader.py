"""CSV data loader for OHLCV data.

Loads historical CSVs from data/raw/ into pandas DataFrames.
Timestamps are converted to US/Eastern timezone (ET).
Data is cached in-process via LRU cache (see cache.py).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from config.instruments import ticker_data_dir
from config.settings import get_settings

log = logging.getLogger(__name__)

REQUIRED_COLS = {"open", "high", "low", "close", "volume"}


def load_ohlcv(ticker: str, timeframe: str, data_dir: Path | None = None) -> pd.DataFrame:
    """Load OHLCV data for a ticker/timeframe from CSV.

    Returns:
        DataFrame with DatetimeIndex in US/Eastern timezone.
        Columns: open, high, low, close, volume (all lowercase).

    Raises:
        FileNotFoundError: if CSV does not exist
        ValueError: if required columns are missing or data is empty
    """
    if data_dir is None:
        data_dir = get_settings().data_dir

    resolved_dir = Path(ticker_data_dir(ticker, data_dir))
    path = resolved_dir / f"{ticker}_{timeframe}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"CSV not found: {path}. Run 'make copy-data' to populate data/raw/."
        )

    df = pd.read_csv(path, index_col=0, parse_dates=True)

    # Normalize column names to lowercase
    df.columns = [c.lower() for c in df.columns]

    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        raise ValueError(f"CSV {path.name} missing required columns: {missing}")

    if df.empty:
        raise ValueError(f"CSV {path.name} is empty")

    # Ensure timezone-aware index.
    # Source CSVs store timestamps in ET already (CME session open = 18:00 ET).
    # Localize directly as ET; do NOT treat as UTC first.
    if df.index.tz is None:
        df.index = df.index.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT")
        df = df[df.index.notna()]  # drop any DST fold/gap rows
    else:
        df.index = df.index.tz_convert("America/New_York")

    df.sort_index(inplace=True)

    log.debug(
        "Loaded %s %s: %d rows (%s to %s)",
        ticker,
        timeframe,
        len(df),
        df.index[0].date(),
        df.index[-1].date(),
    )
    return df
