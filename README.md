# quant-v2

Micro-futures strategy research platform.
Find, validate, and deploy edges in MNQ, MES, MGC.

## Quick Start

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
make install
make copy-data       # copies CSVs from old project
make verify-data     # confirms data integrity
make test-regression # engine must match Pine Script PF within 5%
make dev             # opens at http://localhost:8080
```

## Workflow

1. Open http://localhost:8080
2. Go to **Strategies** -> Add Strategy -> pick family, tickers, timeframes -> Seed
3. **Dashboard** -> toggle Automation ON
4. Watch the **Pipeline** board as experiments advance through gates
5. Get a notification when a strategy hits FWD_READY
6. Review the checklist, download the Pine Script, go live

## IS/OOS Split (immutable)

```
IS_TRAIN  = 2020-01-01 to 2022-12-31   (Optuna optimization target)
IS_VAL    = 2023-01-01 to 2023-12-31   (Optuna objective: IS-val Sharpe)
OOS       = 2024-01-01 to present      (NEVER touched until OOS_VAL gate)
```

**NEVER optimize on OOS data. First OOS run is final. No re-running with different params.**

## Pipeline (5 gates)

```
SCREEN -> IS_OPT -> OOS_VAL -> CONFIRM -> FWD_READY
  <1min   10-45min   <1min     5-15min    ALERT
```

## Data Reference

Historical CSVs are NOT in git. Place your CSV files in `data/raw/` or set `DATA_SRC`
to the directory containing them, then run `make copy-data`.

## Development

```bash
make check          # lint + typecheck + unit tests
make test-all       # all tests including slow Optuna runs
make docker-up      # run in Docker (production mode)
```

## Architecture

- **FastAPI** + **HTMX** + **Alpine.js** + **Tailwind CDN** — no JS build step
- **vectorbt** — 50x faster backtesting
- **Optuna** — Bayesian hyperparameter search (TPE sampler)
- **SQLite** — single file DB, no server required
- **SSE** — real-time pipeline updates in browser
- **Single Docker service** — 1 container, <700 MB RAM

See `QUANT_V2_REPO_PLAN.md` and `docs/` for full design documentation.
