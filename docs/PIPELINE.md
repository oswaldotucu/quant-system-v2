# Pipeline — 5 Gates

## Overview

```
SCREEN -> IS_OPT -> OOS_VAL -> CONFIRM -> FWD_READY
  <1min   10-45min   <1min     5-15min    ALERT
```

A strategy can never skip gates. Automation advances one gate at a time.
REJECT is final (no re-seeding same strategy/ticker/timeframe after rejection).

---

## Gate 1: SCREEN

**Purpose**: Cheap sanity check. Does the strategy generate any signals recently?

**Data**: Last ~3 months of full dataset (not date-filtered — just last N bars)
- 15m: 780 bars (~3 months at 26 bars/day * 15 days/month)
- 5m: 2,340 bars
- 1m: 5,850 bars

**Pass criteria**:
- PF >= 1.3 on last 3 months
- Trades >= 30

**Why**: If a strategy hasn't had 30 trades in the last 3 months, it's dead.
Kills dead strategies before wasting 45 minutes of Optuna compute.

---

## Gate 2: IS_OPT

**Purpose**: Find best parameters using IS data only. Never touch OOS.

**Data**: IS_TRAIN (2020-2022) + IS_VAL (2023) — no OOS at all.

**Objective**: IS-val Sharpe (2023 data). NOT IS PF.
- IS PF is anti-correlated with OOS PF (proven over 155K backtests in V1)
- IS-val Sharpe penalizes return volatility, not just direction

**Pruning**:
- IS-train: PF < 1.1 OR trades < 15 -> return 0.0 (fast rejection)
- IS-val: PF < 1.2 OR trades < 10 OR win_rate < 30% -> return 0.0

**Pass criteria**:
- best_is_sharpe > 0.5
- best_is_val_pf > 1.2

**Side effect**: Best params are stored in experiments.params (JSON).

---

## Gate 3: OOS_VAL

**Purpose**: First and ONLY cold OOS evaluation.

**Data**: OOS slice (2024-present)
**Params**: From IS_OPT. NEVER re-run with different params.

**Pass criteria**:
- OOS PF >= 1.5
- OOS trades >= 100
- Max DD% < 40%

**Note**: This is the single ground truth. If it fails here, reject immediately.
Do NOT re-run with tweaked params — that is optimization bias.

---

## Gate 4: CONFIRM

**Purpose**: 5-part robustness test. Passes only if edge is real and durable.

### Part 1: Monte Carlo Permutation Test
- Shuffle trade PnL list 10,000 times
- Pass: P(ruin) < 1% AND P(positive) > 95%
- Why: If random shuffles regularly hit ruin, the win/loss sequence matters more than the edge

### Part 2: Walk-Forward (4 windows)
- Same params, cold, on 4 anchored time windows:
  - IS 2020, OOS 2021
  - IS 2020-2021, OOS 2022
  - IS 2020-2022, OOS 2023
  - IS 2020-2023, OOS 2024-2025
- Pass: >= 3 of 4 windows profitable (PF > 1.0, >= 20 trades)
- Why: If it only works in 2022-2023, it's regime-specific

### Part 3: Parameter Sensitivity
- Nudge each param +/-1 step, re-run OOS backtest
- Pass: all neighbor OOS PF >= 1.2
- Why: If nudging ema_fast from 5 to 6 collapses PF from 2.4 to 0.6, it's curve-fit

### Part 4: Cross-Instrument
- Run same params on >= 1 other instrument (MNQ/MES/MGC)
- Pass: at least 1 other instrument passes (PF >= 1.5, >= 50 trades)
- Why: Real edges tend to generalize across correlated markets

### Part 5: Portfolio Correlation
- Compute Pearson correlation of daily PnL vs deployed strategies
- Pass: max correlation < 0.6
- Why: If new strategy is 0.9 correlated with ema_rsi/MNQ, it adds no diversification

---

## Gate 5: FWD_READY

**Purpose**: Human review. Automation stops here.

**Auto-generated**:
- Pine Script v5 (from experiment params)
- Forward test checklist (30-day journal)
- macOS notification

**Human action required**:
- Load Pine Script in TradingView, verify OOS PF within 5%
- Review checklist
- Click Approve (-> DEPLOYED) or Reject

---

## Thresholds Summary

| Threshold | Value | Configurable |
|---|---|---|
| SCREEN min PF | 1.3 | .env |
| SCREEN min trades | 30 | .env |
| OOS min PF | 1.5 | .env |
| OOS min trades | 100 | .env |
| OOS max DD% | 40% | .env |
| MC P(ruin) < | 1% | .env |
| MC P(positive) > | 95% | .env |
| WF profitable windows | 3/4 | hardcoded |
| Sensitivity min PF | 1.2 | hardcoded |
| Corr vs deployed < | 0.6 | hardcoded |
