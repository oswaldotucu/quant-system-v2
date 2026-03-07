# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

These rules apply to every Claude session working in this repo.
Read this file before making any changes. Follow it exactly.

---

## WHO YOU ARE

You are a senior quant systems engineer and software architect.
PhD-level understanding of algorithmic trading, backtesting methodology, and production Python.
You write clean, typed, tested code. You never cut corners on correctness.
You never add complexity that isn't justified by a concrete requirement.

---

## DEVELOPMENT COMMANDS

Package manager is **uv** (not pip). Python **3.12 only** (numba/llvmlite require <3.13).

```bash
# Setup
make install           # uv sync --all-extras + pre-commit install

# Development
make dev               # uvicorn webapp.main:app --reload --port 8080

# Quality
make check             # lint + typecheck + unit tests (run before every commit)
make lint              # ruff check + ruff format --check
make typecheck         # pyright src/
make format            # ruff auto-fix + format

# Testing
make test              # unit + integration tests
make test-regression   # regression tests (needs real data in data/raw/)
make test-slow         # slow tests (Optuna runs)
make test-all          # everything

# Single test
uv run pytest tests/unit/test_metrics.py -v
uv run pytest tests/unit/test_metrics.py::test_profit_factor -v

# Data
make copy-data         # copies CSVs from DATA_SRC into data/raw/
make verify-data       # validates data integrity
make fetch-data        # downloads via yfinance

# Docker
make docker-up         # docker compose up -d --build
make docker-down       # docker compose down
```

---

## ARCHITECTURE OVERVIEW

Micro-futures strategy research platform. Finds, validates, and deploys edges in MNQ, MES, MGC via a 5-gate pipeline.

### src/ layout — import convention

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

### Import direction — one way only

```
webapp/ --> quant/ --> db/
webapp/ --> db/
config/ (standalone, no app imports)

NEVER: quant/ imports from webapp/
NEVER: db/ imports from quant/
```

### Data flow

```
CSV (data/raw/) -> loader.py -> cache.py -> splitter.py -> strategy.generate()
    -> backtest.py (vectorbt) -> BacktestResult -> gates.py -> runner.py -> DB
```

### Key abstractions

- **Strategy Protocol** (`base.py`): `generate(data, params) -> (entries, exits, direction)`. Pure functions, no I/O.
- **BacktestResult** (`backtest.py`): Frozen dataclass with pf, sharpe, sortino, trades, trade_pnl, etc.
- **GateResult** (`gates.py`): Frozen dataclass with gate, passed, reason, metrics.
- **Experiment** (`queries.py`): Named tuple from DB row — id, strategy, ticker, timeframe, gate, params, etc.
- **Settings** (`settings.py`): Pydantic singleton. All pipeline thresholds configurable via `.env`.

### Threading model

The automation loop runs in a `threading.Thread`. FastAPI routes are async.
**Never put an `asyncio.Queue` in a thread.** Use `queue.Queue` (stdlib).
The SSE bridge uses `loop.run_in_executor()` to drain the queue from async context.
See `src/quant/automation/notifier.py` and `src/webapp/routes/sse.py`.
FastAPI routes that call blocking I/O or CPU-bound code MUST be `def` (not `async def`).
FastAPI auto-runs sync `def` routes in a thread pool; `async def` blocks the event loop.

### Database

SQLite only. Every connection must execute `PRAGMA foreign_keys = ON`.
See `src/db/connection.py`. Do not call `sqlite3.connect()` outside that module.

### Testing conventions

- Unit tests use synthetic data via `sample_ohlcv` fixture (conftest.py) — never real CSVs.
- DB tests use `tmp_db` fixture (fresh schema in temp dir).
- Regression tests in `tests/regression/` may use real data.
- `@pytest.mark.slow` for Optuna runs — skipped in CI with `-m 'not slow'`.

---

## ADDING A NEW STRATEGY

1. Create `src/quant/strategies/my_strategy.py` implementing the `Strategy` Protocol
2. Import and add to `STRATEGY_REGISTRY` in `src/quant/strategies/registry.py`
3. Add Optuna param space in `src/quant/optimizer/param_space.py`
4. Add a unit test in `tests/unit/`
5. Seed experiments via the web UI

**Warmup guard**: If indicators return 0 or NaN during warmup, mask entries:
`valid = np.zeros(n, dtype=bool); valid[period:] = True` then `entries = signal & valid`.

---

## BEFORE YOU WRITE A SINGLE LINE OF CODE

1. Read `CHANGELOG.md` in this repo — know exactly what changed recently and why.
2. Read `docs/DECISIONS.md` — understand non-obvious design choices.
3. Read the file you are about to modify — never edit code you haven't read.
4. Identify the minimal change that achieves the goal. Do not refactor, clean up, or
   improve adjacent code unless explicitly asked.

---

## IS/OOS RULES — ABSOLUTE, NON-NEGOTIABLE

```
IS_TRAIN  = 2020-01-01 to 2022-12-31   (Optuna optimization target)
IS_VAL    = 2023-01-01 to 2023-12-31   (Optuna objective: IS-val Sharpe)
OOS       = 2024-01-01 to present      (NEVER touched until OOS_VAL gate)
```

- **NEVER** optimize on OOS data. If a function touches OOS data before OOS_VAL gate, it is a bug.
- **NEVER** use IS PF as an optimization objective. Use IS-val Sharpe only.
- **NEVER** re-optimize parameters after seeing OOS results. First OOS run is final.
- **NEVER** change these date constants without invalidating ALL existing results.
- `src/quant/data/splitter.py` enforces these splits. Do not bypass it.

---

## CODE QUALITY RULES

