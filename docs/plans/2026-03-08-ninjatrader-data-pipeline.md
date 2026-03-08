# NinjaTrader Data Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace Yahoo Finance with NinjaTrader CSV exports as the primary OHLCV data source, with validated ingestion from a synced staging folder.

**Architecture:** NinjaTrader runs a single C# indicator that writes 9 CSV files (3 instruments x 3 timeframes) to a cloud-synced folder. A Python ingestion module reads new bars from the staging folder, validates them, deduplicates by timestamp, and appends to `data/raw/`. A `/api/data/health` endpoint and dashboard indicator show per-file freshness and gaps.

**Tech Stack:** Python 3.12, pandas, FastAPI, Jinja2, NinjaScript (C#), uv

---

## Context for Implementers

### Existing data pipeline (DO NOT modify unless instructed)
- `src/quant/data/loader.py` — `load_ohlcv(ticker, tf)` loads CSVs from `data/raw/`, localizes timestamps as ET
- `src/quant/data/cache.py` — `get_ohlcv()` wraps loader with LRU(32); `clear_cache()` invalidates
- `src/quant/data/validate.py` — `validate_ohlcv(df)` checks columns, NaN, min rows
- `src/quant/data/fetcher.py` — Yahoo Finance fetcher (stays as fallback, not modified)
- `src/config/instruments.py` — `TICKERS = ["MNQ", "MES", "MGC"]`, `TIMEFRAMES = ["1m", "5m", "15m"]`
- `src/config/settings.py` — Pydantic `Settings` class, singleton via `get_settings()`

### CSV format expected by loader
```
datetime,open,high,low,close,volume
2024-01-02 18:00:00,16850.25,16855.00,16848.50,16852.75,142
```
Timestamps must be US/Eastern (ET). Columns lowercase. Index column is `datetime`.

### Testing conventions
- Unit tests use synthetic data from `conftest.py:sample_ohlcv` fixture — never real CSVs
- DB tests use `conftest.py:tmp_db` fixture (fresh schema in temp dir)
- Integration tests use `conftest.py:client` fixture (FastAPI TestClient)
- Run: `uv run pytest tests/unit/ tests/integration/ --no-cov -q`

### Import convention
Packages imported as `config.*`, `db.*`, `quant.*`, `webapp.*` — never `src.*`.

---

## Task 1: Add Staging Settings

**Files:**
- Modify: `src/config/settings.py:14-52`
- Modify: `.env.example:1-40`

**Step 1: Add staging_dir field to Settings**

Add after line 21 (`checklist_dir`) in `src/config/settings.py`:

```python
    staging_dir: Path = Path("")  # NT export staging folder (empty = disabled)
```

Add `"staging_dir"` to the existing `resolve_path` field_validator on line 54 (currently validates `data_dir`, `pine_dir`, `checklist_dir`):

```python
    @field_validator("data_dir", "pine_dir", "checklist_dir", "staging_dir", mode="before")
```

**Step 2: Add to .env.example**

Add after line 8 (`CHECKLIST_DIR`) in `.env.example`:

```
STAGING_DIR=                    # Path to NT export synced folder (empty = disabled)
```

**Step 3: Verify nothing breaks**

Run: `uv run pytest tests/unit/ tests/integration/ --no-cov -q`
Expected: All 118 tests PASS (new field has default, no existing behavior changes)

**Step 4: Commit**

```bash
git add src/config/settings.py .env.example
git commit -m "feat: add staging_dir setting for NT export ingestion"
```

---

## Task 2: Ingestion Module — Core Logic

**Files:**
- Create: `src/quant/data/ingest.py`
- Create: `tests/unit/test_ingest.py`

**Step 1: Write the failing tests**

Create `tests/unit/test_ingest.py`:

```python
"""Tests for NinjaTrader CSV ingestion."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest


def _write_csv(path: Path, df: pd.DataFrame) -> None:
    """Helper: write DataFrame to CSV with datetime index."""
    df.to_csv(path, index_label="datetime")


def _make_bars(start: str, periods: int, freq: str = "15min", base: float = 15000.0) -> pd.DataFrame:
    """Helper: generate synthetic OHLCV bars."""
    rng = np.random.default_rng(seed=42)
    idx = pd.date_range(start, periods=periods, freq=freq, tz="America/New_York")
    close = base + np.cumsum(rng.normal(0, 1, periods))
    return pd.DataFrame({
        "open": close + rng.normal(0, 0.5, periods),
        "high": close + abs(rng.normal(0, 1, periods)),
        "low": close - abs(rng.normal(0, 1, periods)),
        "close": close,
        "volume": rng.integers(100, 5000, periods),
    }, index=idx)


class TestIngestFile:
    """Tests for ingest_file() — single file ingestion."""

    def test_new_file_no_existing(self, tmp_path: Path) -> None:
        """Staging file with no existing data/raw file — creates it."""
        from quant.data.ingest import ingest_file

        staging = tmp_path / "staging"
        staging.mkdir()
        data_dir = tmp_path / "raw"
        data_dir.mkdir()

        bars = _make_bars("2024-01-02 18:00", periods=100)
        _write_csv(staging / "MNQ_15m.csv", bars)

        report = ingest_file("MNQ", "15m", staging, data_dir)
        assert report.new_bars == 100
        assert report.rejected_bars == 0
        assert report.status == "updated"
        assert (data_dir / "MNQ_15m.csv").exists()

    def test_append_new_bars(self, tmp_path: Path) -> None:
        """Staging has newer bars — only new bars are appended."""
        from quant.data.ingest import ingest_file

        staging = tmp_path / "staging"
        staging.mkdir()
        data_dir = tmp_path / "raw"
        data_dir.mkdir()

        old_bars = _make_bars("2024-01-02 18:00", periods=100)
        _write_csv(data_dir / "MNQ_15m.csv", old_bars)

        # Staging has old bars + 50 new ones
        all_bars = _make_bars("2024-01-02 18:00", periods=150)
        _write_csv(staging / "MNQ_15m.csv", all_bars)

        report = ingest_file("MNQ", "15m", staging, data_dir)
        assert report.new_bars == 50
        assert report.status == "updated"

        # Verify total rows
        result = pd.read_csv(data_dir / "MNQ_15m.csv", index_col=0, parse_dates=True)
        assert len(result) == 150

    def test_no_new_bars(self, tmp_path: Path) -> None:
        """Staging has same data as existing — nothing to do."""
        from quant.data.ingest import ingest_file

        staging = tmp_path / "staging"
        staging.mkdir()
        data_dir = tmp_path / "raw"
        data_dir.mkdir()

        bars = _make_bars("2024-01-02 18:00", periods=100)
        _write_csv(data_dir / "MNQ_15m.csv", bars)
        _write_csv(staging / "MNQ_15m.csv", bars)

        report = ingest_file("MNQ", "15m", staging, data_dir)
        assert report.new_bars == 0
        assert report.status == "up_to_date"

    def test_deduplicates_overlapping_timestamps(self, tmp_path: Path) -> None:
        """Overlapping timestamps between staging and existing are deduplicated."""
        from quant.data.ingest import ingest_file

        staging = tmp_path / "staging"
        staging.mkdir()
        data_dir = tmp_path / "raw"
        data_dir.mkdir()

        old_bars = _make_bars("2024-01-02 18:00", periods=100)
        _write_csv(data_dir / "MNQ_15m.csv", old_bars)

        # Staging overlaps last 20 bars and adds 30 new
        overlap_start = old_bars.index[80].strftime("%Y-%m-%d %H:%M")
        staging_bars = _make_bars(overlap_start, periods=50)
        _write_csv(staging / "MNQ_15m.csv", staging_bars)

        report = ingest_file("MNQ", "15m", staging, data_dir)
        # Should add 30 new bars (50 staging - 20 overlap)
        assert report.new_bars == 30
        assert report.status == "updated"

    def test_rejects_nan_bars(self, tmp_path: Path) -> None:
        """Bars with NaN in OHLCV columns are rejected."""
        from quant.data.ingest import ingest_file

        staging = tmp_path / "staging"
        staging.mkdir()
        data_dir = tmp_path / "raw"
        data_dir.mkdir()

        bars = _make_bars("2024-01-02 18:00", periods=50)
        bars.iloc[10, bars.columns.get_loc("close")] = float("nan")
        bars.iloc[20, bars.columns.get_loc("high")] = float("nan")
        _write_csv(staging / "MNQ_15m.csv", bars)

        report = ingest_file("MNQ", "15m", staging, data_dir)
        assert report.new_bars == 48
        assert report.rejected_bars == 2

    def test_staging_file_missing(self, tmp_path: Path) -> None:
        """Missing staging file returns error status."""
        from quant.data.ingest import ingest_file

        staging = tmp_path / "staging"
        staging.mkdir()
        data_dir = tmp_path / "raw"
        data_dir.mkdir()

        report = ingest_file("MNQ", "15m", staging, data_dir)
        assert report.status == "error"
        assert report.new_bars == 0


class TestGapDetection:
    """Tests for gap detection during ingestion."""

    def test_detects_weekday_gap(self, tmp_path: Path) -> None:
        """Gap > 24h on a weekday is flagged."""
        from quant.data.ingest import ingest_file

        staging = tmp_path / "staging"
        staging.mkdir()
        data_dir = tmp_path / "raw"
        data_dir.mkdir()

        # Existing data ends Monday
        old_bars = _make_bars("2024-01-08 18:00", periods=100)  # Mon Jan 8
        _write_csv(data_dir / "MNQ_15m.csv", old_bars)

        # Staging starts Thursday (3-day gap on weekdays)
        new_bars = _make_bars("2024-01-11 18:00", periods=50)  # Thu Jan 11
        _write_csv(staging / "MNQ_15m.csv", new_bars)

        report = ingest_file("MNQ", "15m", staging, data_dir)
        assert len(report.gaps) >= 1
        assert report.gaps[0].gap_hours > 24

    def test_weekend_gap_not_flagged(self, tmp_path: Path) -> None:
        """Gap over a weekend is not flagged (markets closed)."""
        from quant.data.ingest import ingest_file

        staging = tmp_path / "staging"
        staging.mkdir()
        data_dir = tmp_path / "raw"
        data_dir.mkdir()

        # Existing data ends Friday evening
        old_bars = _make_bars("2024-01-12 08:00", periods=40, freq="15min")  # Fri Jan 12
        _write_csv(data_dir / "MNQ_15m.csv", old_bars)

        # Staging starts Sunday evening (normal CME globex open)
        new_bars = _make_bars("2024-01-14 18:00", periods=50)  # Sun Jan 14
        _write_csv(staging / "MNQ_15m.csv", new_bars)

        report = ingest_file("MNQ", "15m", staging, data_dir)
        assert len(report.gaps) == 0


class TestIngestAll:
    """Tests for ingest() — all 9 files."""

    def test_ingest_all_files(self, tmp_path: Path) -> None:
        """Ingest processes all 9 instrument/timeframe combos."""
        from quant.data.ingest import ingest

        staging = tmp_path / "staging"
        staging.mkdir()
        data_dir = tmp_path / "raw"
        data_dir.mkdir()

        from config.instruments import TICKERS, TIMEFRAMES

        for ticker in TICKERS:
            for tf in TIMEFRAMES:
                freq = {"1m": "1min", "5m": "5min", "15m": "15min"}[tf]
                bars = _make_bars("2024-01-02 18:00", periods=50, freq=freq)
                _write_csv(staging / f"{ticker}_{tf}.csv", bars)

        report = ingest(staging, data_dir)
        assert report.files_updated == 9
        assert report.total_new_bars == 9 * 50

    def test_ingest_partial_staging(self, tmp_path: Path) -> None:
        """If only some staging files exist, process those and error on missing."""
        from quant.data.ingest import ingest

        staging = tmp_path / "staging"
        staging.mkdir()
        data_dir = tmp_path / "raw"
        data_dir.mkdir()

        # Only create 1 file
        bars = _make_bars("2024-01-02 18:00", periods=50)
        _write_csv(staging / "MNQ_15m.csv", bars)

        report = ingest(staging, data_dir)
        assert report.files_updated == 1
        # 8 files should have error status
        error_count = sum(1 for fr in report.per_file.values() if fr.status == "error")
        assert error_count == 8
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_ingest.py -v`
Expected: All FAIL with `ModuleNotFoundError: No module named 'quant.data.ingest'`

**Step 3: Write the implementation**

Create `src/quant/data/ingest.py`:

```python
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

from config.instruments import TICKERS, TIMEFRAMES
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
    staging_path = staging_dir / filename
    target_path = data_dir / filename

    if not staging_path.exists():
        return FileReport(
            new_bars=0, rejected_bars=0, status="error",
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
            new_bars=0, rejected_bars=0, status="error",
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
                filename, gap_hours, last_existing_ts, first_new_ts,
            )

    # Merge: append new bars to existing
    if existing_df is not None and not existing_df.empty:
        merged = pd.concat([existing_df, new_bars_df])
        # Final dedup (safety net for edge cases)
        merged = merged[~merged.index.duplicated(keep="first")]
        merged.sort_index(inplace=True)
    else:
        merged = new_bars_df
        data_dir.mkdir(parents=True, exist_ok=True)

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
            report.files_updated, report.total_new_bars,
        )
    else:
        log.info("Ingestion complete: no new data")

    return report
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_ingest.py -v`
Expected: All 10 tests PASS

**Step 5: Run full test suite**

Run: `uv run pytest tests/unit/ tests/integration/ --no-cov -q`
Expected: All tests PASS (existing + 10 new)

**Step 6: Commit**

```bash
git add src/quant/data/ingest.py tests/unit/test_ingest.py
git commit -m "feat: add NT CSV ingestion module with validation and gap detection"
```

---

## Task 3: CLI Script + Makefile Target

**Files:**
- Create: `scripts/ingest_data.py`
- Modify: `Makefile:1-2,42-44`

**Step 1: Create the CLI script**

Create `scripts/ingest_data.py`:

```python
"""Ingest NinjaTrader CSV exports from staging folder into data/raw/.

Usage:
    make ingest                              # uses STAGING_DIR from .env
    make ingest STAGING=/path/to/folder      # override staging dir
    uv run python scripts/ingest_data.py     # uses STAGING_DIR from .env
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from config.settings import get_settings
from quant.data.ingest import ingest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def main() -> int:
    cfg = get_settings()

    staging_dir = cfg.staging_dir
    if not str(staging_dir) or str(staging_dir) == ".":
        log.error("STAGING_DIR not set. Set it in .env or pass STAGING=/path/to/folder")
        return 1

    if not staging_dir.exists():
        log.error("Staging directory does not exist: %s", staging_dir)
        return 1

    data_dir = cfg.data_dir
    log.info("Ingesting from %s -> %s", staging_dir, data_dir)

    report = ingest(staging_dir, data_dir)

    # Print summary
    print(f"\n{'='*60}")
    print(f"Ingestion Summary: {report.files_updated} files updated, "
          f"{report.total_new_bars} new bars")
    print(f"{'='*60}")

    for key, fr in sorted(report.per_file.items()):
        if fr.status == "error":
            print(f"  [ERROR]      {key}: {fr.error}")
        elif fr.status == "updated":
            gap_str = f" ({len(fr.gaps)} gaps)" if fr.gaps else ""
            rej_str = f" ({fr.rejected_bars} rejected)" if fr.rejected_bars else ""
            print(f"  [UPDATED]    {key}: +{fr.new_bars} bars{rej_str}{gap_str}")
        else:
            print(f"  [UP TO DATE] {key}")

    # Print gap details
    all_gaps = [(k, g) for k, fr in report.per_file.items() for g in fr.gaps]
    if all_gaps:
        print(f"\nGaps detected:")
        for key, gap in all_gaps:
            print(f"  {key}: {gap.gap_hours}h gap ({gap.last_existing} -> {gap.first_new})")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 2: Add Makefile targets**

In `Makefile`, add `ingest` to the `.PHONY` list on line 1 (after `fetch-data`):

```
.PHONY: install dev test test-regression test-slow test-all lint typecheck check \
        format copy-data verify-data fetch-data ingest docker-up docker-logs docker-down
```

Add after the `fetch-data` target (after line 44):

```makefile
ingest:
ifdef STAGING
	STAGING_DIR=$(STAGING) uv run python scripts/ingest_data.py
else
	uv run python scripts/ingest_data.py
endif
```

**Step 3: Verify Makefile syntax**

Run: `make -n ingest`
Expected: Shows dry-run of `uv run python scripts/ingest_data.py` (may error on STAGING_DIR not set, that's OK)

**Step 4: Commit**

```bash
git add scripts/ingest_data.py Makefile
git commit -m "feat: add make ingest CLI for NT data ingestion"
```

---

## Task 4: Data Health API Endpoint

**Files:**
- Modify: `src/webapp/routes/api.py:84-98`
- Create: `tests/unit/test_data_health.py`

**Step 1: Write the failing test**

Create `tests/unit/test_data_health.py`:

```python
"""Tests for data health reporting."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest


def _make_csv(path: Path, start: str, periods: int, freq: str = "15min") -> None:
    """Write a synthetic CSV to path."""
    rng = np.random.default_rng(seed=42)
    idx = pd.date_range(start, periods=periods, freq=freq, tz="America/New_York")
    close = 15000 + np.cumsum(rng.normal(0, 1, periods))
    df = pd.DataFrame({
        "open": close, "high": close + 1, "low": close - 1,
        "close": close, "volume": rng.integers(100, 5000, periods),
    }, index=idx)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index_label="datetime")


class TestDataHealth:

    def test_returns_all_files(self, tmp_path: Path) -> None:
        """Health check returns status for all 9 instrument/timeframe combos."""
        from quant.data.health import get_data_health

        data_dir = tmp_path / "raw"
        data_dir.mkdir()

        from config.instruments import TICKERS, TIMEFRAMES
        for ticker in TICKERS:
            for tf in TIMEFRAMES:
                freq = {"1m": "1min", "5m": "5min", "15m": "15min"}[tf]
                _make_csv(data_dir / f"{ticker}_{tf}.csv", "2024-01-02 18:00", 100, freq)

        health = get_data_health(data_dir)
        assert len(health) == 9
        for key, info in health.items():
            assert info["status"] in ("fresh", "stale", "missing")
            assert info["bars"] == 100
            assert "last_bar" in info

    def test_missing_file(self, tmp_path: Path) -> None:
        """Missing CSV returns 'missing' status."""
        from quant.data.health import get_data_health

        data_dir = tmp_path / "raw"
        data_dir.mkdir()

        health = get_data_health(data_dir)
        for info in health.values():
            assert info["status"] == "missing"
            assert info["bars"] == 0

    def test_stale_file(self, tmp_path: Path) -> None:
        """File with last bar > 48h ago is 'stale'."""
        from quant.data.health import get_data_health

        data_dir = tmp_path / "raw"
        _make_csv(data_dir / "MNQ_15m.csv", "2020-01-02 18:00", 100)

        health = get_data_health(data_dir)
        assert health["MNQ_15m"]["status"] == "stale"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_data_health.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quant.data.health'`

**Step 3: Write the implementation**

Create `src/quant/data/health.py`:

```python
"""Data health reporting — per-file freshness and gap status."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from config.instruments import TICKERS, TIMEFRAMES

log = logging.getLogger(__name__)

STALE_HOURS = 48.0  # > 48h since last bar = stale


def get_data_health(data_dir: Path) -> dict[str, dict[str, Any]]:
    """Return health status for all 9 instrument/timeframe CSVs.

    Returns:
        Dict keyed by "MNQ_1m" etc, each with:
        - status: "fresh" | "stale" | "missing"
        - bars: int (total rows)
        - last_bar: str | None (last timestamp)
        - stale_hours: float (hours since last bar)
    """
    health: dict[str, dict[str, Any]] = {}
    now = pd.Timestamp.now(tz="America/New_York")

    for ticker in TICKERS:
        for tf in TIMEFRAMES:
            key = f"{ticker}_{tf}"
            path = data_dir / f"{key}.csv"

            if not path.exists():
                health[key] = {
                    "status": "missing",
                    "bars": 0,
                    "last_bar": None,
                    "stale_hours": 0.0,
                }
                continue

            try:
                df = pd.read_csv(path, index_col=0, parse_dates=True)
                if df.empty:
                    health[key] = {
                        "status": "missing",
                        "bars": 0,
                        "last_bar": None,
                        "stale_hours": 0.0,
                    }
                    continue

                if df.index.tz is None:
                    df.index = df.index.tz_localize(
                        "America/New_York", ambiguous="NaT", nonexistent="NaT"
                    )

                last_ts = df.index[-1]
                stale_hours = (now - last_ts).total_seconds() / 3600
                status = "stale" if stale_hours > STALE_HOURS else "fresh"

                health[key] = {
                    "status": status,
                    "bars": len(df),
                    "last_bar": str(last_ts),
                    "stale_hours": round(stale_hours, 1),
                }
            except Exception as e:
                log.warning("Cannot read %s for health check: %s", path, e)
                health[key] = {
                    "status": "missing",
                    "bars": 0,
                    "last_bar": None,
                    "stale_hours": 0.0,
                }

    return health
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_data_health.py -v`
Expected: All 3 tests PASS

**Step 5: Add the API endpoint**

In `src/webapp/routes/api.py`, add after the existing `trigger_fetch` route (after line 98):

```python
@router.get("/data/health")
def data_health(cfg: Any = Depends(get_cfg)) -> dict[str, Any]:
    """Return per-file data freshness and gap status."""
    from quant.data.health import get_data_health
    return {"files": get_data_health(cfg.data_dir)}
```

**Step 6: Add integration test**

Add to `tests/integration/test_api.py` (at the end of the file):

```python
def test_data_health_endpoint(client: TestClient) -> None:
    response = client.get("/api/data/health")
    assert response.status_code == 200
    data = response.json()
    assert "files" in data
```

**Step 7: Run full test suite**

Run: `uv run pytest tests/unit/ tests/integration/ --no-cov -q`
Expected: All tests PASS

**Step 8: Commit**

```bash
git add src/quant/data/health.py tests/unit/test_data_health.py src/webapp/routes/api.py tests/integration/test_api.py
git commit -m "feat: add /api/data/health endpoint for data freshness monitoring"
```

---

## Task 5: Dashboard Data Health Indicator

**Files:**
- Modify: `src/webapp/templates/dashboard.html:57-69`
- Modify: `src/webapp/routes/api.py` (add HTML partial endpoint)
- Create: `src/webapp/templates/partials/data_health.html`

**Step 1: Create the HTML partial**

Create `src/webapp/templates/partials/data_health.html`:

```html
<div class="grid grid-cols-3 gap-2">
  {% for key, info in files.items() %}
  <div class="flex items-center justify-between text-xs p-1.5 rounded
              {% if info.status == 'fresh' %}bg-green-900/30 border border-green-800
              {% elif info.status == 'stale' %}bg-yellow-900/30 border border-yellow-800
              {% else %}bg-red-900/30 border border-red-800{% endif %}">
    <span class="font-mono">{{ key }}</span>
    <span>
      {% if info.status == 'fresh' %}
        <span class="text-green-400">{{ info.bars | default(0) }} bars</span>
      {% elif info.status == 'stale' %}
        <span class="text-yellow-400">{{ info.stale_hours | round(0) | int }}h stale</span>
      {% else %}
        <span class="text-red-400">missing</span>
      {% endif %}
    </span>
  </div>
  {% endfor %}
</div>
```

**Step 2: Add the HTML partial endpoint**

In `src/webapp/routes/api.py`, add after the `data_health` endpoint:

```python
@router.get("/data/health/html", response_class=HTMLResponse)
def data_health_html(
    request: Request,
    cfg: Any = Depends(get_cfg),
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    """Return data health as HTML fragment for HTMX."""
    from quant.data.health import get_data_health
    return templates.TemplateResponse(
        "partials/data_health.html",
        {"request": request, "files": get_data_health(cfg.data_dir)},
    )
```

**Step 3: Add data health section to dashboard**

In `src/webapp/templates/dashboard.html`, add after the PIPELINE STATUS grid (after line 69, before the log tail section):

```html
    <!-- Data Health -->
    <div class="bg-gray-900 border border-gray-700 rounded p-4">
      <h2 class="text-gray-400 font-bold mb-2 text-xs">DATA HEALTH</h2>
      <div id="data-health"
           hx-get="/api/data/health/html"
           hx-trigger="load, every 60s"
           hx-swap="innerHTML">
        <div class="text-gray-600 text-xs">Loading data health...</div>
      </div>
    </div>
```

**Step 4: Add ingest button to settings page**

In `src/webapp/templates/settings.html`, add after the existing DATA section (after line 41, inside the grid):

```html
    <!-- NT Ingestion -->
    <div class="bg-gray-900 border border-gray-700 rounded p-4">
      <h2 class="text-gray-400 text-xs font-bold mb-3">NT INGESTION</h2>
      <button hx-post="/api/data/ingest"
              hx-swap="none"
              class="px-3 py-2 bg-green-700 hover:bg-green-600 rounded text-sm w-full">
        Ingest from NT Export
      </button>
      <p class="text-xs text-gray-500 mt-2">Reads new bars from staging folder into data/raw/.</p>
    </div>
```

**Step 5: Add the ingest API endpoint**

In `src/webapp/routes/api.py`, add after the `data_health_html` endpoint:

```python
@router.post("/data/ingest")
def trigger_ingest(cfg: Any = Depends(get_cfg)) -> dict[str, Any]:
    """Trigger NT CSV ingestion from staging folder."""
    from quant.data.ingest import ingest

    if not str(cfg.staging_dir) or str(cfg.staging_dir) == ".":
        raise HTTPException(status_code=400, detail="STAGING_DIR not configured in .env")
    if not cfg.staging_dir.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Staging directory does not exist: {cfg.staging_dir}",
        )

    report = ingest(cfg.staging_dir, cfg.data_dir)
    return {
        "status": "ok",
        "files_updated": report.files_updated,
        "total_new_bars": report.total_new_bars,
        "per_file": {
            k: {"new_bars": fr.new_bars, "status": fr.status, "gaps": len(fr.gaps)}
            for k, fr in report.per_file.items()
        },
    }
```

**Step 6: Run full test suite**

Run: `uv run pytest tests/unit/ tests/integration/ --no-cov -q`
Expected: All tests PASS

**Step 7: Commit**

```bash
git add src/webapp/templates/partials/data_health.html src/webapp/templates/dashboard.html src/webapp/templates/settings.html src/webapp/routes/api.py
git commit -m "feat: add data health dashboard indicator and ingest API endpoint"
```

---

## Task 6: NinjaScript CsvExporter Indicator

**Files:**
- Create: `scripts/ninjatrader/CsvExporter.cs`

This is a standalone C# file. It is NOT part of the Python codebase. It runs inside NinjaTrader 8. No Python tests needed.

**Step 1: Create the NinjaScript indicator**

Create `scripts/ninjatrader/CsvExporter.cs`:

```csharp
#region Using declarations
using System;
using System.Collections.Generic;
using System.IO;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Indicators;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    /// <summary>
    /// Exports OHLCV data for MNQ, MES, MGC across 1m, 5m, 15m timeframes
    /// to CSV files compatible with quant-system-v2.
    ///
    /// Usage:
    ///   1. Add this indicator to ANY chart (e.g., MNQ 1-minute)
    ///   2. Set OutputDirectory to your synced folder (Dropbox/OneDrive/etc.)
    ///   3. It subscribes to all 9 instrument/timeframe combos via AddDataSeries()
    ///   4. On chart load: writes all historical bars (backfill)
    ///   5. On each bar close: appends one line per series
    ///
    /// Output format (matches quant-system-v2 loader):
    ///   datetime,open,high,low,close,volume
    ///   2024-01-02 18:00:00,16850.25,16855.00,16848.50,16852.75,142
    ///
    /// Timestamps are in Eastern Time (NinjaTrader default for CME futures).
    /// </summary>
    public class CsvExporter : Indicator
    {
        // Maps BarsInProgress index -> (ticker, timeframe, filename)
        private Dictionary<int, (string Ticker, string Timeframe, string Filename)> seriesMap;
        private HashSet<int> headerWritten;

        [NinjaScriptProperty]
        [Display(Name = "Output Directory", Description = "Folder for CSV output",
                 Order = 1, GroupName = "Parameters")]
        public string OutputDirectory { get; set; }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Exports OHLCV to CSV for quant-system-v2";
                Name = "CsvExporter";
                Calculate = Calculate.OnBarClose;
                IsOverlay = true;
                OutputDirectory = @"C:\NtExport";
            }
            else if (State == State.Configure)
            {
                seriesMap = new Dictionary<int, (string, string, string)>();
                headerWritten = new HashSet<int>();

                // The primary series (BarsInProgress=0) is whatever chart this
                // indicator is added to. We add 8 more series below.
                // BarsInProgress indices 1-8 correspond to the added series.

                // MNQ
                AddDataSeries("MNQ 03-26", BarsPeriodType.Minute, 1);   // idx 1
                AddDataSeries("MNQ 03-26", BarsPeriodType.Minute, 5);   // idx 2
                AddDataSeries("MNQ 03-26", BarsPeriodType.Minute, 15);  // idx 3

                // MES
                AddDataSeries("MES 03-26", BarsPeriodType.Minute, 1);   // idx 4
                AddDataSeries("MES 03-26", BarsPeriodType.Minute, 5);   // idx 5
                AddDataSeries("MES 03-26", BarsPeriodType.Minute, 15);  // idx 6

                // MGC
                AddDataSeries("MGC 04-26", BarsPeriodType.Minute, 1);   // idx 7
                AddDataSeries("MGC 04-26", BarsPeriodType.Minute, 5);   // idx 8
                AddDataSeries("MGC 04-26", BarsPeriodType.Minute, 15);  // idx 9

                // Map indices to filenames
                // NOTE: Index 0 is the primary chart series — we skip it
                // (or you can map it too if you want the primary chart exported)
                seriesMap[1] = ("MNQ", "1m",  "MNQ_1m.csv");
                seriesMap[2] = ("MNQ", "5m",  "MNQ_5m.csv");
                seriesMap[3] = ("MNQ", "15m", "MNQ_15m.csv");
                seriesMap[4] = ("MES", "1m",  "MES_1m.csv");
                seriesMap[5] = ("MES", "5m",  "MES_5m.csv");
                seriesMap[6] = ("MES", "15m", "MES_15m.csv");
                seriesMap[7] = ("MGC", "1m",  "MGC_1m.csv");
                seriesMap[8] = ("MGC", "5m",  "MGC_5m.csv");
                seriesMap[9] = ("MGC", "15m", "MGC_15m.csv");
            }
            else if (State == State.DataLoaded)
            {
                // Ensure output directory exists
                if (!Directory.Exists(OutputDirectory))
                    Directory.CreateDirectory(OutputDirectory);
            }
        }

        protected override void OnBarUpdate()
        {
            int idx = BarsInProgress;

            // Skip the primary chart series (index 0)
            if (idx == 0 || !seriesMap.ContainsKey(idx))
                return;

            var (ticker, tf, filename) = seriesMap[idx];
            string filePath = Path.Combine(OutputDirectory, filename);

            // Write header on first bar
            if (!headerWritten.Contains(idx))
            {
                // Overwrite file with header (clean start on chart load)
                File.WriteAllText(filePath, "datetime,open,high,low,close,volume\n");
                headerWritten.Add(idx);
            }

            // Format timestamp as YYYY-MM-DD HH:mm:ss (Eastern Time)
            string timestamp = Times[idx][0].ToString("yyyy-MM-dd HH:mm:ss");
            string line = string.Format("{0},{1},{2},{3},{4},{5}\n",
                timestamp,
                Opens[idx][0],
                Highs[idx][0],
                Lows[idx][0],
                Closes[idx][0],
                (long)Volumes[idx][0]);

            File.AppendAllText(filePath, line);
        }
    }
}
```

**Step 2: Verify the file is valid C# syntax**

No automated test. Manual verification:
1. Copy `CsvExporter.cs` to NinjaTrader's custom indicator folder:
   `Documents\NinjaTrader 8\bin\Custom\Indicators\CsvExporter.cs`
2. In NinjaTrader: right-click the NinjaScript Editor → "Compile"
3. Add indicator to any chart, set OutputDirectory to synced folder
4. Verify 9 CSV files appear with correct format

**Important notes for the user:**
- The `AddDataSeries()` contract names (`"MNQ 03-26"`, `"MES 03-26"`, `"MGC 04-26"`) use the current front-month contract. **Update these when contracts roll** (quarterly for MNQ/MES, bimonthly for MGC).
- If you want continuous contracts, use `"MNQ 00-00"` (NinjaTrader's continuous contract syntax) instead.
- The indicator overwrites files on chart load (historical backfill) and appends during live trading. The Python ingester handles deduplication safely.

**Step 3: Commit**

```bash
mkdir -p scripts/ninjatrader
git add scripts/ninjatrader/CsvExporter.cs
git commit -m "feat: add NinjaTrader CsvExporter indicator for OHLCV export"
```

---

## Task 7: CHANGELOG + Verification

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Run full test suite**

Run: `uv run pytest tests/unit/ tests/integration/ --no-cov -q`
Expected: All tests PASS

**Step 2: Run linter**

Run: `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/`
Expected: No errors

**Step 3: Update CHANGELOG.md**

Add at the top of CHANGELOG.md (after line 6):

```markdown
## [2026-03-08] — NinjaTrader Data Pipeline

