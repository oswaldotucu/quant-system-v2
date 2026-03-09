"""Strategy registry — maps strategy names to their implementation classes.

To add a new strategy:
1. Create src/quant/strategies/my_strategy.py with a class following the Strategy Protocol
2. Import it here and add to STRATEGY_REGISTRY
3. Add the Optuna param space to src/quant/optimizer/param_space.py
4. Seed experiments via the web UI

RULE: Only add strategies that have OOS evidence. Do NOT add blindly.
"""

from __future__ import annotations

from typing import Any

from quant.strategies.adx_ema import AdxEmaStrategy
from quant.strategies.bollinger_squeeze import BollingerSqueezeStrategy
from quant.strategies.donchian_breakout import DonchianBreakoutStrategy
from quant.strategies.ema_rsi import EmaRsiStrategy
from quant.strategies.keltner_channel import KeltnerChannelStrategy
from quant.strategies.macd_trend import MacdTrendStrategy
from quant.strategies.mtf_ema_alignment import MtfEmaAlignmentStrategy
from quant.strategies.regime_switch import RegimeSwitchStrategy
from quant.strategies.rsi2_reversal import Rsi2ReversalStrategy
from quant.strategies.rsi_bollinger_filtered import RsiBollingerFilteredStrategy
from quant.strategies.session_momentum import SessionMomentumStrategy
from quant.strategies.supertrend import SupertrendStrategy
from quant.strategies.volume_breakout import VolumeBreakoutStrategy

# Map strategy name -> class
STRATEGY_REGISTRY: dict[str, Any] = {
    "ema_rsi": EmaRsiStrategy,
    "adx_ema": AdxEmaStrategy,
    "bollinger_squeeze": BollingerSqueezeStrategy,
    "donchian_breakout": DonchianBreakoutStrategy,
    "supertrend": SupertrendStrategy,
    "macd_trend": MacdTrendStrategy,
    "rsi2_reversal": Rsi2ReversalStrategy,
    "keltner_channel": KeltnerChannelStrategy,
    "volume_breakout": VolumeBreakoutStrategy,
    "mtf_ema_alignment": MtfEmaAlignmentStrategy,
    "regime_switch": RegimeSwitchStrategy,
    "session_momentum": SessionMomentumStrategy,
    "rsi_bollinger_filtered": RsiBollingerFilteredStrategy,
}


def get_strategy(name: str) -> Any:
    """Return strategy class by name. Raises KeyError if unknown."""
    if name not in STRATEGY_REGISTRY:
        raise KeyError(f"Unknown strategy '{name}'. Available: {list(STRATEGY_REGISTRY.keys())}")
    return STRATEGY_REGISTRY[name]


def list_strategies() -> list[str]:
    return sorted(STRATEGY_REGISTRY.keys())
