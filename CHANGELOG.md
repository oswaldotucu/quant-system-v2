# CHANGELOG — quant-system-v2

All changes to this codebase are recorded here.
Format: [date] | component | what changed | why.

---

## [2026-03-09] — SCREEN Gate OOS Fix + Warmup Guards + Lint Cleanup

### Fixed
- **SCREEN gate OOS data leak** — `gates.py:111` used `data.iloc[-n_bars:]` on full dataset,
  touching 2024+ OOS data before OOS_VAL gate. Fixed to use `is_full(data).iloc[-n_bars:]`.
- **6 strategy warmup guards** — Added `valid[warmup:] = True` masks to prevent false entries
  during indicator convergence period:
  - `ema_rsi.py` — warmup = max(ema_slow, rsi_period)
  - `adx_ema.py` — warmup = 2 * adx_period (ADX needs double smoothing)
  - `macd_trend.py` — warmup = macd_slow + macd_signal
  - `supertrend.py` — warmup = atr_period + 1 (prevents synthetic flip from zero-init)
  - `rsi2_reversal.py` — warmup = max(rsi_period, trend_ema)
  - `rsi_mean_reversion.py` — warmup = rsi_period
- **Ruff lint cleanup** — Resolved ~336 lint errors: B904 (`raise from e`), F841 (unused vars),
  B007 (unused loop vars), S603/S607 noqa for osascript. Added per-file-ignores for tests
  (S101, S108) and global ignores (B008, ANN401).
- **Ruff format** — Reformatted 41 files for consistency.
- **Verified Round 2 bug fixes** — All 6 fixes confirmed in place: leaderboard sort key None
  handling, N+1 dashboard queries, Bollinger warmup guard, `trigger_fetch` async-to-sync,
  Donchian O(n^2)-to-O(n).

### Changed
- **CLAUDE.md restructured** — Added orchestrator rule (all implementation via sub-agents),
  skill development exception, CLAUDE.md hygiene rule. Extracted verbose sections to
  `docs/dev-commands.md`, `docs/architecture.md`, `docs/code-quality.md`, `docs/templates.md`.
  Reduced from 439 to 237 lines (46% reduction).
- **pyproject.toml ruff config** — Added B008, ANN401 to global ignores; S101, S108
  per-file-ignores for tests.

### Added
- `docs/dev-commands.md` — Full development command reference.
- `docs/architecture.md` — Directory tree, imports, data flow, abstractions, threading.
- `docs/code-quality.md` — Type annotations, error handling, logging, constants patterns.
- `docs/templates.md` — CHANGELOG and DECISIONS.md format templates.

### Pipeline Run — Full 13-Strategy Sweep (15m, micro futures)
- **74 experiments** seeded (13 strategies × 3 tickers × 15m, including re-seeds for prior rejections).
- **SCREEN gate**: 40 rejected (too few trades with default params), 34 advanced to IS_OPT.
- **IS_OPT (Optuna 300 trials)**: 32 rejected ("no IS edge" — all 300 trials returned 0), 2 passed:
  - `rsi2_reversal` MNQ: IS-val Sharpe=2.712, IS-val PF=3.577
  - `supertrend` MES: IS-val Sharpe=2.385, IS-val PF=44.928
- **OOS_VAL**: Both failed:
  - `rsi2_reversal` MNQ: OOS PF=1.249 (need≥1.5), 88 trades (need≥100), DD=-4.6%
  - `supertrend` MES: OOS PF=0.564, 27 trades, DD=-88.4% (classic overfit)
- **Conclusion**: Warmup guards + proper IS/OOS splits eliminated phantom edges from V1.
  The V1 ema_rsi "reference" (OOS PF 2.4-6.1) couldn't find ANY valid Optuna trials in V2,
  confirming those results were driven by unconverged indicator artifacts.

---

## [2026-03-08] — NinjaTrader Data Pipeline + Mini Futures Support

### Added
- `scripts/ninjatrader/CsvExporter.cs`: NinjaScript indicator that exports OHLCV for
  all 18 instrument/timeframe combos (MNQ/MES/MGC/NQ/ES/GC x 1m/5m/15m) to CSV.
  Runs on a single chart via `AddDataSeries()`. Backfills history on load, appends on
  each bar close. Outputs to `micro/` and `mini/` subfolders matching `data/raw/` layout.
