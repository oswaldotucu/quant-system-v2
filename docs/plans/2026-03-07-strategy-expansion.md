# Strategy Expansion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement 5 new strategies (volume_breakout, mtf_ema_alignment, regime_switch, session_momentum, rsi_bollinger_filtered), each with unit tests and Optuna param spaces.

**Architecture:** Each strategy follows the Strategy Protocol: `generate(data, params) -> (entries, exits, direction)`. Pure functions, no I/O. Warmup guard pattern: `valid = np.zeros(n, dtype=bool); valid[period:] = True`. TP/SL in 0.05-0.5% range.

**Tech Stack:** numpy, pandas, existing helpers (`_ema`/`_rsi` from `ema_rsi.py`, `atr_wilder` from `indicators.py`, `_sma`/`_rolling_std` from `bollinger_squeeze.py`)

**Parallelism:** Tasks 1-5 are fully independent and MUST be dispatched in parallel. Task 6 (registry + param space) depends on all 5 completing. Task 7 (CHANGELOG) depends on Task 6.

---

## Task 1: `volume_breakout` Strategy

**Files:**
- Create: `src/quant/strategies/volume_breakout.py`
- Create: `tests/unit/test_volume_breakout.py`

**Step 1: Write the strategy implementation**

```python
"""Volume Breakout strategy — high-volume breaks of session highs/lows.

Theory: Volume confirms price conviction. When price breaks a session
high/low on significantly above-average volume, the move is more likely
to continue than to reverse.

Logic:
- Compute rolling average volume over vol_period bars
- Compute rolling session high/low over session_lookback bars
- Long:  close > session high AND volume > vol_multiplier * avg_volume
- Short: close < session low AND volume > vol_multiplier * avg_volume
- Exit:  TP/SL handled by backtest engine
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


class VolumeBreakoutStrategy:
    name = "volume_breakout"
    family = "price_action"

    @staticmethod
    def default_params() -> dict[str, Any]:
        return {
            "vol_period": 20,
            "vol_multiplier": 2.0,
            "session_lookback": 16,
            "tp_pct": 0.15,
            "sl_pct": 0.3,
        }

    @staticmethod
    def generate(
        data: pd.DataFrame,
        params: dict[str, Any],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        close = data["close"].values
        high = data["high"].values
        low = data["low"].values
        volume = data["volume"].values.astype(float)
        n = len(close)

        vol_period: int = params["vol_period"]
        vol_multiplier: float = params["vol_multiplier"]
        session_lookback: int = params["session_lookback"]

        warmup = max(vol_period, session_lookback)
        if n < warmup + 1:
            zeros = np.zeros(n, dtype=bool)
            return zeros.copy(), zeros.copy(), zeros.copy()

        # Rolling average volume
        avg_vol = pd.Series(volume).rolling(vol_period).mean().values

        # Session high/low (rolling window, shifted to exclude current bar)
        session_high = pd.Series(high).rolling(session_lookback).max().shift(1).values
        session_low = pd.Series(low).rolling(session_lookback).min().shift(1).values

        # Volume spike filter
        vol_spike = volume > (vol_multiplier * avg_vol)

        # Warmup guard
        valid = np.zeros(n, dtype=bool)
        valid[warmup:] = True

        # Signals (NaN comparisons return False, safe for warmup)
        long_entries = (close > session_high) & vol_spike & valid
        short_entries = (close < session_low) & vol_spike & valid

        entries = long_entries | short_entries
        direction = long_entries
        exits = np.zeros(n, dtype=bool)

        return entries, exits, direction
```

**Step 2: Write unit tests**

```python
"""Unit tests for quant/strategies/volume_breakout.py."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.volume_breakout import VolumeBreakoutStrategy


class TestGeneratesSignals:
    def test_generates_signals(self, sample_ohlcv: pd.DataFrame) -> None:
        params = VolumeBreakoutStrategy.default_params()
        entries, exits, direction = VolumeBreakoutStrategy.generate(sample_ohlcv, params)

        assert entries.shape == (len(sample_ohlcv),)
        assert exits.shape == (len(sample_ohlcv),)
        assert direction.shape == (len(sample_ohlcv),)
        assert entries.dtype == bool
        assert exits.dtype == bool
        assert direction.dtype == bool
        assert entries.sum() > 0, "Strategy generated zero entry signals"

    def test_exits_all_false(self, sample_ohlcv: pd.DataFrame) -> None:
        params = VolumeBreakoutStrategy.default_params()
        _, exits, _ = VolumeBreakoutStrategy.generate(sample_ohlcv, params)
        assert exits.sum() == 0


class TestDirectionMatchesEntries:
    def test_direction_array_matches_entries(self, sample_ohlcv: pd.DataFrame) -> None:
        params = VolumeBreakoutStrategy.default_params()
        entries, _, direction = VolumeBreakoutStrategy.generate(sample_ohlcv, params)

        entry_indices = np.where(entries)[0]
        assert len(entry_indices) > 0
        total = direction[entries].sum() + (~direction[entries]).sum()
        assert total > 0

    def test_volume_spike_at_entries(self, sample_ohlcv: pd.DataFrame) -> None:
        """All entries must occur on bars with above-average volume."""
        params = VolumeBreakoutStrategy.default_params()
        entries, _, _ = VolumeBreakoutStrategy.generate(sample_ohlcv, params)

        volume = sample_ohlcv["volume"].values.astype(float)
        avg_vol = pd.Series(volume).rolling(params["vol_period"]).mean().values

        entry_mask = entries & ~np.isnan(avg_vol)
        if entry_mask.sum() > 0:
            assert np.all(
                volume[entry_mask] > params["vol_multiplier"] * avg_vol[entry_mask]
            )


class TestEdgeCases:
    def test_empty_data(self) -> None:
        tiny = pd.DataFrame({
            "open": [100.0], "high": [101.0], "low": [99.0],
            "close": [100.5], "volume": [1000],
        }, index=pd.date_range("2023-01-01", periods=1, freq="15min"))
        params = VolumeBreakoutStrategy.default_params()
        entries, exits, direction = VolumeBreakoutStrategy.generate(tiny, params)
        assert entries.shape == (1,)
        assert entries.sum() == 0

    def test_short_data(self) -> None:
        tiny = pd.DataFrame({
            "open": [100.0] * 5, "high": [101.0] * 5, "low": [99.0] * 5,
            "close": [100.5] * 5, "volume": [1000] * 5,
        }, index=pd.date_range("2023-01-01", periods=5, freq="15min"))
        params = VolumeBreakoutStrategy.default_params()
        entries, _, _ = VolumeBreakoutStrategy.generate(tiny, params)
        assert entries.sum() == 0


class TestDefaultParams:
    def test_has_all_required_keys(self) -> None:
        params = VolumeBreakoutStrategy.default_params()
        required = {"vol_period", "vol_multiplier", "session_lookback", "tp_pct", "sl_pct"}
        assert set(params.keys()) == required

    def test_intraday_scale_tp_sl(self) -> None:
        params = VolumeBreakoutStrategy.default_params()
        assert params["tp_pct"] < 1.0
        assert params["sl_pct"] < 1.0


class TestClassAttributes:
    def test_name(self) -> None:
        assert VolumeBreakoutStrategy.name == "volume_breakout"

    def test_family(self) -> None:
        assert VolumeBreakoutStrategy.family == "price_action"
```

