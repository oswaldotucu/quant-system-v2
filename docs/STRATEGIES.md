# Strategy Catalog

## CANDIDATES (pending first pipeline run)

### ema_rsi

**Family**: trend_following
**Hypothesis**: EMA trend filter + RSI extreme-zone cross = high-probability trend continuation
**Status**: First candidate to run through V2 pipeline once data is loaded.

**Params to test**:
```
ema_fast = 5
ema_slow = 21
rsi_period = 9
rsi_os = 35
rsi_ob = 65
tp_pct = 1.0
sl_pct = 2.8
```

---

### rsi_mean_reversion

**Family**: mean_reversion
**Hypothesis**: RSI extreme zone crosses on raw price = mean-reversion edge
**Status**: V1 Optuna running. DO NOT use until OOS PF >= 1.5.

---

## REJECTED (do not retest)

| Strategy | Reason |
|---|---|
| vwap_reversion | OOS PF < 1.0 across all instruments |
| stoch_rsi MNQ | OOS 2024 = -$143/day |
| gap_fill | IS PF = 0.84 — no IS edge |
| volatility_breakout | OOS PF = 1.22 — consistently weak |
| ema_rsi_confluence MNQ | Optuna overfit, OOS PF = 1.19 |
| opening_range_breakout | PF < 1.0 on all instruments |
| gold_sweep_fade | OOS ceiling PF ~2.7, not scalable |
| vwap_reversion_rth | Only 24 trades in best Optuna result |
