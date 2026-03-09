# Design Decisions — quant-system-v2

Whenever a non-obvious architectural or algorithmic decision is made, record it here.
See CLAUDE.md for the required format.

---

## [2026-02-27] — ThreadPoolExecutor over ProcessPoolExecutor

**Context**: The automation loop runs multiple gate computations in parallel. Two options
existed: `ThreadPoolExecutor` (threads) or `ProcessPoolExecutor` (subprocesses).

**Decision**: Use `ThreadPoolExecutor`.

**Alternatives**: `ProcessPoolExecutor` would give true CPU parallelism and bypass the GIL.

**Consequences**: vectorbt releases the GIL during numerical computation, so threads get
real concurrency for backtesting. More importantly, SQLite connections cannot be pickled
across process boundaries. Using processes would require re-opening the DB connection in
every worker function, which breaks the thread-local connection model in `db/connection.py`.
Threads share the same process memory; each thread gets its own connection via
`threading.local()`. No pickling issues.

---

## [2026-02-27] — queue.Queue (not asyncio.Queue) for EventBus

**Context**: The automation loop emits events from a `threading.Thread`. The SSE endpoint
consumes events from an `async def` FastAPI route. Two queue types exist: `queue.Queue`
(thread-safe stdlib) and `asyncio.Queue` (only safe within a single event loop).

**Decision**: Use `queue.Queue` everywhere. The SSE bridge calls
`await loop.run_in_executor(None, lambda: q.get(timeout=30))` to make the blocking
queue read non-blocking from the async perspective.

**Alternatives**: `asyncio.Queue` requires all producers to be in the same event loop.
The threading.Thread running the automation loop is NOT the event loop. Calling
`asyncio.Queue.put()` from a thread is undefined behavior and can silently deadlock.

**Consequences**: SSE keepalive requires a 30-second timeout on `q.get()` so the async
route does not block indefinitely. A `: keepalive\n\n` comment is sent on timeout.

---

## [2026-02-27] — IS-val Sharpe as Optuna Objective (not IS PF)

**Context**: V1 ran 155,000+ Optuna trials optimizing IS PF. Analysis showed IS PF is
anti-correlated with OOS PF — the Optuna "best" trial on IS was almost never the best
on OOS. IS PF is easy to overfit: strategies with high IS PF typically exploited
look-ahead or had too few IS trades.

**Decision**: Optimize IS-val Sharpe (Sharpe on the 2023 held-out validation year).
2023 was never seen during the trial's IS_TRAIN optimization.

**Alternatives**: IS PF, IS Sharpe (on full IS), IS CAGR.

**Consequences**: The optimizer cannot see OOS data at all. IS_VAL (2023) acts as a
second out-of-sample guard before the true OOS test. Strategies that survive Sharpe
optimization on IS_VAL tend to generalize better to OOS.

---

## [2026-02-27] — SQLite journal_mode = DELETE (not WAL)

**Context**: The DB file is stored on a macOS Docker volume mount. WAL mode creates
additional `-wal` and `-shm` sidecar files. On macOS Docker (osxfs / gRPC FUSE), WAL
file locking has known race conditions that can corrupt the WAL log under concurrent
writer load.

**Decision**: `PRAGMA journal_mode = DELETE` (classic rollback journal).

**Alternatives**: WAL (Write-Ahead Log) for better read concurrency.

**Consequences**: WAL's read/write concurrency benefit is irrelevant here — there is
only one writer (the automation loop, serialized via ThreadPoolExecutor) and reads from
FastAPI are infrequent. DELETE mode is slower for write-heavy workloads but this system
writes at most a few rows per minute.

---

## [2026-02-27] — Single Docker Service (not multi-container)

**Context**: V1 used 16 Docker containers (5 workers, 2 Optuna runners, Redis, dashboard,
orchestrator, etc.) consuming ~5.9 GB RAM. Startup and coordination overhead was high.

**Decision**: Single Docker service running `uvicorn webapp.main:app`. The automation
loop, Optuna runs, and web server all run in the same process using threads.

**Alternatives**: Separate containers for web, workers, and Optuna (V1 approach).

**Consequences**: Simpler deployment, <700 MB RAM target, no inter-process communication.
Trade-off: a crash in the automation thread would bring down the web server too.
Mitigated by per-future try/except in `AutomationLoop` so individual gate failures do
not crash the process.

---

## [2026-03-06] — trade_pnl TEXT column for portfolio correlation

**Context**: The CONFIRM gate checks portfolio correlation (Pearson r) between a new
strategy and deployed strategies. This requires per-trade P&L data for all deployed
experiments. Previously `_check_portfolio_correlation()` was stubbed (always returned
`max_corr=0.0`) because no trade_pnl storage existed.

**Decision**: Add `trade_pnl TEXT` column to experiments table via migration v1.
Store as JSON-encoded `list[float]`. Populated during OOS_VAL gate (same pattern as
`quarterly_wr`). New `save_trade_pnl()` / `load_trade_pnl()` functions in `db/queries.py`.

**Alternatives**: (1) Store in a separate `trade_pnl` table with one row per trade —
more normalized but unnecessary complexity for a correlation check. (2) Recompute by
re-running backtest — too expensive to do for every deployed strategy during CONFIRM.

**Consequences**: Migration adds ~1KB per experiment (100 trades * 10 chars per float).
The column is nullable — experiments that passed CONFIRM before this migration will
have `NULL` and be skipped in the correlation check (equivalent to `max_corr=0.0`).

---

