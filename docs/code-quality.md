# Code Quality Rules — Examples

## Type annotations

Every public function must have full type annotations. Pyright enforces this. No exceptions.

```python
# CORRECT
def pf(trades: list[float]) -> float:

# WRONG
def pf(trades):
```

## Error handling

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

## Logging, not print

```python
import logging
log = logging.getLogger(__name__)   # at module top

log.info("Gate OOS_VAL passed: PF=%.3f", result.pf)
log.error("Gate failed: %s", e)
# Never: print(f"Gate passed: {result.pf}")
```

## Constants, not magic numbers

```python
# CORRECT
MIN_OOS_TRADES = 100
OOS_MIN_PF = 1.5

# WRONG
if result.trades >= 100 and result.pf >= 1.5:
```