- `src/config/instruments.py`: Added mini futures (NQ, ES, GC) — `TICKER_CLASS` mapping,
  `CONTRACT_MULT`, `MARGIN_EST`, `YF_SYMBOLS`, `MINI_TICKERS`. Added `ticker_data_dir()`
  helper for resolving `data_dir/micro/` or `data_dir/mini/` from ticker name.
- `src/quant/data/ingest.py`: Ingestion module — reads NT CSV exports from staging folder,
  validates (NaN rejection, column check), deduplicates by timestamp, detects weekday gaps
  > 24h, appends new bars to `data/raw/{micro,mini}/`, clears LRU cache.
- `src/quant/data/health.py`: Data health reporting — per-file freshness (fresh/stale/missing),
  bar count, last timestamp, staleness in hours. Covers all 18 files.
- `scripts/ingest_data.py`: CLI wrapper for `make ingest`. Reads `STAGING_DIR` from `.env`.
- `src/webapp/routes/api.py`: `GET /api/data/health` endpoint returns per-file status JSON.
  `GET /api/data/health/html` returns HTML partial for HTMX. `POST /api/data/ingest`
  triggers ingestion from staging folder.
- `src/webapp/templates/partials/data_health.html`: Dashboard data health indicator
  (green/yellow/red per file), grouped by MICRO and MINI sections.
- `src/webapp/templates/dashboard.html`: Added DATA HEALTH section with HTMX auto-refresh.
- `src/webapp/templates/settings.html`: Added NT Ingestion button.
- `src/config/settings.py`: Added `staging_dir` setting.
- `Makefile`: Added `make ingest` target.
- `tests/unit/test_ingest.py`: 11 tests for ingestion (new file, append, dedup, NaN, gaps,
  mini subfolder).
- `tests/unit/test_data_health.py`: 3 tests for health reporting.

### Changed
- `src/quant/data/loader.py`: Updated path resolution to use `ticker_data_dir()` for
  subfolder support (`data/raw/micro/` or `data/raw/mini/`).
- `src/quant/data/fetcher.py`: Updated Yahoo Finance path resolution to use `TICKER_CLASS`
  subfolders. Creates subdirectories automatically.
- `scripts/verify_data.py`: Updated to check all 18 files across `micro/` and `mini/`
  subfolders.

---

## [2026-03-07] — Pipeline Observability + Hardening

### Added
- `src/quant/pipeline/runner.py`: Gate timing via `time.monotonic()`. Every gate run now
  logs elapsed time and stores `elapsed_s` in metrics. Helps identify slow gates.
- `src/quant/pipeline/gates.py`: Rich rejection reasons. IS_OPT, OOS_VAL, and CONFIRM
  reason strings now include threshold values (e.g., `PF=0.82 (need>=1.5)`) and per-check
  PASS/FAIL labels for CONFIRM's 5 sub-checks.
- `src/quant/optimizer/search.py`: Optuna progress logging every 50 trials. Logs trial
  count, complete/pruned split, and best objective value.
- `src/quant/automation/loop.py`: SSE events enriched with `strategy`, `ticker`,
  `timeframe`, `elapsed_s`. Dynamic timeout: 7200s for IS_OPT ticks, 300s otherwise.
  TimeoutError handling added. Error logging includes full experiment context.
- `src/webapp/templates/experiment_detail.html`: Gate Results section showing SCREEN,
  IS_OPT, and CONFIRM metrics already stored in DB.
- `tests/unit/test_db.py`: Test for `_safe_commit` rollback behavior.

### Fixed
- `src/db/queries.py`: All 6 `c.commit()` calls replaced with `_safe_commit(c)` which
  calls `rollback()` on `sqlite3.Error` before re-raising. Prevents silent partial state
  on disk-full or lock errors.
- `src/webapp/routes/api.py`: `download_pine` and `download_checklist` changed from
  `async def` to `def`. They do synchronous file I/O and were blocking the event loop.
- `src/webapp/routes/api.py`: `seed_experiments` now validates strategy name against
  `STRATEGY_REGISTRY`, tickers against `TICKERS`, and timeframes against `TIMEFRAMES`
  before DB insert. Returns 400 with details on invalid input.

---

## [2026-03-07] — 5 New Strategy Families