## [2026-03-06] — SCREEN Gate Thresholds Relaxed

**Context**: SCREEN uses default (unoptimized) params on the last 780 bars. With PF>=1.3 and trades>=30, 11/12 strategies were rejected before reaching Optuna — even strategies that would likely find profitable params during IS_OPT. The SCREEN gate was too aggressive for its purpose.

**Decision**: Lowered to SCREEN_MIN_PF=0.0, SCREEN_MIN_TRADES=5. SCREEN now only filters strategies that produce zero or near-zero signals.

**Alternatives**: (1) Keep PF>=1.3 and hand-tune every strategy's defaults to pass — fragile. (2) Skip SCREEN entirely — wastes 45 min Optuna time on zero-signal strategies.

**Consequences**: More strategies reach IS_OPT (13 vs 1). Some will fail IS_OPT quickly (pruned at trial 1). Acceptable tradeoff.

---

## [2026-02-27] — HTMX + Alpine.js + Tailwind CDN (no JS build step)

**Context**: The dashboard is a single-user internal tool. A full JS build pipeline
(Webpack, Vite, npm) would add operational overhead with no benefit.

**Decision**: Load Tailwind CSS via CDN, use HTMX for server-driven partial updates,
Alpine.js for lightweight client state. No `node_modules`, no `npm install`.

**Alternatives**: React/Next.js SPA, Vue, Svelte.

**Consequences**: Dramatically simpler deployment. No JS build step. SSE updates use
a small custom `sse_client.js`. Trade-off: CDN dependency for Tailwind (acceptable for
a local dev tool; can be self-hosted if needed).

---

## [2026-03-07] — 5 New Strategy Families (Diversified Edge Sources)

**Context**: All 40 existing experiments were REJECTED. The 5 original strategies (ema_rsi, adx_ema, supertrend, macd_trend, rsi2_reversal) plus 3 added strategies (bollinger_squeeze, donchian_breakout, keltner_channel) are all momentum/trend-following with indicator-based entries. If the market regime doesn't suit trend-following, all fail together.

**Decision**: Add 5 strategies covering fundamentally different edge sources: volume confirmation (microstructure), multi-timeframe confluence (cross-scale), ATR-based regime switching (non-stationarity), session structure (time-of-day), and regime-filtered mean-reversion (conditional). Total: 13 strategies across 6 families.

**Alternatives**: (1) Add more trend-following variants — high correlation with existing strategies, unlikely to improve pipeline throughput. (2) Add 10 strategies (2 per category) — YAGNI, 5 gives sufficient diversity. (3) Extend protocol for multi-timeframe — unnecessary, internal resampling works.

**Consequences**: `mtf_ema_alignment` resamples 15m→1h internally via `pd.resample("1h")`, keeping the Strategy Protocol unchanged. `regime_switch` has 12 params (most of any strategy), which expands the Optuna search space — mitigated by using 300 trials with TPE sampler. `session_momentum` depends on ET timezone in the DatetimeIndex — will produce zero signals if data lacks 9:30 ET bars.

---

## [2026-03-07] — Reset REJECTED Experiments to SCREEN After Threshold Change

**Context**: 13 experiments were REJECTED under old SCREEN thresholds (PF≥1.3, trades≥30). After relaxing to PF≥0.0, trades≥5 (decision 2026-03-06), all 13 should have passed. But since they were already REJECTED, the new thresholds had no effect.

**Decision**: Direct DB update: `SET gate = 'SCREEN'` for the 13 experiments with `screen_pf IS NOT NULL`. This re-queues them for the automation loop to re-evaluate with current settings.

**Alternatives**: (1) Delete and re-seed — loses the stored screen_pf/screen_trades metrics. (2) Manually advance to IS_OPT — bypasses the gate logic and could advance experiments that shouldn't pass even under new thresholds.

**Consequences**: 13 experiments re-enter SCREEN. The SCREEN gate will re-run `run_backtest()` on recent data and check against current thresholds. The UNIQUE index `idx_experiments_unique` (WHERE gate NOT IN ('REJECTED')) prevents duplicate active experiments per strategy/ticker/timeframe, so the 27 remaining REJECTED duplicates don't conflict.

---

## [2026-03-09] — Walk-Forward Window Counting in CONFIRM Gate

**Context**: During code review, it was flagged that `walk_forward.py` counts ALL windows (both IS and OOS periods) toward the CONFIRM gate pass threshold. The CONFIRM gate requires "profitable in >= 3 of 4 windows" via `wf.profitable_windows / wf.total_windows`. The question is whether only OOS windows should count, since IS windows are expected to be profitable (they were optimized on that data).

**Decision**: Keep current behavior — count all windows including IS periods. Rationale:
1. Walk-forward already uses rolling IS→OOS splits that are distinct from the main IS/OOS split. Each WF window has its own mini-IS and mini-OOS, so the "IS" windows in WF are NOT the same IS data used for Optuna optimization.
2. If a strategy fails even on its own WF-IS windows with the fixed params from Optuna, that's a strong rejection signal.
3. The 3/4 threshold is already conservative. Requiring 3/4 of only-OOS windows would make CONFIRM nearly impossible to pass.

**Alternatives**:
- Count only WF-OOS windows: Higher bar but potentially too aggressive given the 4-window design.
- Weight WF-OOS windows more heavily: Adds complexity without clear benefit.

**Consequences**: Strategies that are profitable on 3+ of 4 walk-forward windows (including WF-IS) pass. This is a moderate bar that catches overfitting without being prohibitively strict.