**Step 3: Run tests**

Run: `uv run pytest tests/unit/test_volume_breakout.py -v`
Expected: All pass

---

## Task 2: `mtf_ema_alignment` Strategy

**Files:**
- Create: `src/quant/strategies/mtf_ema_alignment.py`
- Create: `tests/unit/test_mtf_ema_alignment.py`

**Step 1: Write the strategy implementation**

```python
"""Multi-Timeframe EMA Alignment — 15m crossover confirmed by 1h trend.

Theory: Short-timeframe signals are more reliable when they agree with
longer-timeframe trend direction. Reduces false crossovers in choppy markets.

Logic:
- Resample 15m data -> 1h internally (no protocol change)
- Fast/slow EMA crossover on 15m as entry trigger
- 1h EMA slope (current > previous) as trend confirmation
- Long:  15m fast EMA crosses above slow EMA AND 1h EMA rising
- Short: 15m fast EMA crosses below slow EMA AND 1h EMA falling
- Exit:  TP/SL handled by backtest engine
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from quant.strategies.ema_rsi import _ema

log = logging.getLogger(__name__)


class MtfEmaAlignmentStrategy:
    name = "mtf_ema_alignment"
    family = "multi_timeframe"

    @staticmethod
    def default_params() -> dict[str, Any]:
        return {
            "fast_ema": 8,
            "slow_ema": 21,
            "htf_ema": 20,
            "tp_pct": 0.15,
            "sl_pct": 0.3,
        }

    @staticmethod
    def generate(
        data: pd.DataFrame,
        params: dict[str, Any],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        close = data["close"].values
        n = len(close)

        fast_period: int = params["fast_ema"]
        slow_period: int = params["slow_ema"]
        htf_period: int = params["htf_ema"]

        warmup = slow_period
        if n < warmup + 1:
            zeros = np.zeros(n, dtype=bool)
            return zeros.copy(), zeros.copy(), zeros.copy()

        # --- 15m EMAs ---
        fast_ema = _ema(close, fast_period)
        slow_ema = _ema(close, slow_period)

        # EMA crossover: fast crosses above/below slow
        # Cross = fast > slow NOW and fast <= slow PREVIOUS bar
        fast_above = fast_ema > slow_ema
        cross_up = np.zeros(n, dtype=bool)
        cross_down = np.zeros(n, dtype=bool)
        cross_up[1:] = fast_above[1:] & ~fast_above[:-1]
        cross_down[1:] = ~fast_above[1:] & fast_above[:-1]

        # --- 1h EMA (resampled from 15m) ---
        # Resample close to 1h, compute EMA, forward-fill back to 15m index
        htf_close = data["close"].resample("1h").last().dropna()
        if len(htf_close) < htf_period + 2:
            zeros = np.zeros(n, dtype=bool)
            return zeros.copy(), zeros.copy(), zeros.copy()

        htf_ema_vals = _ema(htf_close.values, htf_period)
        htf_ema_series = pd.Series(htf_ema_vals, index=htf_close.index)

        # Slope: current 1h EMA > previous 1h EMA
        htf_slope = pd.Series(np.zeros(len(htf_ema_vals)), index=htf_close.index)
        htf_slope.iloc[1:] = np.where(
            htf_ema_vals[1:] > htf_ema_vals[:-1], 1.0, -1.0
        )

        # Forward-fill to 15m index
        htf_ema_15m = htf_ema_series.reindex(data.index, method="ffill")
        htf_slope_15m = htf_slope.reindex(data.index, method="ffill")

        slope_up = htf_slope_15m.values > 0
        slope_down = htf_slope_15m.values < 0

        # Warmup guard
        valid = np.zeros(n, dtype=bool)
        valid[warmup:] = True

        long_entries = cross_up & slope_up & valid
        short_entries = cross_down & slope_down & valid

        entries = long_entries | short_entries
        direction = long_entries
        exits = np.zeros(n, dtype=bool)

        return entries, exits, direction
```