### Added
- `src/quant/strategies/volume_breakout.py`: Volume Breakout strategy. High-volume bar
  breaks session high/low → momentum continuation. Family: price_action.
- `src/quant/strategies/mtf_ema_alignment.py`: Multi-Timeframe EMA Alignment. 15m EMA
  crossover confirmed by 1h EMA slope via internal resampling. Family: multi_timeframe.
- `src/quant/strategies/regime_switch.py`: Regime Switch strategy. ATR percentile classifies
  trending/ranging regime, applies EMA crossover (trend) or RSI+BB (reversion). Family: regime_aware.
- `src/quant/strategies/session_momentum.py`: Session Momentum strategy. Opening range
  breakout with time-bounded trade window and range size filter. Family: event_driven.
- `src/quant/strategies/rsi_bollinger_filtered.py`: RSI + Bollinger Band mean-reversion
  with ATR regime filter. Only trades in low-volatility regimes. Family: mean_reversion.
- `src/quant/optimizer/param_space.py`: Optuna param spaces for all 5 new strategies.
- `src/quant/strategies/registry.py`: All 5 new strategies registered (total: 13 strategies).
- `tests/unit/test_volume_breakout.py`: 10 tests.
- `tests/unit/test_mtf_ema_alignment.py`: 10 tests.
- `tests/unit/test_regime_switch.py`: 10 tests.
- `tests/unit/test_session_momentum.py`: 10 tests.
- `tests/unit/test_rsi_bollinger_filtered.py`: 10 tests.
- `docs/plans/2026-03-07-strategy-expansion-design.md`: Design doc for strategy expansion.
- `docs/plans/2026-03-07-strategy-expansion.md`: Implementation plan.

---

## [2026-03-07] — Fix Code Review Findings (Round 2)

### Fixed
- **HIGH** `src/webapp/routes/api.py`: Leaderboard sort key used `getattr(e, sort_by) or fallback`,
  which treats `0` and `0.0` as falsy. `oos_trades=0` sorted as `float("-inf")` and
  `oos_max_dd_pct=0.0` as `float("inf")`. Replaced with explicit `is None` check.
- **MEDIUM** `src/webapp/routes/pages.py`: Dashboard ran 5 separate `list_experiments_by_gate()`
  queries (loading full 28-field Experiment objects) just to count them. Replaced with single
  `count_experiments_by_gate()` GROUP BY query that already existed in `db/queries.py`.
- **MEDIUM** `src/quant/strategies/bollinger_squeeze.py`: First `bb_period - 1` bars had SMA=0
  and std=0, making bandwidth=0 which is always < squeeze_threshold. This caused warmup bars
  to register as "in squeeze", producing false long entries when `close > 0` (always true).
  Added `valid = np.arange(n) >= bb_period` warmup guard on entry signals.
- **LOW** `src/webapp/routes/api.py`: `trigger_fetch` was `async def` but calls `fetch_all()`
  which does blocking network I/O (Yahoo Finance). Changed to `def` so FastAPI auto-runs
  it in a thread pool (same pattern applied to `run_lab_backtest` in prior review).
- **LOW** `src/quant/strategies/donchian_breakout.py`: Replaced O(n × entry_period) Python loop
  with `pd.Series.rolling().max().shift(1)` — O(n) internally. `.shift(1)` is required because
  rolling includes the current bar but the original loop used `high[i-period:i]` (excludes it).

---

## [2026-03-06] — Web Dashboard: Experiment Detail Page, Stats Bar, Health Endpoint

### Added
- `src/webapp/templates/experiment_detail.html`: Comprehensive experiment detail page with
  gate progress bar, color-coded pass/fail metrics for every gate (SCREEN, IS_OPT, OOS_VAL,
  CONFIRM), optimized parameters table, quarterly win rates, Monte Carlo results (p_ruin,
  p_positive), walk-forward windows, portfolio correlation, OOS equity curve chart, and
  action buttons (approve/reject/download Pine/checklist).
- `src/webapp/templates/partials/stats_bar.html`: HTMX-loaded partial showing total experiment
  count and per-gate breakdown (SCREEN, IS_OPT, OOS_VAL, CONFIRM, FWD_READY, DEPLOYED,
  REJECTED) with color-coded links to the pipeline filter view.
