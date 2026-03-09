"""NinjaTrader CSV ingestion — reads staging folder, validates, merges to data/raw/.

Reads CSVs written by the NinjaTrader CsvExporter indicator from a cloud-synced
staging folder. Validates bars, deduplicates by timestamp, appends new bars to
data/raw/, and clears the LRU cache.

RULE: Staging files may contain full history (NT overwrites on chart load).
      Only bars newer than the last existing timestamp are appended.
RULE: Bars with NaN in OHLCV columns are silently rejected (logged as rejected_bars).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from config.instruments import TICKER_CLASS, TICKERS, TIMEFRAMES
from quant.data.cache import clear_cache

log = logging.getLogger(__name__)

OHLCV_COLS = ["open", "high", "low", "close", "volume"]
MAX_WEEKDAY_GAP_HOURS = 24.0


@dataclass
class GapInfo:
    last_existing: str
    first_new: str
    gap_hours: float


@dataclass
class FileReport:
    new_bars: int
    rejected_bars: int
    gaps: list[GapInfo] = field(default_factory=list)
    status: str = "up_to_date"  # "updated" | "up_to_date" | "error"
    error: str | None = None


@dataclass
class IngestReport:
    files_updated: int
    total_new_bars: int
    per_file: dict[str, FileReport] = field(default_factory=dict)


def ingest_file(
    ticker: str,
    timeframe: str,
    staging_dir: Path,
    data_dir: Path,
) -> FileReport:
    """Ingest a single staging CSV into data/raw/.

    Args:
        ticker: "MNQ", "MES", or "MGC"
        timeframe: "1m", "5m", or "15m"
        staging_dir: path to NT export synced folder
        data_dir: path to data/raw/

    Returns:
        FileReport with new_bars, rejected_bars, gaps, status
    """
    filename = f"{ticker}_{timeframe}.csv"
    ticker_cls = TICKER_CLASS[ticker]
    staging_path = staging_dir / ticker_cls / filename
    target_dir = data_dir / ticker_cls
    target_path = target_dir / filename

    if not staging_path.exists():
        return FileReport(
            new_bars=0,
            rejected_bars=0,
            status="error",
            error=f"Staging file not found: {staging_path}",
        )

    try:
        staging_df = pd.read_csv(staging_path, index_col=0, parse_dates=True)
    except Exception as e:
        log.error("Cannot read staging %s: %s", staging_path, e)
        return FileReport(new_bars=0, rejected_bars=0, status="error", error=str(e))

    staging_df.columns = [c.lower() for c in staging_df.columns]

    # Validate required columns
    missing = set(OHLCV_COLS) - set(staging_df.columns)
    if missing:
        return FileReport(
            new_bars=0,
            rejected_bars=0,
            status="error",
            error=f"Missing columns in staging: {missing}",
        )

    # Localize timestamps as ET if naive
    if staging_df.index.tz is None:
        staging_df.index = staging_df.index.tz_localize(
            "America/New_York", ambiguous="NaT", nonexistent="NaT"
        )
        staging_df = staging_df[staging_df.index.notna()]

    staging_df.sort_index(inplace=True)

    # Reject bars with NaN in OHLCV
    nan_mask = staging_df[OHLCV_COLS].isna().any(axis=1)
    rejected_bars = int(nan_mask.sum())
    if rejected_bars > 0:
        log.warning("%s: rejected %d bars with NaN values", filename, rejected_bars)
        staging_df = staging_df[~nan_mask]

    if staging_df.empty:
        return FileReport(new_bars=0, rejected_bars=rejected_bars, status="up_to_date")

    # Load existing data (if any)
    existing_df: pd.DataFrame | None = None
    last_existing_ts: pd.Timestamp | None = None

    if target_path.exists():
        try:
            existing_df = pd.read_csv(target_path, index_col=0, parse_dates=True)
            existing_df.columns = [c.lower() for c in existing_df.columns]
            if existing_df.index.tz is None:
                existing_df.index = existing_df.index.tz_localize(
                    "America/New_York", ambiguous="NaT", nonexistent="NaT"
                )
                existing_df = existing_df[existing_df.index.notna()]
            existing_df.sort_index(inplace=True)
            if not existing_df.empty:
                last_existing_ts = existing_df.index[-1]
        except Exception as e:
            log.warning("Cannot read existing %s, will overwrite: %s", target_path, e)

    # Filter to only new bars (after last existing timestamp)
    if last_existing_ts is not None:
        new_bars_df = staging_df[staging_df.index > last_existing_ts]
    else:
        new_bars_df = staging_df

    if new_bars_df.empty:
        return FileReport(new_bars=0, rejected_bars=rejected_bars, status="up_to_date")

    # Gap detection
    gaps: list[GapInfo] = []
    if last_existing_ts is not None and not new_bars_df.empty:
        first_new_ts = new_bars_df.index[0]
        gap_td = first_new_ts - last_existing_ts
        gap_hours = gap_td.total_seconds() / 3600

        # Only flag weekday gaps (skip Sat/Sun)
        last_day = last_existing_ts.weekday()  # 0=Mon ... 6=Sun
        first_day = first_new_ts.weekday()
        is_weekend_gap = last_day == 4 and first_day in (6, 0)  # Fri -> Sun/Mon

        if gap_hours > MAX_WEEKDAY_GAP_HOURS and not is_weekend_gap:
            gap = GapInfo(
                last_existing=str(last_existing_ts),
                first_new=str(first_new_ts),
                gap_hours=round(gap_hours, 1),
            )
            gaps.append(gap)
            log.warning(
                "%s: gap of %.1fh between %s and %s",
                filename,
                gap_hours,
                last_existing_ts,
                first_new_ts,
            )

    # Merge: append new bars to existing
    if existing_df is not None and not existing_df.empty:
        merged = pd.concat([existing_df, new_bars_df])
        # Final dedup (safety net for edge cases)
        merged = merged[~merged.index.duplicated(keep="first")]
        merged.sort_index(inplace=True)
    else:
        merged = new_bars_df
        target_dir.mkdir(parents=True, exist_ok=True)

    merged.to_csv(target_path, index_label="datetime")

    new_count = len(new_bars_df)
    log.info("%s: +%d new bars (last: %s)", filename, new_count, merged.index[-1])

    return FileReport(
        new_bars=new_count,
        rejected_bars=rejected_bars,
        gaps=gaps,
        status="updated",
    )


def ingest(staging_dir: Path, data_dir: Path) -> IngestReport:
    """Ingest all 9 instrument/timeframe CSVs from staging to data/raw/.

    Args:
        staging_dir: path to NT export synced folder
        data_dir: path to data/raw/

    Returns:
        IngestReport with per-file results and totals
    """
    report = IngestReport(files_updated=0, total_new_bars=0)

    for ticker in TICKERS:
        for tf in TIMEFRAMES:
            key = f"{ticker}_{tf}"
            file_report = ingest_file(ticker, tf, staging_dir, data_dir)
            report.per_file[key] = file_report

            if file_report.status == "updated":
                report.files_updated += 1
                report.total_new_bars += file_report.new_bars

    # Clear LRU cache so next backtest sees fresh data
    if report.files_updated > 0:
        clear_cache()
        log.info(
            "Ingestion complete: %d files updated, %d new bars total",
            report.files_updated,
            report.total_new_bars,
        )
    else:
        log.info("Ingestion complete: no new data")

    return report