**Step 2: Write unit tests**

```python
"""Unit tests for quant/strategies/mtf_ema_alignment.py."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.mtf_ema_alignment import MtfEmaAlignmentStrategy


class TestGeneratesSignals:
    def test_generates_signals(self, sample_ohlcv: pd.DataFrame) -> None:
        params = MtfEmaAlignmentStrategy.default_params()
        entries, exits, direction = MtfEmaAlignmentStrategy.generate(sample_ohlcv, params)

        assert entries.shape == (len(sample_ohlcv),)
        assert entries.dtype == bool
        assert entries.sum() > 0, "Strategy generated zero entry signals"

    def test_exits_all_false(self, sample_ohlcv: pd.DataFrame) -> None:
        params = MtfEmaAlignmentStrategy.default_params()
        _, exits, _ = MtfEmaAlignmentStrategy.generate(sample_ohlcv, params)
        assert exits.sum() == 0


class TestDirectionMatchesEntries:
    def test_direction_array_matches_entries(self, sample_ohlcv: pd.DataFrame) -> None:
        params = MtfEmaAlignmentStrategy.default_params()
        entries, _, direction = MtfEmaAlignmentStrategy.generate(sample_ohlcv, params)

        entry_indices = np.where(entries)[0]
        assert len(entry_indices) > 0
        total = direction[entries].sum() + (~direction[entries]).sum()
        assert total > 0

    def test_crossover_at_entries(self, sample_ohlcv: pd.DataFrame) -> None:
        """Long entries must have fast EMA > slow EMA."""
        from quant.strategies.ema_rsi import _ema

        params = MtfEmaAlignmentStrategy.default_params()
        entries, _, direction = MtfEmaAlignmentStrategy.generate(sample_ohlcv, params)

        close = sample_ohlcv["close"].values
        fast = _ema(close, params["fast_ema"])
        slow = _ema(close, params["slow_ema"])

        long_mask = entries & direction
        if long_mask.sum() > 0:
            assert np.all(fast[long_mask] > slow[long_mask])


class TestEdgeCases:
    def test_empty_data(self) -> None:
        tiny = pd.DataFrame({
            "open": [100.0], "high": [101.0], "low": [99.0],
            "close": [100.5], "volume": [1000],
        }, index=pd.date_range("2023-01-01", periods=1, freq="15min",
                               tz="America/New_York"))
        params = MtfEmaAlignmentStrategy.default_params()
        entries, exits, direction = MtfEmaAlignmentStrategy.generate(tiny, params)
        assert entries.shape == (1,)
        assert entries.sum() == 0

    def test_short_data(self) -> None:
        tiny = pd.DataFrame({
            "open": [100.0] * 10, "high": [101.0] * 10, "low": [99.0] * 10,
            "close": [100.5] * 10, "volume": [1000] * 10,
        }, index=pd.date_range("2023-01-01", periods=10, freq="15min",
                               tz="America/New_York"))
        params = MtfEmaAlignmentStrategy.default_params()
        entries, _, _ = MtfEmaAlignmentStrategy.generate(tiny, params)
        assert entries.sum() == 0


class TestDefaultParams:
    def test_has_all_required_keys(self) -> None:
        params = MtfEmaAlignmentStrategy.default_params()
        required = {"fast_ema", "slow_ema", "htf_ema", "tp_pct", "sl_pct"}
        assert set(params.keys()) == required

    def test_intraday_scale_tp_sl(self) -> None:
        params = MtfEmaAlignmentStrategy.default_params()
        assert params["tp_pct"] < 1.0
        assert params["sl_pct"] < 1.0


class TestClassAttributes:
    def test_name(self) -> None:
        assert MtfEmaAlignmentStrategy.name == "mtf_ema_alignment"

    def test_family(self) -> None:
        assert MtfEmaAlignmentStrategy.family == "multi_timeframe"
```

**Step 3: Run tests**

Run: `uv run pytest tests/unit/test_mtf_ema_alignment.py -v`
Expected: All pass

---

## Task 3: `regime_switch` Strategy

**Files:**
- Create: `src/quant/strategies/regime_switch.py`
- Create: `tests/unit/test_regime_switch.py`

**Step 1: Write the strategy implementation**