- `src/db/queries.py`: `count_experiments_by_gate()` — aggregates experiment counts grouped
  by gate. `get_last_activity()` — returns most recent `updated_at` timestamp across all
  experiments. `count_total_experiments()` — returns total experiment count.
- `src/webapp/routes/api.py`: `GET /api/stats` — JSON endpoint returning total and per-gate
  experiment counts. `GET /api/stats/html` — HTML fragment endpoint for HTMX stats bar.
  `GET /api/health` — system health endpoint returning status, db_size_mb, total_experiments,
  automation_running, last_activity, and uptime_seconds.
- `src/webapp/main.py`: Tracks `app.state.start_time` at startup for uptime calculation.

### Changed
- `src/db/queries.py`: `Experiment` dataclass expanded from 11 to 28 fields to include all
  DB columns: screen_pf, screen_trades, is_sharpe, is_pf, sens_min_pf, oos_max_dd,
  quarterly_wr, p_ruin, p_positive, wf_windows, cross_confirmed, max_corr, notes,
  pine_path, checklist_path, created_at, updated_at. `_row_to_experiment()` updated to
  populate all fields from the DB row.
- `src/webapp/routes/pages.py`: `experiment_detail()` route now passes `best_trial` and
  `trial_count` to template, renders `experiment_detail.html` instead of `experiment.html`.
  Fixed pre-existing pyright type error (replaced `Response(404)` with `HTTPException(404)`).
- `src/webapp/templates/dashboard.html`: Added HTMX-loaded stats bar at top of dashboard,
  auto-refreshes every 30 seconds via `GET /api/stats/html`.

---

## [2026-03-06] — 3 New Strategies + Dashboard Improvements + Integration

### Added
- `src/quant/strategies/bollinger_squeeze.py`: Bollinger Band Squeeze breakout strategy.
  Detects low-volatility compression (bandwidth < threshold for N consecutive bars), enters
  on breakout above upper band (long) or below lower band (short). Family: breakout.
- `src/quant/strategies/donchian_breakout.py`: Donchian Channel Breakout (Turtle Trader).
  Enters on new N-period highs (long) or lows (short), with optional EMA trend filter.
  Family: trend_following.
- `src/quant/strategies/keltner_channel.py`: Keltner Channel momentum strategy. ATR-based
  bands around EMA, enters when price closes outside channel with EMA slope confirmation.
  Uses shared `atr_wilder()` from `indicators.py`. Family: trend_following.
- `src/quant/optimizer/param_space.py`: Optuna param spaces for all 3 new strategies.
- `src/quant/strategies/registry.py`: All 3 new strategies registered (total: 8 strategies).
- `tests/unit/test_bollinger_squeeze.py`: 8 tests covering signal generation, direction
  correctness, edge cases (empty/single bar), and default params validation.
- `tests/unit/test_donchian_breakout.py`: 8 tests including trend filter reduction
  verification and channel breakout direction correctness.
- `tests/unit/test_keltner_channel.py`: 7 tests covering empty data, direction matching,
  and signal generation.
- `src/webapp/routes/pages.py`: `/experiment/{exp_id}` detail page with OOS results, params,
  and equity chart.
- `src/webapp/templates/experiment_detail.html`: Experiment detail page with 3-panel grid
  (identity, OOS results, params), error display, and equity chart canvas.
- `src/webapp/routes/api.py`: `/api/stats` pipeline stats endpoint, `/api/health` system
  health endpoint with DB size, uptime, automation status, and last activity.
- `src/db/queries.py`: `count_experiments_by_gate()`, `count_total_experiments()`,
  `get_last_activity()` aggregate query functions.

### Fixed
- `src/webapp/routes/pages.py`: Template reference `experiment_detail.html` now matches
  actual template filename (was `experiment.html` → renamed to `experiment_detail.html`).

### Removed
- `src/quant/optimizer/param_space.py`: Removed stale param space entries for
  `rsi_mean_reversion` and `volatility_breakout` (both removed from registry in prior fix).
- 5 empty git worktrees from agent execution.

---

## [2026-03-06] — Leaderboard Page and API

### Added
- `src/db/queries.py`: `list_experiments_past_gate(min_gate)` — returns experiments at
  OOS_VAL, CONFIRM, FWD_READY, or DEPLOYED gates, ordered by `oos_pf` descending.
  Uses `_LEADERBOARD_GATES` tuple for gate ordering validation.
