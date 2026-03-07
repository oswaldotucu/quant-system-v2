# Signal Conventions

How entry/exit signals are represented throughout the codebase.

---

## Strategy Interface

All strategies implement the `Strategy` Protocol defined in `src/quant/strategies/base.py`.
The core method is a static `generate()` that returns three numpy arrays:

```python
@staticmethod
def generate(
    data: pd.DataFrame,
    params: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Returns:
        entries:   bool array — True on bars to enter a trade
        exits:     bool array — True on bars to explicitly exit a trade
        direction: bool array — True = long, False = short (only meaningful where entries=True)

    All arrays are the same length as data.
    """
```

No `pd.Series` — all signals are `np.ndarray` (dtype bool) for vectorbt compatibility.

---

## TP/SL Handling

Take-profit and stop-loss are NOT in the signal arrays. They are applied by the backtest
engine via vectorbt's `sl_stop` and `tp_stop` parameters in `run_backtest()`.

```python
# In backtest.py
pf = vbt.Portfolio.from_signals(
    close=data["close"],
    entries=entries,
    exits=exits,
    sl_stop=params["sl_pct"] / 100,
    tp_stop=params["tp_pct"] / 100,
    ...
)
```

This means:
- `exits` in the signal arrays is for explicit exits (e.g. end-of-day close, regime change)
- TP/SL exits fire automatically from the engine without needing an exit signal
- Most strategies return `exits = np.zeros(n, dtype=bool)` and rely entirely on TP/SL

---

## Bar Timing

- Signals are computed on bar **close**
- Fills execute on the **next bar open** (no look-ahead bias)
- vectorbt is configured with `init_cash` and `freq` matching the timeframe

---

## Long + Short

Strategies can be long-only, short-only, or both. The `direction` array determines
which side each entry is on:

```python
# Long entry when trend up + RSI crosses oversold
long_entries = trend_up & rsi_cross_up

# Short entry when trend down + RSI crosses overbought
short_entries = trend_dn & rsi_cross_dn

entries = long_entries | short_entries
direction = long_entries   # True = long, False = short
exits = np.zeros(n, dtype=bool)
return entries, exits, direction
```

---

## Data Columns Required

```python
data.columns  # must contain:
["open", "high", "low", "close", "volume"]
```

Column names are lowercase. Validated by `src/quant/data/validate.py` before
any strategy sees the data.

---

## Indicator Implementation

All indicator helpers are **pure numpy** — no `ta`, `pandas_ta`, or `talib` dependencies.
This keeps the engine portable and avoids version-pinning issues.

```python
def _ema(close: np.ndarray, period: int) -> np.ndarray:
    alpha = 2.0 / (period + 1)
    result = np.empty_like(close)
    result[0] = close[0]
    for i in range(1, len(close)):
        result[i] = alpha * close[i] + (1 - alpha) * result[i - 1]
    return result
```

If a new strategy needs a complex indicator not worth reimplementing (e.g. ATR bands,
Bollinger Bands), add a `_indicator_name()` numpy helper in the strategy file and
document it in `docs/DECISIONS.md`.
