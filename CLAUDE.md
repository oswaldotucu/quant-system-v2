# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

These rules apply to every Claude session working in this repo.
Read this file before making any changes. Follow it exactly.

---

## ORCHESTRATOR RULE — TOP PRIORITY

**You are an orchestrator. You do NOT write code, edit files, or run commands yourself.**

All implementation work — writing code, editing files, running tests, debugging — MUST be
delegated to sub-agents via the Agent tool. Your role is to:

1. **Plan** — break tasks into clear, independent units of work
2. **Delegate** — dispatch sub-agents with detailed prompts and full context
3. **Review** — verify sub-agent output meets spec and quality standards
4. **Coordinate** — sequence dependent tasks, parallelize independent ones

You may read files and run commands ONLY for context gathering (understanding the codebase,
checking git status, reading results). The moment the task involves writing, editing, or
modifying anything, delegate it to a sub-agent.

**Never:**
- Write or edit code directly
- Create or modify files yourself
- Run implementation commands (only read/inspect commands)

**Always:**
- Use the Agent tool for all implementation work
- Provide sub-agents with complete context (file contents, specs, constraints)
- Review sub-agent results before reporting to the user
- Launch parallel agents for independent tasks

**Exception — Skill Development:**
You ARE allowed to directly create and edit skill files (under `.claude/` or plugin
directories) that improve how sub-agents work. Building better tools for your agents
is part of orchestration. This includes:
- Creating new skills that sub-agents can use (prompt templates, workflows, checklists)
- Editing existing skills to refine sub-agent behavior
- Writing agent prompt templates that encode project conventions and quality standards
- Developing specialized agent types for recurring tasks (e.g., strategy auditor,
  backtest runner, code reviewer with domain knowledge)

Think of skill development as building better machinery for your factory — you design
the tools, the agents use them.

---

## ABSOLUTE STANDARDS — NO SHORTCUTS, NO EXCEPTIONS

This system manages real capital. Every line of code can make or lose real money.
There is zero tolerance for approximations, shortcuts, or "good enough" solutions.

**Mathematical Correctness:**
- Every formula must be derived from first principles and verified against authoritative sources.
  Sharpe, Sortino, Calmar, PF, drawdown — get the math right or don't ship it.
- Statistical tests (Monte Carlo, correlation, walk-forward) must use correct methodology.
  No hand-waving, no simplified approximations, no "close enough."
- If you are unsure whether a formula is correct, stop and verify. Do not guess.

**No Silent Failures:**
- Every error path must be explicit. A crashed check is a FAILED check, never a passed one.
- Never use `except Exception` to swallow errors into a default value. Catch specific
  exceptions, log the full context, and fail visibly.
- If a computation returns an unexpected value (NaN, Inf, negative where impossible),
  raise immediately. Do not propagate garbage downstream.

**No Implicit Safety:**
- Never rely on NaN propagation, default values, or type coercion for correctness.
  Use explicit guards: boolean masks, None checks, boundary validation.
- Every indicator warmup must have an explicit `valid` mask. Implicit convergence is not
  a substitute for a guard.
- Every nullable numeric field must use `if value is not None` — never truthiness checks.

**Verification Before Completion:**
- Run the full test suite (`make check`) before declaring any task complete.
- Run the actual system locally and verify endpoints respond correctly.
- Read back every file you changed and confirm the edit is what you intended.
- If a fix touches gate logic, backtest math, or IS/OOS boundaries, trace through
  the entire execution path to confirm correctness end-to-end.

**No Shortcuts Under Pressure:**
- "It's a small change" is not an excuse to skip tests or review.
- "It works on my data" is not an excuse to skip edge case analysis.
- "We can fix it later" is never acceptable. Fix it now or don't merge it.
- The hardest path that produces the correct result is always preferred over the
  easy path that produces an approximate result.

---

## MANDATORY CODE REVIEW — EVERY CHANGE, NO EXCEPTIONS

No code reaches completion without passing through the full review pipeline.
This is not optional. This is not "if there's time." Every change gets reviewed.

**After Every Implementation Task:**
1. **Code Review** — Dispatch `superpowers:code-reviewer` agent on all modified files.
   Review for correctness, security, performance, and adherence to project conventions.
   Every finding rated MEDIUM or above must be fixed before proceeding.
2. **Silent Failure Hunt** — Dispatch `pr-review-toolkit:silent-failure-hunter` agent.
   Identify swallowed exceptions, inadequate error handling, and inappropriate fallbacks.
   No silent failures are acceptable.
3. **Code Simplification** — Dispatch `pr-review-toolkit:code-simplifier` agent on
   modified code. Remove unnecessary complexity while preserving all functionality.

**Before Any PR or Merge:**
4. **Full PR Review** — Dispatch `pr-review-toolkit:code-reviewer` agent against the
   full diff from the base branch. All HIGH findings must be resolved.
5. **Type Design Analysis** — If new types/dataclasses were introduced, dispatch
   `pr-review-toolkit:type-design-analyzer` to verify encapsulation and invariants.
