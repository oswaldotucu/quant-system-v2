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
