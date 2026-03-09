"""Instrument constants for micro and mini futures.

These are physical facts about the contracts — they never change.
Copy-verified from V1 and broker specs.
"""

from __future__ import annotations

# Contract class — determines subfolder under data/raw/
# data/raw/micro/MNQ_1m.csv, data/raw/mini/NQ_1m.csv
TICKER_CLASS: dict[str, str] = {
    "MNQ": "micro",
    "MES": "micro",
    "MGC": "micro",
    "NQ": "mini",
    "ES": "mini",
    "GC": "mini",
}

# USD per point (tick value)
CONTRACT_MULT: dict[str, float] = {
    "MNQ": 2.0,  # Micro E-mini Nasdaq-100: $2 per point
    "MES": 5.0,  # Micro E-mini S&P 500:    $5 per point
    "MGC": 10.0,  # Micro Gold:               $10 per point
    "NQ": 20.0,  # E-mini Nasdaq-100:        $20 per point
    "ES": 50.0,  # E-mini S&P 500:           $50 per point
    "GC": 100.0,  # Gold:                     $100 per point
}

# Estimated initial margin per contract (approx — verify with broker)
MARGIN_EST: dict[str, float] = {
    "MNQ": 1_200,
    "MES": 650,
    "MGC": 800,
    "NQ": 12_000,
    "ES": 6_500,
    "GC": 8_000,
}

# Commission per round-trip: NinjaTrader fees + exchange + slippage
COMMISSION_RT: float = 3.40  # USD

# Tickers by contract class
MICRO_TICKERS: list[str] = ["MNQ", "MES", "MGC"]
MINI_TICKERS: list[str] = ["NQ", "ES", "GC"]

# All supported tickers
TICKERS: list[str] = MICRO_TICKERS + MINI_TICKERS

# Supported timeframes
TIMEFRAMES: list[str] = ["1m", "5m", "15m"]

# Yahoo Finance symbols
YF_SYMBOLS: dict[str, str] = {
    "MNQ": "MNQ=F",
    "MES": "MES=F",
    "MGC": "MGC=F",
    "NQ": "NQ=F",
    "ES": "ES=F",
    "GC": "GC=F",
}

# Approximate bars per trading day per timeframe
BARS_PER_DAY: dict[str, int] = {
    "1m": 1_390,  # ~23.2 hours * 60 min (24/5 minus weekend)
    "5m": 278,
    "15m": 93,
}


def ticker_data_dir(ticker: str, data_dir: str | object) -> str:
    """Resolve the data subfolder for a ticker: data_dir/micro/ or data_dir/mini/."""
    from pathlib import Path

    cls = TICKER_CLASS.get(ticker)
    if cls is None:
        raise ValueError(f"Unknown ticker: {ticker}")
    return str(Path(str(data_dir)) / cls)
