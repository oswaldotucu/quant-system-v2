"""Auto-generate Pine Script v5 from experiment params.

Generates a TradingView Pine Script that matches the Python backtest logic exactly.
The script is saved to data/pine_scripts/ and the path stored in experiments.pine_path.

RULE: Only ASCII characters in Pine Script output. No em-dashes, arrows, or Unicode.
"""

from __future__ import annotations

import logging
from pathlib import Path

from config.settings import get_settings
from db.queries import Experiment

log = logging.getLogger(__name__)


def generate_ema_rsi_pine(exp: Experiment, params: dict) -> str:
    """Generate Pine Script v5 for the EMA+RSI strategy."""
    ema_fast = params["ema_fast"]
    ema_slow = params["ema_slow"]
    rsi_period = params["rsi_period"]
    rsi_os = params["rsi_os"]
    rsi_ob = params["rsi_ob"]
    tp_pct = params["tp_pct"]
    sl_pct = params["sl_pct"]

    return f"""//@version=5
strategy("EMA+RSI {exp.ticker} {exp.timeframe} | OOS PF {exp.oos_pf:.3f}", overlay=true,
         commission_type=strategy.commission.cash_per_contract,
         commission_value=1.70,
         default_qty_type=strategy.fixed,
         default_qty_value=1)

// Params (from Optuna IS optimization -- DO NOT change without re-running OOS)
ema_fast = {ema_fast}
ema_slow = {ema_slow}
rsi_period = {rsi_period}
rsi_os = {rsi_os}
rsi_ob = {rsi_ob}
tp_pct = {tp_pct}
sl_pct = {sl_pct}

// Indicators
fast = ta.ema(close, ema_fast)
slow = ta.ema(close, ema_slow)
rsi = ta.rsi(close, rsi_period)

// Signals
trend_up = fast > slow
trend_dn = fast < slow
rsi_cross_up = ta.crossover(rsi, rsi_os)
rsi_cross_dn = ta.crossunder(rsi, rsi_ob)

long_entry = trend_up and rsi_cross_up
short_entry = trend_dn and rsi_cross_dn

// Entries
if long_entry
    strategy.entry("Long", strategy.long)

if short_entry
    strategy.entry("Short", strategy.short)

// Exits via TP/SL
strategy.exit("Long Exit", "Long",
    profit=strategy.position_avg_price * tp_pct / 100,
    loss=strategy.position_avg_price * sl_pct / 100)
strategy.exit("Short Exit", "Short",
    profit=strategy.position_avg_price * tp_pct / 100,
    loss=strategy.position_avg_price * sl_pct / 100)

// Plot
plot(fast, color=color.blue, linewidth=1, title="EMA Fast")
plot(slow, color=color.orange, linewidth=2, title="EMA Slow")
hline(rsi_os, "RSI OS", color=color.green, linestyle=hline.style_dashed)
hline(rsi_ob, "RSI OB", color=color.red, linestyle=hline.style_dashed)
"""


GENERATORS = {
    "ema_rsi": generate_ema_rsi_pine,
}


def generate_pine_script(exp: Experiment) -> Path:
    """Generate and save Pine Script for an experiment.

    Returns:
        Path to the saved .pine file
    """
    cfg = get_settings()
    generator = GENERATORS.get(exp.strategy)
    if generator is None:
        raise ValueError(f"No Pine Script generator for strategy '{exp.strategy}'")

    if exp.params is None:
        raise ValueError(f"Experiment {exp.id} has no params (IS_OPT not done?)")

    script = generator(exp, exp.params)

    pine_dir = cfg.pine_dir
    pine_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{exp.strategy}_{exp.ticker}_{exp.timeframe}_exp{exp.id}.pine"
    path = pine_dir / fname

    path.write_text(script)
    log.info("Pine Script saved: %s", path)
    return path