- `src/webapp/routes/pages.py`: `GET /leaderboard` page route rendering `leaderboard.html`.
- `src/webapp/routes/api.py`: `GET /api/leaderboard` JSON endpoint with `?sort_by=`
  query parameter. Supports sorting by `oos_pf`, `oos_trades`, `oos_sharpe`,
  `oos_sortino`, `oos_calmar`, `daily_pnl`, `oos_max_dd_pct`. Returns all OOS metrics.
- `src/webapp/templates/leaderboard.html`: Leaderboard table with client-side sortable
  columns (Alpine.js). Columns: Rank, Strategy, Ticker, TF, Gate, OOS PF, Trades,
  Sharpe, $/day, Max DD%. Color coding: green (PF >= 2.0), yellow (1.5-2.0),
  red (< 1.5). Gate badges colored by stage (DEPLOYED=green, FWD_READY=blue).
- `src/webapp/templates/base.html`: Added "Leaderboard" nav link between Pipeline and
  Strategies.

### Changed
- `src/db/queries.py`: `Experiment` dataclass expanded with `oos_sharpe`, `oos_sortino`,
  `oos_calmar`, `oos_max_dd_pct` fields (previously only had `oos_pf`, `oos_trades`,
  `daily_pnl`). `_row_to_experiment()` updated to populate these fields from DB rows.

---

## [2026-03-06] — Fix Code Review Findings (2 Critical, 6 High, 8 Medium)

### Fixed
- **CRITICAL** `src/quant/optimizer/objective.py`: Added `trial.set_user_attr()` calls for
  `is_train_pf` and `is_val_pf`. Without these, `search.py` always read 0.0 for
  `best_is_val_pf`, causing `gates.py` IS_OPT check `best_is_val_pf > 1.2` to always fail.
  No experiment could ever pass IS_OPT. Pipeline was non-functional.
- **CRITICAL** `src/quant/strategies/adx_ema.py` and `supertrend.py`: ATR Wilder seed used
  `.sum()` instead of `.mean()`, inflating initial ATR by `period`x (e.g., 14x for ADX).
  Distorted SuperTrend bands and ADX values during warmup period. Fixed in `_atr_wilder()`,
  `_adx._smooth()`, and `_supertrend()`.
- **HIGH** `src/quant/automation/notifier.py`: `notify_macos()` now escapes `"` and `\` in
  title/message before AppleScript interpolation. Previously, double quotes in strategy
  names could enable shell injection via `osascript`.
- **HIGH** `src/db/queries.py`: `advance_experiment()` now validates update column names
  against `_UPDATABLE_COLUMNS` frozenset. Previously, dict keys were interpolated directly
  into SQL column names with no allowlist (linter suppressed via `# noqa: S608`).
- **HIGH** `src/quant/engine/backtest.py`: Commission fee uses `data["close"].median()`
  instead of `data["close"].iloc[0]`. Over IS period (2020-2023), MNQ ranged 9000-22000,
  causing up to 60% commission error on early trades.
- **HIGH** `src/webapp/routes/api.py`: `run_lab_backtest` and `experiment_equity` changed
  from `async def` to `def`. These routes call CPU-bound `run_backtest()` which would block
  the entire FastAPI event loop, freezing SSE and all other requests.
- **HIGH** `src/quant/automation/notifier.py`: Added `threading.Lock` to `EventBus`
  `subscribe/unsubscribe/emit`. `_subscribers` list was mutated from multiple threads
  (async context + automation thread) without synchronization.
- **MEDIUM** `src/quant/engine/backtest.py`: Changed `freq="1T"` to `freq="1min"`. `"1T"`
  is deprecated in pandas 2.2+.
- **MEDIUM** `src/quant/pipeline/gates.py`: Removed duplicate `BacktestResult` import
  (line 27 shadowed line 26). Removed unused `get_best_trial` import.
- **MEDIUM** `src/quant/pipeline/gates.py`: IS_OPT thresholds (0.5, 1.2), CONFIRM max_corr
  (0.6), and cross_min_trades (50) extracted to `Settings` as `is_opt_min_sharpe`,
  `is_opt_min_pf`, `confirm_max_corr`, `cross_min_trades`.