```python
"""Regime Switch strategy — adapts signal logic to volatility regime.

Theory: Markets alternate between trending and ranging regimes. Using a
trend-following strategy in ranging markets (or mean-reversion in trending
markets) causes losses. ATR percentile classifies the regime; each regime
gets its own signal generator.

Logic:
- ATR(14) rolling percentile over 100 bars classifies regime
- High-ATR (trending): EMA crossover (fast/slow)
- Low-ATR (ranging): RSI extreme + Bollinger Band confirmation
- Exit: TP/SL handled by backtest engine
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from quant.strategies.bollinger_squeeze import _sma, _rolling_std
from quant.strategies.ema_rsi import _ema, _rsi
from quant.strategies.indicators import atr_wilder

log = logging.getLogger(__name__)


class RegimeSwitchStrategy:
    name = "regime_switch"
    family = "regime_aware"

    @staticmethod
    def default_params() -> dict[str, Any]:
        return {
            "atr_period": 14,
            "atr_lookback": 100,
            "regime_threshold": 60,
            "trend_fast_ema": 8,
            "trend_slow_ema": 21,
            "rev_rsi_period": 14,
            "rev_rsi_os": 30,
            "rev_rsi_ob": 70,
            "rev_bb_period": 20,
            "rev_bb_std": 2.0,
            "tp_pct": 0.15,
            "sl_pct": 0.3,
        }

    @staticmethod
    def generate(
        data: pd.DataFrame,
        params: dict[str, Any],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        close = data["close"].values
        high = data["high"].values
        low = data["low"].values
        n = len(close)

        atr_period: int = params["atr_period"]
        atr_lookback: int = params["atr_lookback"]
        regime_threshold: float = params["regime_threshold"]
        trend_fast: int = params["trend_fast_ema"]
        trend_slow: int = params["trend_slow_ema"]
        rev_rsi_period: int = params["rev_rsi_period"]
        rev_rsi_os: float = params["rev_rsi_os"]
        rev_rsi_ob: float = params["rev_rsi_ob"]
        rev_bb_period: int = params["rev_bb_period"]
        rev_bb_std: float = params["rev_bb_std"]

        warmup = max(atr_lookback, rev_bb_period, trend_slow)
        if n < warmup + 1:
            zeros = np.zeros(n, dtype=bool)
            return zeros.copy(), zeros.copy(), zeros.copy()

        # --- Regime classification ---
        atr = atr_wilder(high, low, close, atr_period)
        atr_pctl = pd.Series(atr).rolling(atr_lookback).rank(pct=True).values * 100
        high_atr = atr_pctl > regime_threshold
        low_atr = ~high_atr

        # --- Trend signals (EMA crossover) ---
        fast_ema = _ema(close, trend_fast)
        slow_ema = _ema(close, trend_slow)

        trend_long = np.zeros(n, dtype=bool)
        trend_short = np.zeros(n, dtype=bool)
        fast_above = fast_ema > slow_ema
        trend_long[1:] = fast_above[1:] & ~fast_above[:-1]   # cross up
        trend_short[1:] = ~fast_above[1:] & fast_above[:-1]  # cross down

        # --- Reversion signals (RSI + Bollinger Band) ---
        rsi = _rsi(close, rev_rsi_period)
        sma = _sma(close, rev_bb_period)
        std = _rolling_std(close, rev_bb_period)
        bb_lower = sma - rev_bb_std * std
        bb_upper = sma + rev_bb_std * std

        rev_long = (rsi < rev_rsi_os) & (close < bb_lower)
        rev_short = (rsi > rev_rsi_ob) & (close > bb_upper)

        # --- Combine by regime ---
        valid = np.zeros(n, dtype=bool)
        valid[warmup:] = True

        long_entries = ((high_atr & trend_long) | (low_atr & rev_long)) & valid
        short_entries = ((high_atr & trend_short) | (low_atr & rev_short)) & valid

        entries = long_entries | short_entries
        direction = long_entries
        exits = np.zeros(n, dtype=bool)

        return entries, exits, direction
```

**Step 2: Write unit tests**

```python
"""Unit tests for quant/strategies/regime_switch.py."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.regime_switch import RegimeSwitchStrategy


class TestGeneratesSignals:
    def test_generates_signals(self, sample_ohlcv: pd.DataFrame) -> None:
        params = RegimeSwitchStrategy.default_params()
        entries, exits, direction = RegimeSwitchStrategy.generate(sample_ohlcv, params)

        assert entries.shape == (len(sample_ohlcv),)
        assert entries.dtype == bool
        assert entries.sum() > 0, "Strategy generated zero entry signals"

    def test_exits_all_false(self, sample_ohlcv: pd.DataFrame) -> None:
        params = RegimeSwitchStrategy.default_params()
        _, exits, _ = RegimeSwitchStrategy.generate(sample_ohlcv, params)
        assert exits.sum() == 0


class TestDirectionMatchesEntries:
    def test_direction_array_matches_entries(self, sample_ohlcv: pd.DataFrame) -> None:
        params = RegimeSwitchStrategy.default_params()
        entries, _, direction = RegimeSwitchStrategy.generate(sample_ohlcv, params)

        entry_indices = np.where(entries)[0]
        assert len(entry_indices) > 0
        total = direction[entries].sum() + (~direction[entries]).sum()
        assert total > 0


class TestRegimeBehavior:
    def test_both_regimes_produce_signals(self, sample_ohlcv: pd.DataFrame) -> None:
        """With 78K bars, both trending and ranging regimes should fire."""
        from quant.strategies.indicators import atr_wilder

        params = RegimeSwitchStrategy.default_params()
        entries, _, direction = RegimeSwitchStrategy.generate(sample_ohlcv, params)

        close = sample_ohlcv["close"].values
        high = sample_ohlcv["high"].values
        low = sample_ohlcv["low"].values

        atr = atr_wilder(high, low, close, params["atr_period"])
        atr_pctl = pd.Series(atr).rolling(params["atr_lookback"]).rank(pct=True).values * 100
        high_atr = atr_pctl > params["regime_threshold"]

        entries_in_trend = entries & high_atr
        entries_in_range = entries & ~high_atr

        # Both regimes should produce at least some signals
        assert entries_in_trend.sum() > 0 or entries_in_range.sum() > 0


class TestEdgeCases:
    def test_empty_data(self) -> None:
        tiny = pd.DataFrame({
            "open": [100.0], "high": [101.0], "low": [99.0],
            "close": [100.5], "volume": [1000],
        }, index=pd.date_range("2023-01-01", periods=1, freq="15min"))
        params = RegimeSwitchStrategy.default_params()
        entries, exits, direction = RegimeSwitchStrategy.generate(tiny, params)
        assert entries.shape == (1,)
        assert entries.sum() == 0

    def test_short_data(self) -> None:
        tiny = pd.DataFrame({
            "open": [100.0] * 50, "high": [101.0] * 50, "low": [99.0] * 50,
            "close": [100.5] * 50, "volume": [1000] * 50,
        }, index=pd.date_range("2023-01-01", periods=50, freq="15min"))
        params = RegimeSwitchStrategy.default_params()
        entries, _, _ = RegimeSwitchStrategy.generate(tiny, params)
        assert entries.sum() == 0


class TestDefaultParams:
    def test_has_all_required_keys(self) -> None:
        params = RegimeSwitchStrategy.default_params()
        required = {
            "atr_period", "atr_lookback", "regime_threshold",
            "trend_fast_ema", "trend_slow_ema",
            "rev_rsi_period", "rev_rsi_os", "rev_rsi_ob",
            "rev_bb_period", "rev_bb_std",
            "tp_pct", "sl_pct",
        }
        assert set(params.keys()) == required

    def test_intraday_scale_tp_sl(self) -> None:
        params = RegimeSwitchStrategy.default_params()
        assert params["tp_pct"] < 1.0
        assert params["sl_pct"] < 1.0


class TestClassAttributes:
    def test_name(self) -> None:
        assert RegimeSwitchStrategy.name == "regime_switch"

    def test_family(self) -> None:
        assert RegimeSwitchStrategy.family == "regime_aware"
```