### Added
- `scripts/ninjatrader/CsvExporter.cs`: NinjaScript indicator that exports OHLCV for
  all 9 instrument/timeframe combos (MNQ/MES/MGC × 1m/5m/15m) to CSV. Runs on a single
  chart via `AddDataSeries()`. Backfills history on load, appends on each bar close.
- `src/quant/data/ingest.py`: Ingestion module — reads NT CSV exports from staging folder,
  validates (NaN rejection, column check), deduplicates by timestamp, detects weekday gaps
  > 24h, appends new bars to `data/raw/`, clears LRU cache.
- `src/quant/data/health.py`: Data health reporting — per-file freshness (fresh/stale/missing),
  bar count, last timestamp, staleness in hours.
- `scripts/ingest_data.py`: CLI wrapper for `make ingest`. Reads `STAGING_DIR` from `.env`.
- `src/webapp/routes/api.py`: `GET /api/data/health` endpoint returns per-file status JSON.
  `GET /api/data/health/html` returns HTML partial for HTMX. `POST /api/data/ingest`
  triggers ingestion from staging folder.
- `src/webapp/templates/partials/data_health.html`: Dashboard data health indicator
  (green/yellow/red per file).
- `src/webapp/templates/dashboard.html`: Added DATA HEALTH section with HTMX auto-refresh.
- `src/webapp/templates/settings.html`: Added NT Ingestion button.
- `src/config/settings.py`: Added `staging_dir` setting.
- `Makefile`: Added `make ingest` target.
- `tests/unit/test_ingest.py`: 10 tests for ingestion (new file, append, dedup, NaN, gaps).
- `tests/unit/test_data_health.py`: 3 tests for health reporting.
```

**Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: update CHANGELOG for NT data pipeline"
```

---

## File Summary

| File | Task | Action |
|------|------|--------|
| `src/config/settings.py` | 1 | Add `staging_dir` field |
| `.env.example` | 1 | Add `STAGING_DIR` |
| `src/quant/data/ingest.py` | 2 | Create ingestion module |
| `tests/unit/test_ingest.py` | 2 | Create ingestion tests (10 tests) |
| `scripts/ingest_data.py` | 3 | Create CLI script |
| `Makefile` | 3 | Add `ingest` target |
| `src/quant/data/health.py` | 4 | Create health module |
| `tests/unit/test_data_health.py` | 4 | Create health tests (3 tests) |
| `src/webapp/routes/api.py` | 4, 5 | Add health + ingest endpoints |
| `tests/integration/test_api.py` | 4 | Add health endpoint test |
| `src/webapp/templates/partials/data_health.html` | 5 | Create health partial |
| `src/webapp/templates/dashboard.html` | 5 | Add DATA HEALTH section |
| `src/webapp/templates/settings.html` | 5 | Add ingest button |
| `scripts/ninjatrader/CsvExporter.cs` | 6 | Create NinjaScript indicator |
| `CHANGELOG.md` | 7 | Record all changes |