- **MEDIUM** `src/quant/pipeline/gates.py`: CONFIRM gate now reuses stored `trade_pnl`
  from OOS_VAL (via `load_trade_pnl()`) for Monte Carlo and portfolio correlation, instead
  of re-running the full OOS backtest. Falls back to fresh backtest if no stored data.
- **MEDIUM** `src/quant/automation/loop.py`: `_tick()` uses `as_completed(futures)` instead
  of sequential iteration. Slow IS_OPT experiments (45 min) no longer block event emission
  for faster experiments that already completed.

### Refactored
- `src/quant/strategies/indicators.py`: New shared module with `true_range()`,
  `wilders_smooth()`, and `atr_wilder()`. Eliminates 3x duplication of Wilder's ATR
  across `adx_ema.py` (2 copies: `_atr_wilder` + `_smooth`) and `supertrend.py` (inline).
  Future ATR bugs need only one fix.
- `src/quant/pipeline/gates.py`: Added `log.warning()` when CONFIRM gate falls back to
  re-running OOS backtest (stored `trade_pnl` not found). Makes the fallback debuggable.

### Removed
- `src/quant/strategies/registry.py`: Removed `volatility_breakout` and `rsi_mean_reversion`
  from `STRATEGY_REGISTRY`. Both are on the CLAUDE.md rejected/unvalidated list.
- `src/db/queries.py`: Removed dead `save_trade_pnl()` function (never called; `trade_pnl`
  flows through `advance_experiment` updates dict instead).

### Added
- `src/config/settings.py`: 4 new configurable thresholds: `is_opt_min_sharpe`,
  `is_opt_min_pf`, `confirm_max_corr`, `cross_min_trades`.
- `docs/DECISIONS.md`: Entry for SCREEN gate threshold relaxation.
- `tests/unit/test_db.py`: `test_advance_experiment_with_trade_pnl` (replaces removed
  `test_save_and_load_trade_pnl`), `test_advance_experiment_rejects_invalid_columns`.

---

## [2026-03-06] — Calibrate Strategy Params for 15m Resolution + Make Schema Idempotent

### Fixed
- All 7 strategy `default_params()`: TP/SL was 0.5-2.8% (multi-day moves for MNQ). Changed to
  0.15% TP / 0.3% SL (~37 pts MNQ, ~9 pts MES — intraday scale). Root cause: V1 params were
  calibrated against incorrect NinjaTrader data where price levels were different.
- `src/quant/strategies/adx_ema.py`: `adx_threshold` 25→15 (too strict for 15m, filtered most signals).
- `src/quant/strategies/supertrend.py`: `multiplier` 3.0→1.5, `atr_period` 10→7 (tighter bands for 15m).
- `src/quant/strategies/macd_trend.py`: `trend_ema` 100→50 (100-period EMA on 15m = ~25 hours lag).
- `src/quant/strategies/rsi2_reversal.py`: `trend_ema` 100→50 (same lag issue).
- `src/quant/optimizer/param_space.py`: TP/SL search ranges were 0.5-4.0% for all strategies.
  Changed to 0.05-0.5% TP and 0.1-0.8% SL. Without this fix, Optuna would only search in the
  "too wide" parameter space and never find intraday-scale exits.
- `src/db/schema.sql`: Added `IF NOT EXISTS` to all CREATE TABLE/INDEX/TRIGGER statements.
  Server crash on restart when DB already exists (`table strategies already exists`).

### Changed
- `.env`: `SCREEN_MIN_PF` 1.3→0.0, `SCREEN_MIN_TRADES` 30→5. SCREEN uses default params, not
  optimized ones. PF<1.0 with defaults is expected — Optuna's job is to find profitable params.
  Old thresholds rejected 11/12 strategies before they reached Optuna.

### Result
- 13 experiments passed SCREEN and entered IS_OPT (Optuna optimization).
- adx_ema MNQ passed SCREEN with PF=1.72, 29 trades on first attempt (before threshold change).
- Pipeline is running end-to-end for the first time.

---

## [2026-03-06] — Make System Functional End-to-End

### Fixed
- `src/webapp/routes/api.py`: `seed_experiments()` — replaced `SeedRequest(BaseModel)` with
  `Form(...)` params. HTMX sends `application/x-www-form-urlencoded` but FastAPI requires
  JSON body for Pydantic models. Every seed attempt from the UI returned 422.
