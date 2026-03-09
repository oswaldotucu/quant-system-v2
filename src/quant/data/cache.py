"""LRU in-memory cache for loaded OHLCV DataFrames.

Avoids reloading the same 300MB CSV on every backtest call.
Cache is shared across all threads in the same process (safe because DataFrames are read-only).
"""

from __future__ import annotations

import functools
from pathlib import Path

import pandas as pd

from quant.data.loader import load_ohlcv


@functools.lru_cache(maxsize=32)
def cached_ohlcv(ticker: str, timeframe: str, data_dir_str: str) -> pd.DataFrame:
    """Cached version of load_ohlcv. Cache key includes data_dir as string."""
    return load_ohlcv(ticker, timeframe, Path(data_dir_str))


def get_ohlcv(ticker: str, timeframe: str, data_dir: Path | None = None) -> pd.DataFrame:
    """Load OHLCV with in-process LRU cache.

    This is the preferred entry point for all backtest code.
    """
    from config.settings import get_settings

    if data_dir is None:
        data_dir = get_settings().data_dir
    return cached_ohlcv(ticker, timeframe, str(data_dir))


def clear_cache() -> None:
    """Clear the LRU cache (e.g. after a data fetch update)."""
    cached_ohlcv.cache_clear()