**Step 3: Run tests**

Run: `uv run pytest tests/unit/test_regime_switch.py -v`
Expected: All pass

---

## Task 4: `session_momentum` Strategy

**Files:**
- Create: `src/quant/strategies/session_momentum.py`
- Create: `tests/unit/test_session_momentum.py`

**Step 1: Write the strategy implementation**

```python
"""Session Momentum strategy — opening range breakout with time bounds.

Theory: The first 30-60 minutes of RTH (9:30 ET) establish the day's
directional bias. A breakout from this opening range, if the range is
large enough, tends to continue. Restricting trades to a window after
the range avoids overnight chop.

Differs from rejected `opening_range_breakout`: adds time bounds
(trade_window) and minimum range size filter (min_range_pct).

Logic:
- Identify RTH open (9:30 ET) from DatetimeIndex
- Track high/low of first range_bars after open
- Long:  close > opening_high AND range >= min_range_pct
- Short: close < opening_low AND range >= min_range_pct
- Only signal within trade_window bars after the range closes
- Exit: TP/SL handled by backtest engine
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

RTH_OPEN_HOUR = 9
RTH_OPEN_MINUTE = 30


class SessionMomentumStrategy:
    name = "session_momentum"
    family = "event_driven"

    @staticmethod
    def default_params() -> dict[str, Any]:
        return {
            "range_bars": 4,
            "trade_window": 16,
            "min_range_pct": 0.1,
            "tp_pct": 0.15,
            "sl_pct": 0.3,
        }

    @staticmethod
    def generate(
        data: pd.DataFrame,
        params: dict[str, Any],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        close = data["close"].values
        high = data["high"].values
        low = data["low"].values
        n = len(close)

        range_bars: int = params["range_bars"]
        trade_window: int = params["trade_window"]
        min_range_pct: float = params["min_range_pct"]

        if n < range_bars + 1:
            zeros = np.zeros(n, dtype=bool)
            return zeros.copy(), zeros.copy(), zeros.copy()

        long_entries = np.zeros(n, dtype=bool)
        short_entries = np.zeros(n, dtype=bool)

        # Identify session open bars (9:30 ET)
        idx = data.index
        # Handle both tz-aware and tz-naive indexes
        if hasattr(idx, 'tz') and idx.tz is not None:
            times = idx
        else:
            times = idx

        is_session_open = (times.hour == RTH_OPEN_HOUR) & (times.minute == RTH_OPEN_MINUTE)
        session_open_indices = np.where(is_session_open)[0]

        for open_idx in session_open_indices:
            range_end = open_idx + range_bars
            if range_end >= n:
                continue

            # Opening range: high/low of first range_bars
            range_high = high[open_idx:range_end].max()
            range_low = low[open_idx:range_end].min()

            # Range size filter
            mid = (range_high + range_low) / 2
            if mid == 0:
                continue
            range_pct = (range_high - range_low) / mid * 100
            if range_pct < min_range_pct:
                continue

            # Trade window: from range_end to range_end + trade_window
            window_end = min(range_end + trade_window, n)
            for i in range(range_end, window_end):
                if close[i] > range_high:
                    long_entries[i] = True
                elif close[i] < range_low:
                    short_entries[i] = True

        entries = long_entries | short_entries
        direction = long_entries
        exits = np.zeros(n, dtype=bool)

        return entries, exits, direction
```

**Step 2: Write unit tests**