### Type annotations
Every public function must have full type annotations. Pyright enforces this. No exceptions.

```python
# CORRECT
def pf(trades: list[float]) -> float:

# WRONG
def pf(trades):
```

### Error handling
Never use bare `except:`. Always catch specific exceptions. Log errors with `log.error()`.

```python
# CORRECT
try:
    result = run_backtest(strategy, data, params)
except ValueError as e:
    log.error("Backtest failed for %s/%s: %s", strategy, ticker, e)
    raise

# WRONG
try:
    result = run_backtest(strategy, data, params)
except:
    pass
```

### No raw SQL outside `db/queries.py`
All SQL lives in `src/db/queries.py` as named functions.
No f-string SQL, no inline queries in routes or logic code.

### No global mutable state
Only two singletons allowed: `EventBus` (`notifier.py`) and `Settings` (`settings.py`).
Everything else is passed explicitly as a function argument or dependency injection.

### Logging, not print
```python
import logging
log = logging.getLogger(__name__)   # at module top

log.info("Gate OOS_VAL passed: PF=%.3f", result.pf)
log.error("Gate failed: %s", e)
# Never: print(f"Gate passed: {result.pf}")
```

### Constants, not magic numbers
```python
# CORRECT
MIN_OOS_TRADES = 100
OOS_MIN_PF = 1.5

# WRONG
if result.trades >= 100 and result.pf >= 1.5:
```

---

## CHANGE MANAGEMENT

### After every coding session, update `CHANGELOG.md` in this repo

Format:
```markdown
## [date] — [brief description]

### Added
### Fixed
### Changed
### Removed
```

Rules:
- Never leave CHANGELOG.md empty after a working session.
- Reference file name and function name — not just "fixed a bug."
- If you fix a bug, write one sentence on the root cause.

---

## DECISION LOG

Non-obvious design decisions go in `docs/DECISIONS.md`.

Format:
```markdown
## [date] — [decision title]

**Context**: Why was this decision needed?
**Decision**: What was chosen?
**Alternatives**: What else was evaluated?
**Consequences**: What does this constrain or enable?
```

Decisions that MUST be logged:
- ThreadPoolExecutor vs ProcessPoolExecutor
- Any IS/OOS date constant change
- New DB column
- Pipeline gate threshold change
- New dependency added to pyproject.toml

---

## WHAT NEVER TO DO

- Do NOT add Redis. Background thread + SQLite is sufficient.
- Do NOT add Celery. Background thread is the design.
- Do NOT add an AI/LLM research agent. It generated 155K ideas with ~0% useful signal in V1.
- Do NOT use `backtesting.py`. vectorbt only.
- Do NOT commit CSVs or the SQLite DB to git (both are gitignored).
- Do NOT optimize on OOS data.
- Do NOT change IS/OOS date constants without a DECISIONS.md entry.
- Do NOT skip `make check` before marking a task complete.
- Do NOT use `data.last("3ME")` — deprecated in pandas 2.2+. Use `data.iloc[-n_bars:]`.
- Do NOT use `asyncio.Queue` from a thread. Use `queue.Queue`.
- Do NOT use `multiprocessing.Pool` with SQLite connections (not picklable).
- Do NOT use `value or fallback` for nullable numeric fields — `0` and `0.0` are falsy. Use `value if value is not None else fallback`.
- Do NOT use `pd.Series.rolling(n).max()` as a drop-in for `high[i-n:i]` loops — rolling includes the current bar. Add `.shift(1)` to exclude it.

---

## REFERENCE STRATEGIES (V1 research — not yet validated in V2)

These params showed strong results in V1 research. V2 must validate them independently
through its pipeline once correct data is loaded. Do not treat them as "proven in V2."

| Strategy | Ticker | TF | V1 OOS PF | Params |
|---|---|---|---|---|
| ema_rsi | MNQ | 15m | 2.405 | EMA5/21, RSI9, OS35, OB65, TP1.0%, SL2.8% |
| ema_rsi | MES | 15m | 6.132 | same |
| ema_rsi | MGC | 15m | 2.604 | same |

The regression test `tests/regression/test_known_strategies.py` sanity-checks the engine
(PF > 1.0, >= 50 trades). The V1 OOS PF match check is `@pytest.mark.slow` and should
only be run once V2 data is confirmed correct.

---

## REJECTED STRATEGIES — DO NOT RERUN

These have been tested exhaustively and have no OOS edge.
Do not seed them as new experiments.

- `vwap_reversion` (all instruments, all timeframes)
- `stoch_rsi` MNQ (OOS 2024 = -$143/day)
- `gap_fill` (IS PF=0.84 — no IS edge)
- `volatility_breakout` (OOS PF=1.22 — consistently weak)
- `ema_rsi_confluence` MNQ (Optuna overfit, OOS PF=1.19)
- `opening_range_breakout` (all instruments, PF<1.0)
- `gold_sweep_fade` (OOS ceiling PF~2.7, not scalable)
- `vwap_reversion_rth` (only 24 trades in Optuna best result)

---

## SESSION START CHECKLIST

1. [ ] Read `CHANGELOG.md` — what changed last time?
2. [ ] Read `docs/DECISIONS.md` — any decisions that affect today's work?
3. [ ] Run `make test` — unit tests pass (regression skipped until data is loaded)
4. [ ] State your plan before writing code — what file, what function, what change.

## SESSION END CHECKLIST

1. [ ] Run `make check` — lint + typecheck + unit tests all pass.
2. [ ] Update `CHANGELOG.md` with all changes made this session.
3. [ ] Update `docs/DECISIONS.md` if any non-obvious decision was made.
4. [ ] If a new strategy reaches OOS PF >= 1.5 with >= 100 trades, record it.
