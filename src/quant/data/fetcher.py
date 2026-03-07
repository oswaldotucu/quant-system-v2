"""Incremental Yahoo Finance data fetcher.

Downloads only new bars since the last CSV timestamp.
Triggered from Settings page or programmatically.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yfinance as yf

from config.instruments import TIMEFRAMES, YF_SYMBOLS
from config.settings import get_settings
from quant.data.cache import clear_cache

log = logging.getLogger(__name__)

START_DATE = "2020-01-01"  # earliest date to fetch if CSV is missing


@dataclass
class FetchResult:
    ticker: str
    timeframe: str
    new_bars: int
    last_date: pd.Timestamp
    status: str  # 'updated' | 'up_to_date' | 'error'
    error: str | None = None


def fetch_incremental(
    ticker: str,
    tf: str,
    data_dir: Path | None = None,
) -> FetchResult:
    """Download only new bars since last CSV timestamp and append to CSV.

    Args:
        ticker: 'MNQ', 'MES', or 'MGC'
        tf: '1m', '5m', or '15m'
        data_dir: directory containing CSVs (defaults to settings.data_dir)

    Returns:
        FetchResult with new_bars count and status
    """
    if data_dir is None:
        data_dir = get_settings().data_dir

    path = Path(data_dir) / f"{ticker}_{tf}.csv"
    yf_symbol = YF_SYMBOLS[ticker]

    # Load existing data to find last timestamp
    last_ts = START_DATE
    if path.exists():
        try:
            existing = pd.read_csv(path, index_col=0, parse_dates=True)
            if not existing.empty:
                last_ts = str(existing.index[-1].date())
        except Exception as e:
            log.warning("Could not read existing CSV %s: %s", path, e)

    log.info("Fetching %s %s from %s...", ticker, tf, last_ts)

    try:
        new_data = yf.download(
            yf_symbol,
            start=last_ts,
            interval=tf,
            auto_adjust=True,
            progress=False,
        )
    except Exception as e:
        log.error("yfinance download failed for %s %s: %s", ticker, tf, e)
        return FetchResult(ticker=ticker, timeframe=tf, new_bars=0,
                          last_date=pd.Timestamp.now(), status="error", error=str(e))

    if new_data.empty:
        log.info("%s %s: no new data", ticker, tf)
        return FetchResult(ticker=ticker, timeframe=tf, new_bars=0,
                          last_date=pd.Timestamp(last_ts), status="up_to_date")

    # Normalize columns
    new_data.columns = [c.lower() for c in new_data.columns]

    # Merge with existing
    if path.exists() and not existing.empty:
        merged = pd.concat([existing, new_data]).drop_duplicates().sort_index()
    else:
        merged = new_data

    merged.to_csv(path)
    clear_cache()

    new_count = len(new_data)
    last_date = merged.index[-1]
    log.info("%s %s: +%d new bars, last date %s", ticker, tf, new_count, last_date.date())

    return FetchResult(ticker=ticker, timeframe=tf, new_bars=new_count,
                      last_date=last_date, status="updated")


def fetch_all(data_dir: Path | None = None) -> list[FetchResult]:
    """Fetch all 9 instrument/timeframe combinations."""
    tickers = list(YF_SYMBOLS.keys())
    results: list[FetchResult] = []
    for ticker in tickers:
        for tf in TIMEFRAMES:
            results.append(fetch_incremental(ticker, tf, data_dir))
    return results
