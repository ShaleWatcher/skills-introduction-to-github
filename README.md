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

## Generate “lock the spread” execution signals (forward 15-minute windows)

This scans upcoming markets in the `KXBTC15M` series and outputs a signal when the market’s **YES/NO pair** allows a **locked payout** (buy YES + buy NO) at a net profit after fees.

```bash
python3 -m kalshi_arbitrage.signals --series KXBTC15M --lookahead-minutes 240 --fee 0.01 --min-profit 0.01
```

For machine consumption:

```bash
python3 -m kalshi_arbitrage.signals --output jsonl --lookahead-minutes 240
```

## Backtest (historical wins/losses) for “lock spread” opportunities

This uses Kalshi’s **1-minute candlesticks** to find moments where the YES book is **crossed** (bid > ask), which is the only way a single-market “lock spread” can be risk-free.

```bash
python3 -m kalshi_arbitrage.backtest --series KXBTC15M --lookback-minutes 720 --fee 0.01 --min-profit 0.01
```

Export rows:

```bash
python3 -m kalshi_arbitrage.backtest --output csv --csv-path backtest.csv
python3 -m kalshi_arbitrage.backtest --output jsonl
```

## Web dashboard (single screen)

This serves a single-page dashboard showing **Live signals + Backtest summary** on one screen.

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the server:

```bash
python3 -m kalshi_arbitrage.web --host 0.0.0.0 --port 8000
```

Open on your iPad Safari:
- `http://<your-server-ip>:8000/`

You can tune parameters via URL query params, e.g.:
- `/?lookahead=240&lookback=1440&fee=0.01&min_profit=0.01&refresh=10&depth=1`

### Optional: execution from the dashboard

Execution is **disabled by default**. To enable trading buttons, set these env vars on the server:

- `KALSHI_ENABLE_EXECUTION=1`
- `KALSHI_EXECUTION_MODE=demo` (recommended) or `live`
- `KALSHI_ACCESS_KEY=<your api key id>`
- `KALSHI_PRIVATE_KEY_PATH=/path/to/your/private.key`
- `KALSHI_TRADE_BASE_URL=https://demo-api.kalshi.co` (optional; defaults based on mode)

If (and only if) you explicitly set `KALSHI_EXECUTION_MODE=live`, you must also set:

- `KALSHI_CONFIRM_LIVE=I_UNDERSTAND`

Then the dashboard “Trade” button can submit a **Fill-or-Kill** paired order (BUY YES + BUY NO) for the selected ticker when a valid lock-spread signal exists.

## Code layout

- `kalshi_arbitrage/models.py`: top-of-book model (`TopOfBook`)
- `kalshi_arbitrage/arbitrage.py`: UP/DOWN pair-arb detection
- `kalshi_arbitrage/scenarios.py`: BTC path model + synthetic orderbooks
- `kalshi_arbitrage/simulate.py`: CLI Monte Carlo runner
- `kalshi_arbitrage/monitor.py`: simple polling monitor (file/URL JSON) for live-style following
- `kalshi_arbitrage/signals.py`: scans forward windows and emits “lock spread” signals
- `kalshi_arbitrage/backtest.py`: historical backtest of lock-spread opportunities (candlesticks)
- `kalshi_arbitrage/web.py`: single-page dashboard (Safari-friendly)
- `kalshi_arbitrage/execution.py`: optional authenticated Kalshi order execution

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

### Monitor a live Kalshi market (by URL)

Example (your market):

```bash
python3 -m kalshi_arbitrage.monitor --kalshi-url "https://kalshi.com/markets/kxbtc15m/bitcoin-price-up-down/kxbtc15m-26jan101400"
```

This uses Kalshi’s documented base URL (`https://api.elections.kalshi.com/trade-api/v2`) to fetch `/markets/{ticker}/orderbook` and then checks **single-market YES/NO** locked arbitrage.
