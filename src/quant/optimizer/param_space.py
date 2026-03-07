"""Optuna search spaces per strategy.

Each strategy has a dict of {param_name: {low, high, step}} defining the grid.
Used by both Optuna (suggest_int/suggest_float) and sensitivity.py (neighbor nudge).

RULE: Only params listed here are optimized. Everything else is fixed.
"""

from __future__ import annotations

from typing import Any

# Type: each param spec is {'low': X, 'high': Y, 'step': Z, 'type': 'int'|'float'}
ParamSpec = dict[str, Any]
ParamSpace = dict[str, ParamSpec]

PARAM_SPACES: dict[str, ParamSpace] = {
    "ema_rsi": {
        "ema_fast": {"low": 3, "high": 10, "step": 1, "type": "int"},
        "ema_slow": {"low": 10, "high": 30, "step": 1, "type": "int"},
        "rsi_period": {"low": 5, "high": 14, "step": 1, "type": "int"},
        "rsi_os": {"low": 25, "high": 50, "step": 5, "type": "int"},
        "rsi_ob": {"low": 50, "high": 75, "step": 5, "type": "int"},
        "tp_pct": {"low": 0.05, "high": 0.5, "step": 0.05, "type": "float"},
        "sl_pct": {"low": 0.1, "high": 0.8, "step": 0.05, "type": "float"},
    },
    "bollinger_squeeze": {
        "bb_period": {"low": 10, "high": 30, "step": 2, "type": "int"},
        "bb_std": {"low": 1.5, "high": 3.0, "step": 0.25, "type": "float"},
        "squeeze_threshold": {"low": 0.005, "high": 0.05, "step": 0.005, "type": "float"},
        "squeeze_lookback": {"low": 3, "high": 15, "step": 1, "type": "int"},
        "tp_pct": {"low": 0.05, "high": 0.5, "step": 0.05, "type": "float"},
        "sl_pct": {"low": 0.1, "high": 0.8, "step": 0.05, "type": "float"},
    },
    "donchian_breakout": {
        "entry_period": {"low": 10, "high": 55, "step": 5, "type": "int"},
        "trend_ema": {"low": 25, "high": 200, "step": 25, "type": "int"},
        "use_trend_filter": {"low": 0, "high": 1, "step": 1, "type": "int"},
        "tp_pct": {"low": 0.05, "high": 0.5, "step": 0.05, "type": "float"},
        "sl_pct": {"low": 0.1, "high": 0.8, "step": 0.05, "type": "float"},
    },
    "adx_ema": {
        "ema_fast": {"low": 5, "high": 15, "step": 1, "type": "int"},
        "ema_slow": {"low": 18, "high": 50, "step": 2, "type": "int"},
        "adx_period": {"low": 10, "high": 20, "step": 2, "type": "int"},
        "adx_threshold": {"low": 15, "high": 35, "step": 5, "type": "int"},
        "tp_pct": {"low": 0.05, "high": 0.5, "step": 0.05, "type": "float"},
        "sl_pct": {"low": 0.1, "high": 0.8, "step": 0.05, "type": "float"},
    },
    "supertrend": {
        "atr_period": {"low": 7, "high": 21, "step": 2, "type": "int"},
        "multiplier": {"low": 1.0, "high": 4.0, "step": 0.25, "type": "float"},
        "tp_pct": {"low": 0.05, "high": 0.5, "step": 0.05, "type": "float"},
        "sl_pct": {"low": 0.1, "high": 0.8, "step": 0.05, "type": "float"},
    },
    "macd_trend": {
        "macd_fast": {"low": 3, "high": 12, "step": 1, "type": "int"},
        "macd_slow": {"low": 10, "high": 30, "step": 2, "type": "int"},
        "macd_signal": {"low": 3, "high": 15, "step": 2, "type": "int"},
        "trend_ema": {"low": 25, "high": 150, "step": 25, "type": "int"},
        "tp_pct": {"low": 0.05, "high": 0.5, "step": 0.05, "type": "float"},
        "sl_pct": {"low": 0.1, "high": 0.8, "step": 0.05, "type": "float"},
    },
    "rsi2_reversal": {
        "rsi_period": {"low": 2, "high": 7, "step": 1, "type": "int"},
        "rsi_os": {"low": 5, "high": 25, "step": 5, "type": "int"},
        "rsi_ob": {"low": 75, "high": 95, "step": 5, "type": "int"},
        "trend_ema": {"low": 50, "high": 200, "step": 25, "type": "int"},
        "tp_pct": {"low": 0.05, "high": 0.5, "step": 0.05, "type": "float"},
        "sl_pct": {"low": 0.1, "high": 0.8, "step": 0.05, "type": "float"},
    },
    "keltner_channel": {
        "kc_period": {"low": 10, "high": 30, "step": 2, "type": "int"},
        "atr_period": {"low": 7, "high": 21, "step": 2, "type": "int"},
        "multiplier": {"low": 1.0, "high": 3.0, "step": 0.25, "type": "float"},
        "tp_pct": {"low": 0.05, "high": 0.5, "step": 0.05, "type": "float"},
        "sl_pct": {"low": 0.1, "high": 0.8, "step": 0.05, "type": "float"},
    },
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
}


def get_param_space(strategy_name: str) -> ParamSpace:
    """Return param space for a strategy. Raises KeyError if unknown."""
    if strategy_name not in PARAM_SPACES:
        raise KeyError(
            f"No param space defined for '{strategy_name}'. Add it to optimizer/param_space.py."
        )
    return PARAM_SPACES[strategy_name]