```python
"""Unit tests for quant/strategies/session_momentum.py."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.session_momentum import SessionMomentumStrategy


class TestGeneratesSignals:
    def test_generates_signals(self, sample_ohlcv: pd.DataFrame) -> None:
        params = SessionMomentumStrategy.default_params()
        entries, exits, direction = SessionMomentumStrategy.generate(sample_ohlcv, params)

        assert entries.shape == (len(sample_ohlcv),)
        assert entries.dtype == bool
        # sample_ohlcv has 15min bars from 2020 with ET timezone,
        # so there should be bars at 9:30 ET
        assert entries.sum() > 0, "Strategy generated zero entry signals"

    def test_exits_all_false(self, sample_ohlcv: pd.DataFrame) -> None:
        params = SessionMomentumStrategy.default_params()
        _, exits, _ = SessionMomentumStrategy.generate(sample_ohlcv, params)
        assert exits.sum() == 0


class TestDirectionMatchesEntries:
    def test_direction_array_matches_entries(self, sample_ohlcv: pd.DataFrame) -> None:
        params = SessionMomentumStrategy.default_params()
        entries, _, direction = SessionMomentumStrategy.generate(sample_ohlcv, params)

        entry_indices = np.where(entries)[0]
        assert len(entry_indices) > 0
        total = direction[entries].sum() + (~direction[entries]).sum()
        assert total > 0


class TestSessionLogic:
    def test_no_signals_outside_trade_window(self) -> None:
        """Signals should only appear within trade_window after range_bars."""
        # Create data with a clear 9:30 session open
        idx = pd.date_range(
            "2023-06-01 09:00", periods=40, freq="15min", tz="America/New_York"
        )
        rng = np.random.default_rng(seed=99)
        close = 100 + np.cumsum(rng.normal(0, 0.5, 40))
        high = close + rng.uniform(0, 0.3, 40)
        low = close - rng.uniform(0, 0.3, 40)

        data = pd.DataFrame({
            "open": close + rng.normal(0, 0.1, 40),
            "high": high, "low": low, "close": close,
            "volume": rng.integers(100, 1000, 40),
        }, index=idx)

        params = {
            "range_bars": 2, "trade_window": 4,
            "min_range_pct": 0.0, "tp_pct": 0.15, "sl_pct": 0.3,
        }
        entries, _, _ = SessionMomentumStrategy.generate(data, params)

        # 9:30 is index 2 (09:00, 09:15, 09:30, ...). Range ends at 4.
        # Trade window is bars 4-7. No entries before bar 4.
        assert entries[:4].sum() == 0, "No entries before range closes"


class TestEdgeCases:
    def test_empty_data(self) -> None:
        tiny = pd.DataFrame({
            "open": [100.0], "high": [101.0], "low": [99.0],
            "close": [100.5], "volume": [1000],
        }, index=pd.date_range("2023-01-01", periods=1, freq="15min",
                               tz="America/New_York"))
        params = SessionMomentumStrategy.default_params()
        entries, _, _ = SessionMomentumStrategy.generate(tiny, params)
        assert entries.sum() == 0

    def test_no_rth_sessions(self) -> None:
        """Data that doesn't include 9:30 ET should produce zero signals."""
        idx = pd.date_range(
            "2023-01-01 14:00", periods=20, freq="15min", tz="America/New_York"
        )
        data = pd.DataFrame({
            "open": [100.0] * 20, "high": [101.0] * 20, "low": [99.0] * 20,
            "close": [100.5] * 20, "volume": [1000] * 20,
        }, index=idx)
        params = SessionMomentumStrategy.default_params()
        entries, _, _ = SessionMomentumStrategy.generate(data, params)
        assert entries.sum() == 0


class TestDefaultParams:
    def test_has_all_required_keys(self) -> None:
        params = SessionMomentumStrategy.default_params()
        required = {"range_bars", "trade_window", "min_range_pct", "tp_pct", "sl_pct"}
        assert set(params.keys()) == required

    def test_intraday_scale_tp_sl(self) -> None:
        params = SessionMomentumStrategy.default_params()
        assert params["tp_pct"] < 1.0
        assert params["sl_pct"] < 1.0


class TestClassAttributes:
    def test_name(self) -> None:
        assert SessionMomentumStrategy.name == "session_momentum"

    def test_family(self) -> None:
        assert SessionMomentumStrategy.family == "event_driven"
```

**Step 3: Run tests**

Run: `uv run pytest tests/unit/test_session_momentum.py -v`
Expected: All pass

---

## Task 5: `rsi_bollinger_filtered` Strategy

**Files:**
- Create: `src/quant/strategies/rsi_bollinger_filtered.py`
- Create: `tests/unit/test_rsi_bollinger_filtered.py`

**Step 1: Write the strategy implementation**

```python
"""RSI + Bollinger Band mean-reversion with ATR regime filter.

Theory: Mean-reversion signals (RSI extreme + Bollinger touch) work well
in ranging markets but get destroyed in trending markets. An ATR-based
regime filter restricts entries to low-volatility periods where
mean-reversion has higher probability.

Differs from rejected `rsi_mean_reversion` and `stoch_rsi`:
ATR regime filter prevents trading into trends.

Logic:
- Compute RSI, Bollinger Bands, and ATR percentile
- Low-ATR regime only (percentile <= threshold)
- Long:  RSI < oversold AND close < lower BB
- Short: RSI > overbought AND close > upper BB
- Exit:  TP/SL handled by backtest engine
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from quant.strategies.bollinger_squeeze import _sma, _rolling_std
from quant.strategies.ema_rsi import _rsi
from quant.strategies.indicators import atr_wilder

log = logging.getLogger(__name__)


class RsiBollingerFilteredStrategy:
    name = "rsi_bollinger_filtered"
    family = "mean_reversion"

    @staticmethod
    def default_params() -> dict[str, Any]:
        return {
            "rsi_period": 14,
            "rsi_os": 30,
            "rsi_ob": 70,
            "bb_period": 20,
            "bb_std": 2.0,
            "atr_period": 14,
            "atr_lookback": 100,
            "regime_threshold": 50,
            "tp_pct": 0.15,
            "sl_pct": 0.3,
        }

    @staticmethod
    def generate(
        data: pd.DataFrame,
        params: dict[str, Any],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        close = data["close"].values
        high = data["high"].values
        low = data["low"].values
        n = len(close)

        rsi_period: int = params["rsi_period"]
        rsi_os: float = params["rsi_os"]
        rsi_ob: float = params["rsi_ob"]
        bb_period: int = params["bb_period"]
        bb_std: float = params["bb_std"]
        atr_period: int = params["atr_period"]
        atr_lookback: int = params["atr_lookback"]
        regime_threshold: float = params["regime_threshold"]

        warmup = max(bb_period, atr_lookback)
        if n < warmup + 1:
            zeros = np.zeros(n, dtype=bool)
            return zeros.copy(), zeros.copy(), zeros.copy()

        # --- Indicators ---
        rsi = _rsi(close, rsi_period)
        sma = _sma(close, bb_period)
        std = _rolling_std(close, bb_period)
        bb_upper = sma + bb_std * std
        bb_lower = sma - bb_std * std

        # --- Regime filter (ATR percentile) ---
        atr = atr_wilder(high, low, close, atr_period)
        atr_pctl = pd.Series(atr).rolling(atr_lookback).rank(pct=True).values * 100
        low_atr = atr_pctl <= regime_threshold

        # --- Signals ---
        valid = np.zeros(n, dtype=bool)
        valid[warmup:] = True

        long_entries = (rsi < rsi_os) & (close < bb_lower) & low_atr & valid
        short_entries = (rsi > rsi_ob) & (close > bb_upper) & low_atr & valid

        entries = long_entries | short_entries
        direction = long_entries
        exits = np.zeros(n, dtype=bool)

        return entries, exits, direction
```