- `src/webapp/routes/api.py`: `run_lab_backtest()` — same HTMX encoding fix. Also changed
  return type from JSON to HTML (`TemplateResponse`) so `hx-swap="innerHTML"` works.
- `tests/integration/test_api.py`: Fixed settings singleton leak between unit and integration
  tests. `get_settings()` cached the `DB_PATH` from the prior unit test, causing
  `sqlite3.OperationalError: table strategies already exists` in integration tests.

### Added
- `src/webapp/templates/partials/lab_results.html`: New HTML fragment for lab backtest
  results — styled grid with PF, trades, win_rate, sharpe, $/day, max_dd, total_return.
  Color-coded green/red based on thresholds.
- `src/db/migrations.py`: Migration v1 — `ALTER TABLE experiments ADD COLUMN trade_pnl TEXT`.
  Stores JSON-encoded per-trade P&L for portfolio correlation analysis.
- `src/db/queries.py`: `save_trade_pnl()` and `load_trade_pnl()` for round-trip storage.
- `src/quant/pipeline/gates.py`: `_run_oos_val()` now stores `trade_pnl` in metrics.
  `_check_portfolio_correlation()` — implemented actual Pearson correlation logic using
  `load_trade_pnl()` for deployed experiments. Was previously stubbed (always returned 0.0).
- `src/webapp/routes/api.py`: 5 new endpoints:
  - `GET /api/pine/{exp_id}` — generates and downloads Pine Script
  - `GET /api/checklist/{exp_id}` — generates and downloads forward-test checklist
  - `POST /api/experiments/{exp_id}/approve` — moves FWD_READY -> DEPLOYED
  - `GET /api/experiments/{exp_id}/equity` — re-runs OOS backtest, returns cumulative PnL
- `src/webapp/routes/pages.py`: `GET /fwd-ready` page route rendering `fwd_ready.html`.
- `src/webapp/templates/base.html`: Added "FWD Ready" nav link.
- `src/webapp/templates/experiment.html`: Added equity chart `<canvas>` and JS fetch call
  for experiments past IS_OPT gate.
- `tests/unit/test_db.py`: `test_save_and_load_trade_pnl` — round-trip test.
- `tests/integration/test_api.py`: `test_seed_via_form_data`, `test_fwd_ready_page`,
  `test_approve_not_found`, `test_approve_wrong_gate`.
- `docs/DECISIONS.md`: Entry for `trade_pnl TEXT column` decision.

---

## [2026-02-27] — Data Integration + Bug Fixes

### Added
- 9 correct historical CSVs loaded into `data/raw/` (MNQ/MES/MGC, 1m/5m/15m).
  Coverage: MNQ/MES from 2019-05-05, MGC from 2015-01-01, all through 2026-02-27.

### Fixed
- `src/quant/data/loader.py`: CSVs store timestamps in ET already (CME session open =
  18:00 ET). Changed `tz_localize("UTC").tz_convert("ET")` to
  `tz_localize("America/New_York")` — UTC-localize would have shifted every bar 4-5
  hours earlier, misaligning all indicators and IS/OOS boundaries.

- `src/quant/strategies/ema_rsi.py` `_rsi()`: Completely rewritten. Prior
  implementation used `np.empty()` (uninitialized memory) for `avg_gain`/`avg_loss`,
  then wrote to `avg_gain[1] = np.nan` AFTER the loop, meaning index 2 had already
  been computed from garbage. This caused RSI values in the range [-143, +126] instead
  of [0, 100]. Rewrote with correct Wilder's smoothing: simple-average seed for the
  first `period` bars, then Wilder's formula for subsequent bars.

- `pyproject.toml`: Added `plotly>=5.11,<6.0`. vectorbt 0.26.2 uses the `heatmapgl`
  chart type which was removed in plotly 6.x. Without this pin, `import vectorbt`
  raises `ValueError: Bad property path: heatmapgl`.

### Key Finding: V1 Params Not Valid on Correct Data
After fixing RSI, ema_rsi with EMA5/21, RSI9, OS35/OB65 generates only 26 OOS signals
in 50,778 OOS bars (MNQ 15m, 2024-present) and 38 IS trades with PF=0.921 (IS
2020-2023). V1 reported 314 OOS trades and PF=2.405 — those results were artifacts of
the incorrect NinjaTrader data. V2 starts with no proven strategies.
Next step: run Optuna on new data to discover valid parameter sets.

