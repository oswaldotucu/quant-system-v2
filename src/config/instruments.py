"""Instrument constants for MNQ, MES, MGC.

These are physical facts about the contracts — they never change.
Copy-verified from V1 and broker specs.
"""

from __future__ import annotations

# USD per point (tick value)
CONTRACT_MULT: dict[str, float] = {
    "MNQ": 2.0,   # Micro E-mini Nasdaq-100: $2 per point
    "MES": 5.0,   # Micro E-mini S&P 500:    $5 per point
    "MGC": 10.0,  # Micro Gold:               $10 per point
}

# Estimated initial margin per contract (approx — verify with broker)
MARGIN_EST: dict[str, float] = {
    "MNQ": 1_200,
    "MES": 650,
    "MGC": 800,
}

# Commission per round-trip: NinjaTrader fees + exchange + slippage
COMMISSION_RT: float = 3.40  # USD

# Supported tickers
TICKERS: list[str] = ["MNQ", "MES", "MGC"]

# Supported timeframes
TIMEFRAMES: list[str] = ["1m", "5m", "15m"]

# Yahoo Finance symbols
YF_SYMBOLS: dict[str, str] = {
    "MNQ": "MNQ=F",
    "MES": "MES=F",
    "MGC": "MGC=F",
}

# Approximate bars per trading day per timeframe
BARS_PER_DAY: dict[str, int] = {
    "1m":  1_390,  # ~23.2 hours * 60 min (24/5 minus weekend)
    "5m":  278,
    "15m": 93,
}