**Step 2: Write unit tests**

```python
"""Unit tests for quant/strategies/rsi_bollinger_filtered.py."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.rsi_bollinger_filtered import RsiBollingerFilteredStrategy


class TestGeneratesSignals:
    def test_generates_signals(self, sample_ohlcv: pd.DataFrame) -> None:
        params = RsiBollingerFilteredStrategy.default_params()
        entries, exits, direction = RsiBollingerFilteredStrategy.generate(
            sample_ohlcv, params
        )

        assert entries.shape == (len(sample_ohlcv),)
        assert entries.dtype == bool
        assert entries.sum() > 0, "Strategy generated zero entry signals"

    def test_exits_all_false(self, sample_ohlcv: pd.DataFrame) -> None:
        params = RsiBollingerFilteredStrategy.default_params()
        _, exits, _ = RsiBollingerFilteredStrategy.generate(sample_ohlcv, params)
        assert exits.sum() == 0


class TestDirectionMatchesEntries:
    def test_direction_array_matches_entries(self, sample_ohlcv: pd.DataFrame) -> None:
        params = RsiBollingerFilteredStrategy.default_params()
        entries, _, direction = RsiBollingerFilteredStrategy.generate(
            sample_ohlcv, params
        )

        entry_indices = np.where(entries)[0]
        assert len(entry_indices) > 0
        total = direction[entries].sum() + (~direction[entries]).sum()
        assert total > 0

    def test_regime_filter_active(self, sample_ohlcv: pd.DataFrame) -> None:
        """All entries must be in low-ATR regime."""
        from quant.strategies.indicators import atr_wilder

        params = RsiBollingerFilteredStrategy.default_params()
        entries, _, _ = RsiBollingerFilteredStrategy.generate(sample_ohlcv, params)

        high = sample_ohlcv["high"].values
        low = sample_ohlcv["low"].values
        close = sample_ohlcv["close"].values

        atr = atr_wilder(high, low, close, params["atr_period"])
        atr_pctl = pd.Series(atr).rolling(params["atr_lookback"]).rank(pct=True).values * 100

        entry_mask = entries & ~np.isnan(atr_pctl)
        if entry_mask.sum() > 0:
            assert np.all(atr_pctl[entry_mask] <= params["regime_threshold"])


class TestEdgeCases:
    def test_empty_data(self) -> None:
        tiny = pd.DataFrame({
            "open": [100.0], "high": [101.0], "low": [99.0],
            "close": [100.5], "volume": [1000],
        }, index=pd.date_range("2023-01-01", periods=1, freq="15min"))
        params = RsiBollingerFilteredStrategy.default_params()
        entries, _, _ = RsiBollingerFilteredStrategy.generate(tiny, params)
        assert entries.shape == (1,)
        assert entries.sum() == 0

    def test_short_data(self) -> None:
        tiny = pd.DataFrame({
            "open": [100.0] * 50, "high": [101.0] * 50, "low": [99.0] * 50,
            "close": [100.5] * 50, "volume": [1000] * 50,
        }, index=pd.date_range("2023-01-01", periods=50, freq="15min"))
        params = RsiBollingerFilteredStrategy.default_params()
        entries, _, _ = RsiBollingerFilteredStrategy.generate(tiny, params)
        assert entries.sum() == 0


class TestDefaultParams:
    def test_has_all_required_keys(self) -> None:
        params = RsiBollingerFilteredStrategy.default_params()
        required = {
            "rsi_period", "rsi_os", "rsi_ob",
            "bb_period", "bb_std",
            "atr_period", "atr_lookback", "regime_threshold",
            "tp_pct", "sl_pct",
        }
        assert set(params.keys()) == required

    def test_intraday_scale_tp_sl(self) -> None:
        params = RsiBollingerFilteredStrategy.default_params()
        assert params["tp_pct"] < 1.0
        assert params["sl_pct"] < 1.0


class TestClassAttributes:
    def test_name(self) -> None:
        assert RsiBollingerFilteredStrategy.name == "rsi_bollinger_filtered"

    def test_family(self) -> None:
        assert RsiBollingerFilteredStrategy.family == "mean_reversion"
```

**Step 3: Run tests**

Run: `uv run pytest tests/unit/test_rsi_bollinger_filtered.py -v`
Expected: All pass

---

## Task 6: Register All Strategies + Param Spaces

**Depends on:** Tasks 1-5 all complete

