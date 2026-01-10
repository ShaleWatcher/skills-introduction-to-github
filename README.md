# Kalshi Bitcoin UP/DOWN arbitrage simulator

An **algorithm + scenario simulator** for Kalshi-style “Bitcoin UP or DOWN” binary contracts, focused on detecting **locked (risk-free) pair arbitrage** using top-of-book quotes and then replaying many simulated days to estimate how often it appears and how much it can make under fees + capital limits.

> This is a research/simulation scaffold. Real trading requires exchange-specific APIs, risk controls, and careful handling of fills/latency.

## What “locked arbitrage” means here

If you have two markets that represent **mutually exclusive + collectively exhaustive** outcomes (UP vs DOWN) for the same settlement:

- **Buy YES(UP) + Buy YES(DOWN)** always pays **$1** at expiry (exactly one YES wins).
- **Buy NO(UP) + Buy NO(DOWN)** also always pays **$1** at expiry.

So the “free money” test is:

- **YES pair arb** when \(ask\_yes\_up + ask\_yes\_down + fees < 1\)
- **NO pair arb** when \(ask\_no\_up + ask\_no\_down + fees < 1\)

The code in `kalshi_arbitrage/arbitrage.py` computes this from a `TopOfBook` snapshot (best bid/ask + size).

## Run the scenario simulator

This repo is stdlib-only; use `python3`.

### Monte Carlo run

```bash
python3 -m kalshi_arbitrage.simulate --sims 500 --steps 390 --horizon-days 1 \
  --start-cash 1000 --fee 0.01 --spread 0.01 --mid-noise 0.03 --depth 200
```

You can tune:
- **fees** (`--fee`) and **capital** (`--start-cash`) to see if arbs survive frictions
- **spread/noise** to make markets more/less efficient
- **max size per trade** (`--max-pairs-per-trade`) to model fill limits

### Run tests

```bash
python3 -m unittest discover -s tests -q
```

## Code layout

- `kalshi_arbitrage/models.py`: top-of-book model (`TopOfBook`)
- `kalshi_arbitrage/arbitrage.py`: UP/DOWN pair-arb detection
- `kalshi_arbitrage/scenarios.py`: BTC path model + synthetic orderbooks
- `kalshi_arbitrage/simulate.py`: CLI Monte Carlo runner
- `kalshi_arbitrage/monitor.py`: simple polling monitor (file/URL JSON) for live-style following

## Next step (live “follow the contract”)

To “follow” the live Kalshi UP/DOWN contract you’d add a small adapter that:
- fetches top-of-book for the two markets on an interval (or websocket if available)
- converts Kalshi cents → dollars and fills a `TopOfBook`
- calls `find_up_down_arbs(up, down, fee_per_contract=..., min_profit_per_pair=...)`
- logs alerts (or places orders, if you wire execution + risk checks)

If you can export top-of-book snapshots to a simple JSON shape like:

```json
{
  "yes_bid": 0.48,
  "yes_bid_size": 100,
  "yes_ask": 0.50,
  "yes_ask_size": 120,
  "no_bid": 0.50,
  "no_bid_size": 100,
  "no_ask": 0.52,
  "no_ask_size": 120
}
```

…then you can “follow” them with:

```bash
python3 -m kalshi_arbitrage.monitor --up path/to/up.json --down path/to/down.json --units dollars
```
