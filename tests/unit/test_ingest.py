"""Tests for NinjaTrader CSV ingestion."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def _write_csv(path: Path, df: pd.DataFrame) -> None:
    """Helper: write DataFrame to CSV with datetime index."""
    df.to_csv(path, index_label="datetime")


def _make_bars(
    start: str, periods: int, freq: str = "15min", base: float = 15000.0,
) -> pd.DataFrame:
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