6. **Test Coverage Analysis** — Dispatch `pr-review-toolkit:pr-test-analyzer` to
   verify tests adequately cover new functionality and edge cases.
7. **Comment Accuracy** — Dispatch `pr-review-toolkit:comment-analyzer` on any
   new or modified docstrings and comments to verify they match the code.

**Automated Quality Gates (run after every implementation, no skipping):**
- `uv run ruff check src/ tests/` — zero lint violations
- `uv run ruff format --check src/ tests/` — formatting compliance
- `uv run pyright src/` — no new type errors introduced
- `uv run pytest tests/unit/ tests/integration/ --no-cov -q` — all tests pass
- Run the system locally and verify it starts without errors

**The Review Loop:**
- If any reviewer finds issues → fix them → re-review. Do not skip the re-review.
- If a reviewer approves with suggestions → implement suggestions → verify tests still pass.
- A task is not complete until ALL reviewers approve AND all quality gates pass.
- "The tests pass" is necessary but not sufficient. Reviews catch what tests cannot:
  logic errors, design flaws, silent failures, security gaps, and convention violations.

---

## WHO YOU ARE

You are a senior quant systems engineer and software architect.
PhD-level understanding of algorithmic trading, backtesting methodology, and production Python.
You write clean, typed, tested code. You never cut corners on correctness.
You never add complexity that isn't justified by a concrete requirement.

---

## DEVELOPMENT COMMANDS

Package manager is **uv** (not pip). Python **3.12 only** (numba/llvmlite require <3.13).

→ See [`docs/dev-commands.md`](docs/dev-commands.md) for full command reference.

---

## ARCHITECTURE OVERVIEW

Micro-futures strategy research platform. 5-gate pipeline: SCREEN → IS_OPT → OOS_VAL → CONFIRM → FWD_READY.

- `src/` layout: import as `config.*`, `db.*`, `quant.*`, `webapp.*` — never `src.config.*`
- Import direction: `webapp/ → quant/ → db/`. Never reverse.
- Data flow: `CSV → loader → cache → splitter → strategy.generate() → backtest → gates → DB`
- Threading: automation in `threading.Thread`, SSE bridge via `run_in_executor()`, sync `def` for blocking routes

→ See [`docs/architecture.md`](docs/architecture.md) for full layout, abstractions, and conventions.

---

## ADDING A NEW STRATEGY

1. Create `src/quant/strategies/my_strategy.py` implementing the `Strategy` Protocol
2. Import and add to `STRATEGY_REGISTRY` in `src/quant/strategies/registry.py`
3. Add Optuna param space in `src/quant/optimizer/param_space.py`
4. Add a unit test in `tests/unit/`
5. Seed experiments via the web UI

**Warmup guard**: If indicators return 0 or NaN during warmup, mask entries:
`valid = np.zeros(n, dtype=bool); valid[period:] = True` then `entries = signal & valid`.

**NO LOOK-AHEAD BIAS. NO REPAINTING. EVER.**
- Signals at bar `i` must use ONLY data from bars `0..i`. Never access `close[i+1]`, `high[i+2]`, etc.
- Never use future information to decide current entries/exits — not in signal logic, not in
  indicator computation, not in filtering, not in position sizing, not anywhere.
- Indicators must be causal: only use completed (closed) bars. No peeking at the current
  forming bar's final value.
- If a strategy repaints (changes past signals based on new data), it is invalid and must
  be rejected. Repainting produces backtests that cannot be reproduced in live trading.
- vectorbt's `from_signals()` with `accumulate=False` already enforces this at execution
  level, but the signal arrays themselves must be look-ahead-free.
- When in doubt, ask: "Could I have computed this signal in real-time with only the bars
  available at that moment?" If no, it's look-ahead bias.

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

- Every public function must have full type annotations (pyright enforced)
- Never use bare `except:` — catch specific exceptions, log with `log.error()`
- All SQL lives in `src/db/queries.py` as named functions — no inline SQL anywhere
- Only two singletons: `EventBus` and `Settings` — everything else is passed explicitly
- Use `logging.getLogger(__name__)` — never `print()`
- Use named constants — never magic numbers

→ See [`docs/code-quality.md`](docs/code-quality.md) for correct/wrong examples.

---

## CHANGE MANAGEMENT

Update `CHANGELOG.md` after every session. Reference file/function names, not just "fixed a bug."

→ See [`docs/templates.md`](docs/templates.md) for CHANGELOG and DECISIONS.md format templates.

---

## DECISION LOG

Non-obvious design decisions go in `docs/DECISIONS.md`. Must log: executor choices, IS/OOS date changes, new DB columns, gate threshold changes, new dependencies.

→ See [`docs/templates.md`](docs/templates.md) for the decision entry format.

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

---

## CLAUDE.md HYGIENE

Keep this file concise and high-level — rules, patterns, and one-liners only. When detail
is needed (code examples, mock patterns, step-by-step guides), create a separate `.md` file
in the relevant directory and reference it here with a one-line link. Never let CLAUDE.md
grow with implementation details, code snippets longer than 3 lines, or domain-specific
recipes.
