# Deployment Checklist

Follow this before going live with any FWD_READY strategy.

## Pre-Live

### 1. TradingView Verification
- [ ] Load Pine Script from data/pine_scripts/
- [ ] Apply to correct instrument + timeframe
- [ ] Set date range to 2024-01-01 in TradingView backtest
- [ ] Confirm OOS PF is within 5% of automated result
- [ ] Commission: $1.70/side (cash_per_contract) in strategy settings

### 2. Paper Trade (optional, 1-2 weeks)
- [ ] Enable paper trading in broker
- [ ] Run strategy for at least 5 trades
- [ ] Verify entry/exit signals match TradingView

### 3. Broker Setup
- [ ] Fund account (min $5,000 recommended per contract)
- [ ] Enable micro futures trading
- [ ] Set default quantity: 1 contract
- [ ] Set alerts for risk limits

---

## Daily Operation

### Pre-session
- [ ] Check system is running (http://localhost:8080)
- [ ] Verify data is fresh (Settings page)
- [ ] Check no error_msg on deployed experiments

### Post-session
- [ ] Check daily P&L vs expected
- [ ] Note any anomalies (spike, news event, data gap)

---

## Kill Switch Protocol

Stop trading immediately if:
- 5 consecutive losing trades (max_consecutive_losses exceeded)
- Daily loss > 3x average day
- Weekly loss > monthly expected
- Any server error in automation log

After stopping:
1. Download Pine Script and re-verify in TradingView
2. Check if data is stale (run make fetch-data)
3. Check if OOS period has changed regime (re-run OOS_VAL gate)

---

## Position Sizing

Per-instrument at current levels (adjust for account size):

| Instrument | 1 contract | Margin (est.) | Max risk/trade |
|---|---|---|---|
| MNQ | $2/pt | $1,200 | $336 (at 2.8% SL) |
| MES | $5/pt | $650 | $175 |
| MGC | $10/pt | $800 | $280 |

To scale: if max DD is -$7,155 for 3 contracts, maintain 3:1 capital:max-DD ratio.
At $289/day expected and -$7,155 max DD: ~25 days to recover.

---

## Proven Contract Multipliers

```python
CONTRACT_MULT = {"MNQ": 2, "MES": 5, "MGC": 10}  # USD per point
COMMISSION_RT = 3.40  # USD per round-trip
```

**CRITICAL**: commission_rt already includes both sides. Do not double-count.
