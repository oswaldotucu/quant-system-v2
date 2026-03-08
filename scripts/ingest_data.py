"""Ingest NinjaTrader CSV exports from staging folder into data/raw/.

Usage:
    make ingest                              # uses STAGING_DIR from .env
    make ingest STAGING=/path/to/folder      # override staging dir
    uv run python scripts/ingest_data.py     # uses STAGING_DIR from .env
"""

from __future__ import annotations

import logging
import sys

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
        print("\nGaps detected:")
        for key, gap in all_gaps:
            print(f"  {key}: {gap.gap_hours}h gap ({gap.last_existing} -> {gap.first_new})")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
