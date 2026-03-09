# Architecture Overview

Micro-futures strategy research platform. Finds, validates, and deploys edges in MNQ, MES, MGC via a 5-gate pipeline.

## src/ layout — import convention

Uses `src/` layout (`[tool.setuptools.package-dir] "" = "src"`). Packages are imported
as `config.*`, `db.*`, `quant.*`, `webapp.*` — **never** `src.config.*`.

```
src/
├── config/            # Settings (pydantic-settings), instrument constants
│   ├── settings.py    # Settings singleton — all config via .env
│   └── instruments.py # CONTRACT_MULT, TICKERS, TIMEFRAMES, BARS_PER_DAY
├── db/                # SQLite layer — all SQL lives here
│   ├── connection.py  # Thread-local connections (get_conn/close_conn)
│   ├── queries.py     # Named SQL functions (Experiment namedtuple)
│   ├── migrations.py  # Integer-versioned ALTER TABLE runner
│   └── schema.sql     # 3-table schema + trigger + CHECK constraints
├── quant/
│   ├── data/          # Load, cache, split, validate OHLCV data
│   │   ├── loader.py  # CSV -> DataFrame (timestamps are ET, not UTC)
│   │   ├── cache.py   # get_ohlcv() — in-memory cache
│   │   ├── splitter.py# is_train(), is_val(), is_full(), oos() — enforces date splits
│   │   └── validate.py
│   ├── engine/        # Backtesting and analytics (all pure functions)
│   │   ├── backtest.py# run_backtest() -> BacktestResult (vectorbt wrapper)
│   │   ├── metrics.py # pf, sharpe, sortino, calmar, max_drawdown
│   │   ├── monte_carlo.py
│   │   ├── walk_forward.py
│   │   └── sensitivity.py
│   ├── strategies/    # Signal generators (Strategy Protocol)
│   │   ├── base.py    # Strategy Protocol: generate(data, params) -> (entries, exits, direction)
│   │   ├── registry.py# STRATEGY_REGISTRY dict + get_strategy(name)
│   │   ├── ema_rsi.py, adx_ema.py, supertrend.py, macd_trend.py, ...
│   ├── optimizer/     # Optuna hyperparameter search
│   │   ├── search.py  # run_optuna() — objective is IS-val Sharpe
│   │   ├── objective.py
│   │   └── param_space.py # Per-strategy Optuna param spaces
│   ├── pipeline/      # 5-gate validation pipeline
│   │   ├── gates.py   # SCREEN -> IS_OPT -> OOS_VAL -> CONFIRM -> FWD_READY
│   │   └── runner.py  # run_next_gate() — advances experiment + updates DB
│   └── automation/    # Background processing
│       ├── loop.py    # AutomationLoop (ThreadPoolExecutor in threading.Thread)
│       ├── notifier.py# EventBus singleton (queue.Queue, NOT asyncio.Queue)
│       ├── seeder.py  # Creates initial experiments
│       ├── pine_generator.py
│       └── checklist_generator.py
└── webapp/            # FastAPI + HTMX + Alpine.js + Tailwind CDN
    ├── main.py        # create_app(), lifespan (DB init, automation start)
    ├── deps.py        # FastAPI dependencies
    ├── routes/
    │   ├── pages.py   # HTML page routes (Jinja2 templates)
    │   ├── api.py     # JSON API routes
    │   └── sse.py     # Server-Sent Events (real-time pipeline updates)
    ├── templates/     # 8 Jinja2 templates
    └── static/        # sse_client.js, charts.js, custom.css
```

## Import direction — one way only

```
webapp/ --> quant/ --> db/
webapp/ --> db/
config/ (standalone, no app imports)

NEVER: quant/ imports from webapp/
NEVER: db/ imports from quant/
```

## Data flow

```
CSV (data/raw/) -> loader.py -> cache.py -> splitter.py -> strategy.generate()
    -> backtest.py (vectorbt) -> BacktestResult -> gates.py -> runner.py -> DB
```

## Key abstractions

- **Strategy Protocol** (`base.py`): `generate(data, params) -> (entries, exits, direction)`. Pure functions, no I/O.
- **BacktestResult** (`backtest.py`): Frozen dataclass with pf, sharpe, sortino, trades, trade_pnl, etc.
- **GateResult** (`gates.py`): Frozen dataclass with gate, passed, reason, metrics.
- **Experiment** (`queries.py`): Named tuple from DB row — id, strategy, ticker, timeframe, gate, params, etc.
- **Settings** (`settings.py`): Pydantic singleton. All pipeline thresholds configurable via `.env`.

## Threading model

The automation loop runs in a `threading.Thread`. FastAPI routes are async.
**Never put an `asyncio.Queue` in a thread.** Use `queue.Queue` (stdlib).
The SSE bridge uses `loop.run_in_executor()` to drain the queue from async context.
See `src/quant/automation/notifier.py` and `src/webapp/routes/sse.py`.
FastAPI routes that call blocking I/O or CPU-bound code MUST be `def` (not `async def`).
FastAPI auto-runs sync `def` routes in a thread pool; `async def` blocks the event loop.

## Database

SQLite only. Every connection must execute `PRAGMA foreign_keys = ON`.
See `src/db/connection.py`. Do not call `sqlite3.connect()` outside that module.

## Testing conventions

- Unit tests use synthetic data via `sample_ohlcv` fixture (conftest.py) — never real CSVs.
- DB tests use `tmp_db` fixture (fresh schema in temp dir).
- Regression tests in `tests/regression/` may use real data.
- `@pytest.mark.slow` for Optuna runs — skipped in CI with `-m 'not slow'`.