---

## [2026-02-27] — Data Source Cleanup

### Changed
- `README.md`: Removed "Proven Strategies (already deployed)" table. V2 has not run its
  pipeline yet; no strategies are proven in V2.
- `docs/STRATEGIES.md`: Removed "PROVEN (deployed)" section. `ema_rsi` is now listed as
  first candidate, pending a clean pipeline run.
- `tests/regression/test_known_strategies.py`: Split into two tests:
  (1) `test_ema_rsi_engine_sanity` always runs, asserts PF > 1.0 and >= 50 trades.
  (2) `test_ema_rsi_matches_v1_reference` is `@pytest.mark.slow`, checks within 5% of
  V1 OOS PF targets. Only meaningful once V2 data is confirmed correct.
- `scripts/copy_data.sh`: Source path now configurable via `DATA_SRC` env var. Prompts
  interactively if not set. Removed hardcoded path to incorrect NinjaTrader data.

### Root cause
NinjaTrader CSV data in the V1 project was incorrect. User is re-downloading from the
correct source. All references to specific V1 OOS PF values as "already proven in V2"
were premature.

---

## [2026-02-27] — Full Repo Scaffold

### Added
- Complete repo scaffold: pyproject.toml, Makefile, docker-compose.yml, .gitignore,
  .env.example, .pre-commit-config.yaml, docker/app/Dockerfile
- `scripts/`: copy_data.sh, verify_data.py, setup_dev.sh
- `src/config/`: settings.py (pydantic-settings), instruments.py (CONTRACT_MULT, COMMISSION_RT)
- `src/db/`: schema.sql (3-table schema + trigger + CHECK constraints), connection.py
  (thread-local SQLite, PRAGMA foreign_keys + journal_mode=DELETE), queries.py (all SQL),
  migrations.py (integer-versioned ALTER TABLE runner)
- `src/quant/data/`: loader.py, cache.py, splitter.py, validate.py, fetcher.py
- `src/quant/engine/`: metrics.py (pf, sharpe, sortino, calmar, max_drawdown, etc.),
  backtest.py (vectorbt wrapper -> BacktestResult), monte_carlo.py, walk_forward.py,
  sensitivity.py
- `src/quant/strategies/`: ema_rsi.py, rsi_mean_reversion.py, volatility_breakout.py
- `src/quant/optimizer/`: objective.py (IS-val Sharpe), search.py, param_space.py
- `src/quant/pipeline/`: gates.py (all 5 gates), runner.py
- `src/quant/automation/`: loop.py (ThreadPoolExecutor), notifier.py (queue.Queue EventBus),
  seeder.py, pine_generator.py, checklist_generator.py
- `src/webapp/`: main.py (FastAPI + lifespan), deps.py, routes/ (api, pages, sse),
  8 HTML templates, static/ (sse_client.js, charts.js, custom.css)
- `tests/`: conftest.py, 28 unit tests, integration tests, regression tests
- `docs/`: PIPELINE.md, STRATEGIES.md, DEPLOYMENT.md, DECISIONS.md, SIGNALS.md
- `CLAUDE.md` — AI rules for this repo
- Python 3.12 pinned via `.python-version` (numba/llvmlite require <3.13)
- uv 0.10.7 installed on host

### Fixed
- `pyproject.toml` build-backend: `setuptools.backends.legacy:build` -> `setuptools.build_meta`
  (legacy path not valid in all setuptools versions)
- `vectorbt==0.26.2` + `numba>=0.58,<0.60` + `numpy<2.0` pinned to avoid building
  `llvmlite 0.46.0` from source (requires LLVM via Homebrew; no pre-built macOS wheels)
- `tests/unit/test_monte_carlo.py`:
  - `test_all_losing_trades_high_ruin`: added `initial_capital=1_000` so 100x-$100 trades
    actually trigger the 30% ruin threshold (default $100K would not be hit)
  - `test_returns_correct_structure`: changed `<` to `<=` and used 10 varied trades so
    percentile assertions hold even when all shuffles produce the same terminal value
- Makefile `dev` target: `uvicorn src.webapp.main:app` -> `uvicorn webapp.main:app`
  (src/ layout: packages live at `webapp.*` not `src.webapp.*`)

### Result
`uv sync --all-extras`: 113 packages installed. `make test`: 28/28 unit tests pass.
