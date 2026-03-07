# Strategy Expansion Design — 5 New Strategy Families

**Date:** 2026-03-07
**Goal:** Add 5 strategies covering price action, multi-timeframe, regime-aware, event-driven, and filtered mean-reversion categories. Get 2-3 strategies live-trading within 3 months while building a trustworthy research machine.

---

## Architecture Constraints

- All strategies follow the existing `Strategy Protocol`: `generate(data, params) -> (entries, exits, direction)`
- Pure functions, no I/O
- Warmup guard: `valid = np.zeros(n, dtype=bool); valid[period:] = True`
- TP/SL in 0.05-0.5% range (intraday micro-futures scale)
- Multi-timeframe: resample internally (no protocol change)
- Regime-aware: self-contained sub-logics (no inter-strategy coupling)
- Session-aware: extract RTH boundaries from ET timestamps in DatetimeIndex

---

## Strategy Designs

### A) `volume_breakout` — Price Action / Microstructure

**Signal:** High-volume bar breaks session high/low = momentum continuation.

- Rolling avg volume (20 bars)
- Session high/low (rolling window of RTH bars)
- Long: close > session high AND volume > 2x avg
- Short: close < session low AND volume > 2x avg

**Params:** `vol_period`=20, `vol_multiplier`=2.0, `session_lookback`=16, `tp_pct`=0.15, `sl_pct`=0.3
**Warmup:** `max(vol_period, session_lookback)`

---

### B) `mtf_ema_alignment` — Multi-Timeframe Confluence

**Signal:** 15m EMA crossover confirmed by 1h EMA direction.

- Resample 15m -> 1h internally
- Fast/slow EMA on 15m (8/21), trend EMA on 1h (20) forward-filled to 15m index
- Long: 15m fast > slow cross AND 1h EMA slope > 0
- Short: 15m fast < slow cross AND 1h EMA slope < 0

**Params:** `fast_ema`=8, `slow_ema`=21, `htf_ema`=20, `tp_pct`=0.15, `sl_pct`=0.3
**Warmup:** `slow_ema` bars

---

### C) `regime_switch` — Regime-Aware

**Signal:** ATR percentile classifies regime; trend strategy in high-ATR, mean-reversion in low-ATR.

- ATR(14) percentile over 100 bars
- High-ATR (>60th pctl): EMA crossover (fast 8 / slow 21)
- Low-ATR (<=60th pctl): RSI extreme (<30/>70) + Bollinger Band confirmation

**Params:** `atr_period`=14, `atr_lookback`=100, `regime_threshold`=60, `trend_fast_ema`=8, `trend_slow_ema`=21, `rev_rsi_period`=14, `rev_rsi_os`=30, `rev_rsi_ob`=70, `rev_bb_period`=20, `rev_bb_std`=2.0, `tp_pct`=0.15, `sl_pct`=0.3
**Warmup:** `max(atr_lookback, rev_bb_period)`

---

### D) `session_momentum` — Event-Driven

**Signal:** Opening range breakout with time-bounded trading window.

- Identify RTH open (9:30 ET) from DatetimeIndex
- Track high/low of first N bars after open (opening range)
- After range window: enter in breakout direction
- Only trade for next M bars (avoid overnight chop)
- Filter: minimum range size (% of price)

**Differs from rejected `opening_range_breakout`:** time bounds + range size filter.

**Params:** `range_bars`=4, `trade_window`=16, `min_range_pct`=0.1, `tp_pct`=0.15, `sl_pct`=0.3
**Warmup:** None (session-based)

---

### E) `rsi_bollinger_filtered` — Filtered Mean-Reversion

**Signal:** RSI extreme + Bollinger Band touch, only in low-volatility regime.

- RSI(14), Bollinger Bands(20, 2.0), ATR percentile(14, 100)
- Low-ATR only (<=50th pctl) — skip trending markets
- Long: RSI < oversold AND close < lower BB
- Short: RSI > overbought AND close > upper BB

**Key differentiator from rejected strategies:** ATR regime filter prevents trading into trends.

**Params:** `rsi_period`=14, `rsi_os`=30, `rsi_ob`=70, `bb_period`=20, `bb_std`=2.0, `atr_period`=14, `atr_lookback`=100, `regime_threshold`=50, `tp_pct`=0.15, `sl_pct`=0.3
**Warmup:** `max(bb_period, atr_lookback)`

---

## File Plan

### Create (per strategy):
- `src/quant/strategies/<name>.py` — strategy implementation
- `tests/unit/test_<name>.py` — 5-7 tests per strategy

### Modify:
- `src/quant/strategies/registry.py` — register all 5
- `src/quant/optimizer/param_space.py` — add 5 Optuna param spaces
- `CHANGELOG.md`

### Shared helpers (reuse existing):
- `_ema` from `ema_rsi.py`
- `_rsi` from `ema_rsi.py`
- `atr_wilder` from `indicators.py`
- `_sma`, `_rolling_std` from `bollinger_squeeze.py`

---

## Test Plan

Per strategy:
1. `test_generates_signals` — entries on 78K synthetic bars
2. `test_direction_matches_entries` — direction valid only where entries True
3. `test_empty_data` — empty arrays
4. `test_short_data` — zeros for insufficient bars
5. `test_default_params` — expected keys present
6. Strategy-specific (resampling, regime switching, session detection)
