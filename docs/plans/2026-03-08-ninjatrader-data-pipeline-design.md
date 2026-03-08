# NinjaTrader Data Pipeline Design

**Date:** 2026-03-08

**Goal:** Replace Yahoo Finance with NinjaTrader exports as the primary OHLCV data source for backtesting and (later) forward testing.

**Architecture:** NinjaTrader runs a single indicator that writes 9 CSV files (3 instruments × 3 timeframes) to a cloud-synced folder. The quant system ingests from that folder on demand (`make ingest`) or automatically after session close, validating, deduplicating, and merging new bars into `data/raw/`.

---

## Component 1: NinjaScript Indicator (`CsvExporter.cs`)

A single NinjaTrader indicator added to any chart. Internally subscribes to all 9 instrument/timeframe combinations via `AddDataSeries()`.

**Instruments/Timeframes:**
- MNQ: 1m, 5m, 15m
- MES: 1m, 5m, 15m
- MGC: 1m, 5m, 15m

**Behavior:**
- `State.Configure`: 9 × `AddDataSeries()` calls
- `State.DataLoaded`: Creates/overwrites 9 CSV files with headers
- `OnBarUpdate()`: Appends `datetime,open,high,low,close,volume` for whichever series triggered the update
- Timestamps: Eastern Time, format `YYYY-MM-DD HH:mm:ss`
- Output directory: configurable property (defaults to `C:\NtExport\`)
- File naming: `MNQ_1m.csv`, `MES_15m.csv`, etc.

On first load with full chart history, it backfills all historical bars. After that, it appends one line per bar close in real-time.

**Output format (matches existing CSV schema):**
```
datetime,open,high,low,close,volume
2024-01-02 18:00:00,16850.25,16855.00,16848.50,16852.75,142
```

---

## Component 2: Ingestion Module (`src/quant/data/ingest.py`)

New module following existing patterns (pure function, no global state).

**Entry point:**
```python
def ingest(staging_dir: Path, data_dir: Path) -> IngestReport
```

**Steps per file:**
1. Read staging CSV, parse timestamps as ET
2. Read existing `data/raw/` CSV
3. Find the last timestamp in existing data
4. Filter staging to only bars after that timestamp (new bars)
5. Validate new bars: OHLCV columns present, no NaN, timestamps ascending, no future dates
6. Detect gaps: if first new bar is >24h after last existing bar on a weekday, flag it
7. Append valid bars to `data/raw/` CSV
8. Clear LRU cache for that ticker/timeframe

**Data structures:**
```python
@dataclass
class GapInfo:
    last_existing: str    # timestamp
    first_new: str        # timestamp
    gap_hours: float

@dataclass
class FileReport:
    new_bars: int
    rejected_bars: int
    gaps: list[GapInfo]
    status: str           # "updated", "up_to_date", "error"

@dataclass
class IngestReport:
    files_updated: int
    total_new_bars: int
    per_file: dict[str, FileReport]  # keyed by "MNQ_1m" etc.
```

---

## Component 3: CLI Entry Point (`scripts/ingest_data.py`)

Thin wrapper for `make ingest`:
```bash
make ingest                                  # uses STAGING_DIR from .env
make ingest STAGING=/path/to/synced/folder   # override
```

Reads `STAGING_DIR` from `.env` (or CLI arg), calls `ingest()`, prints the report summary.

---

## Component 4: Settings

New settings in `.env` / `src/config/settings.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `STAGING_DIR` | `""` | Path to synced NT export folder |
| `INGEST_AUTO` | `false` | Enable daily auto-ingest in AutomationLoop |
| `INGEST_TIME` | `17:30` | ET time to trigger auto-ingest (after CME maintenance) |

---

## Component 5: AutomationLoop Integration (deferred)

When `INGEST_AUTO=true`, the `AutomationLoop` checks once per tick whether:
- Current time is past `INGEST_TIME` ET
- Ingestion hasn't run today

If both true, runs `ingest()` before processing experiments. This ensures experiments always run on fresh data.

**Not built in this iteration** — manual `make ingest` only for now.

---

## Component 6: Data Health API + Dashboard

**Endpoint:** `GET /api/data/health`

Returns per-file status:
- Last bar timestamp
- Total bar count
- Gaps flagged during last ingest
- Staleness (hours since last bar)

**Dashboard indicator** per instrument/timeframe:
- Green: fresh (< 24h stale), no gaps
- Yellow: > 24h stale or has gaps
- Red: file missing

---

## What This Does NOT Include

- Near-real-time file watching (deferred to forward testing feature)
- Alternative data sources beyond NT (Yahoo Finance stays as fallback)
- Automated NT restart or health monitoring
- Bar aggregation (NT handles 1m → 5m → 15m natively via AddDataSeries)

---

## Decisions

- **Staging folder pattern**: NT writes to a cloud-synced folder, quant system reads from it. This decouples NT (Windows) from the quant system (Mac). No SSH, rsync, or push mechanism needed.
- **Overwrite on load, append on bar close**: The NinjaScript overwrites files on chart load (ensures clean state with full history) and appends during live trading. The ingester handles deduplication, so re-exporting history is safe.
- **ET timestamps**: NinjaTrader defaults to Eastern Time for CME futures. The existing loader expects ET. No conversion needed.
- **Gap detection without blocking**: Gaps are logged and flagged in the dashboard, but ingestion proceeds. Gaps are expected (holidays, half-days, maintenance windows).