**Files:**
- Modify: `src/quant/strategies/registry.py`
- Modify: `src/quant/optimizer/param_space.py`

**Step 1: Update registry.py**

Add these imports after existing imports (after line 23):

```python
from quant.strategies.mtf_ema_alignment import MtfEmaAlignmentStrategy
from quant.strategies.regime_switch import RegimeSwitchStrategy
from quant.strategies.rsi_bollinger_filtered import RsiBollingerFilteredStrategy
from quant.strategies.session_momentum import SessionMomentumStrategy
from quant.strategies.volume_breakout import VolumeBreakoutStrategy
```

Add these entries to `STRATEGY_REGISTRY` dict (after line 34):

```python
    "volume_breakout": VolumeBreakoutStrategy,
    "mtf_ema_alignment": MtfEmaAlignmentStrategy,
    "regime_switch": RegimeSwitchStrategy,
    "session_momentum": SessionMomentumStrategy,
    "rsi_bollinger_filtered": RsiBollingerFilteredStrategy,
```

**Step 2: Update param_space.py**

Add these entries to `PARAM_SPACES` dict (after line 78, before the closing `}`):

```python
    "volume_breakout": {
        "vol_period": {"low": 10, "high": 40, "step": 5, "type": "int"},
        "vol_multiplier": {"low": 1.5, "high": 4.0, "step": 0.25, "type": "float"},
        "session_lookback": {"low": 8, "high": 32, "step": 4, "type": "int"},
        "tp_pct": {"low": 0.05, "high": 0.5, "step": 0.05, "type": "float"},
        "sl_pct": {"low": 0.1, "high": 0.8, "step": 0.05, "type": "float"},
    },
    "mtf_ema_alignment": {
        "fast_ema": {"low": 3, "high": 13, "step": 1, "type": "int"},
        "slow_ema": {"low": 15, "high": 30, "step": 1, "type": "int"},
        "htf_ema": {"low": 10, "high": 50, "step": 5, "type": "int"},
        "tp_pct": {"low": 0.05, "high": 0.5, "step": 0.05, "type": "float"},
        "sl_pct": {"low": 0.1, "high": 0.8, "step": 0.05, "type": "float"},
    },
    "regime_switch": {
        "atr_period": {"low": 7, "high": 21, "step": 2, "type": "int"},
        "atr_lookback": {"low": 50, "high": 200, "step": 25, "type": "int"},
        "regime_threshold": {"low": 40, "high": 80, "step": 5, "type": "int"},
        "trend_fast_ema": {"low": 3, "high": 13, "step": 1, "type": "int"},
        "trend_slow_ema": {"low": 15, "high": 30, "step": 1, "type": "int"},
        "rev_rsi_period": {"low": 7, "high": 21, "step": 2, "type": "int"},
        "rev_rsi_os": {"low": 20, "high": 40, "step": 5, "type": "int"},
        "rev_rsi_ob": {"low": 60, "high": 80, "step": 5, "type": "int"},
        "rev_bb_period": {"low": 10, "high": 30, "step": 5, "type": "int"},
        "rev_bb_std": {"low": 1.5, "high": 3.0, "step": 0.25, "type": "float"},
        "tp_pct": {"low": 0.05, "high": 0.5, "step": 0.05, "type": "float"},
        "sl_pct": {"low": 0.1, "high": 0.8, "step": 0.05, "type": "float"},
    },
    "session_momentum": {
        "range_bars": {"low": 2, "high": 8, "step": 1, "type": "int"},
        "trade_window": {"low": 8, "high": 32, "step": 4, "type": "int"},
        "min_range_pct": {"low": 0.0, "high": 0.5, "step": 0.05, "type": "float"},
        "tp_pct": {"low": 0.05, "high": 0.5, "step": 0.05, "type": "float"},
        "sl_pct": {"low": 0.1, "high": 0.8, "step": 0.05, "type": "float"},
    },
    "rsi_bollinger_filtered": {
        "rsi_period": {"low": 7, "high": 21, "step": 2, "type": "int"},
        "rsi_os": {"low": 20, "high": 40, "step": 5, "type": "int"},
        "rsi_ob": {"low": 60, "high": 80, "step": 5, "type": "int"},
        "bb_period": {"low": 10, "high": 30, "step": 5, "type": "int"},
        "bb_std": {"low": 1.5, "high": 3.0, "step": 0.25, "type": "float"},
        "atr_period": {"low": 7, "high": 21, "step": 2, "type": "int"},
        "atr_lookback": {"low": 50, "high": 200, "step": 25, "type": "int"},
        "regime_threshold": {"low": 30, "high": 70, "step": 5, "type": "int"},
        "tp_pct": {"low": 0.05, "high": 0.5, "step": 0.05, "type": "float"},
        "sl_pct": {"low": 0.1, "high": 0.8, "step": 0.05, "type": "float"},
    },
```

**Step 3: Run all tests**

Run: `uv run pytest tests/unit/ tests/integration/ --no-cov -q`
Expected: All pass (67 existing + ~45 new = ~112 tests)

---

## Task 7: Update CHANGELOG.md

**Depends on:** Task 6

**Step 1: Add entry at top of CHANGELOG.md (after the header)**

```markdown
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
- `tests/unit/test_volume_breakout.py`: 9 tests
- `tests/unit/test_mtf_ema_alignment.py`: 9 tests
- `tests/unit/test_regime_switch.py`: 9 tests
- `tests/unit/test_session_momentum.py`: 9 tests
- `tests/unit/test_rsi_bollinger_filtered.py`: 9 tests
```

**Step 2: Run final verification**

Run: `uv run pytest tests/unit/ tests/integration/ --no-cov -q`
Expected: All pass
