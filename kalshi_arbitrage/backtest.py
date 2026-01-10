from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from .kalshi import KALSHI_PUBLIC_BASE_URL, list_markets


def _now_ts() -> int:
    return int(time.time())


def _parse_rfc3339(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def _to_ts_utc(s: str) -> int:
    # Accept RFC3339 or "YYYY-mm-ddTHH:MM:SSZ" or "YYYY-mm-dd HH:MM" (assumed UTC).
    s = s.strip()
    try:
        return int(_parse_rfc3339(s).timestamp())
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return int(datetime.strptime(s, fmt).replace(tzinfo=timezone.utc).timestamp())
        except Exception:
            continue
    raise ValueError(f"Could not parse timestamp: {s}")


def fetch_market_candlesticks(
    *,
    series_ticker: str,
    market_ticker: str,
    start_ts: int,
    end_ts: int,
    period_interval: int = 1,
    base_url: str = KALSHI_PUBLIC_BASE_URL,
    timeout_s: float = 10.0,
) -> dict[str, Any]:
    import urllib.parse
    import urllib.request

    q = urllib.parse.urlencode(
        {
            "start_ts": str(int(start_ts)),
            "end_ts": str(int(end_ts)),
            "period_interval": str(int(period_interval)),
        }
    )
    url = f"{base_url}/series/{series_ticker}/markets/{market_ticker}/candlesticks?{q}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        data = resp.read()
    return json.loads(data.decode("utf-8"))


def _dollars(x: Any) -> float | None:
    if x is None:
        return None
    # candlesticks return strings like "0.4700"
    return float(x)


@dataclass(frozen=True, slots=True)
class BacktestRow:
    market_ticker: str
    close_time: str
    end_period_ts: int
    yes_bid: float
    yes_ask: float
    profit_per_pair: float


@dataclass(frozen=True, slots=True)
class BacktestSummary:
    series: str
    start_ts: int
    end_ts: int
    markets_scanned: int
    signals: int
    wins: int
    losses: int
    total_profit: float
    avg_profit: Optional[float]
    min_profit: Optional[float]
    max_profit: Optional[float]


def iter_rows(
    *,
    series_ticker: str,
    market_ticker: str,
    close_time: str,
    open_ts: int,
    close_ts: int,
    fee_per_contract: float,
    min_profit_per_pair: float,
) -> Iterable[BacktestRow]:
    # Pull 1-min candlesticks from a little before open to close.
    resp = fetch_market_candlesticks(
        series_ticker=series_ticker,
        market_ticker=market_ticker,
        start_ts=open_ts - 60,
        end_ts=close_ts + 60,
        period_interval=1,
    )
    candles = resp.get("candlesticks", []) or []

    fee = max(0.0, float(fee_per_contract))
    min_profit = float(min_profit_per_pair)

    for c in candles:
        bid = _dollars(((c.get("yes_bid") or {}).get("close_dollars")))
        ask = _dollars(((c.get("yes_ask") or {}).get("close_dollars")))
        end_period_ts = int(c.get("end_period_ts", 0) or 0)
        if bid is None or ask is None:
            continue

        # Locked arb within a single market only exists when the book is crossed:
        # profit = yes_bid - yes_ask - 2*fee
        profit = float(bid) - float(ask) - 2.0 * fee
        if profit >= min_profit:
            yield BacktestRow(
                market_ticker=market_ticker,
                close_time=close_time,
                end_period_ts=end_period_ts,
                yes_bid=float(bid),
                yes_ask=float(ask),
                profit_per_pair=float(profit),
            )


def compute_backtest_rows(
    *,
    series_ticker: str,
    start_ts: int,
    end_ts: int,
    fee_per_contract: float,
    min_profit_per_pair: float,
    max_markets: int = 200,
) -> tuple[list[dict[str, Any]], list[BacktestRow]]:
    mkts = list_markets(
        series_ticker=str(series_ticker),
        min_close_ts=int(start_ts),
        max_close_ts=int(end_ts),
        status="",
    )
    mkts.sort(key=lambda m: (m.get("close_time") or ""))
    mkts = mkts[: max(0, int(max_markets))]

    rows: list[BacktestRow] = []
    for m in mkts:
        ticker = m.get("ticker")
        if not ticker:
            continue
        open_time = m.get("open_time")
        close_time = m.get("close_time")
        if not open_time or not close_time:
            continue
        open_ts = int(_parse_rfc3339(open_time).timestamp())
        close_ts = int(_parse_rfc3339(close_time).timestamp())
        rows.extend(
            list(
                iter_rows(
                    series_ticker=str(series_ticker),
                    market_ticker=str(ticker),
                    close_time=str(close_time),
                    open_ts=open_ts,
                    close_ts=close_ts,
                    fee_per_contract=float(fee_per_contract),
                    min_profit_per_pair=float(min_profit_per_pair),
                )
            )
        )
    return mkts, rows


def compute_backtest_summary(
    *,
    series_ticker: str,
    start_ts: int,
    end_ts: int,
    fee_per_contract: float,
    min_profit_per_pair: float,
    max_markets: int = 200,
) -> BacktestSummary:
    mkts, rows = compute_backtest_rows(
        series_ticker=series_ticker,
        start_ts=start_ts,
        end_ts=end_ts,
        fee_per_contract=fee_per_contract,
        min_profit_per_pair=min_profit_per_pair,
        max_markets=max_markets,
    )
    profits = [r.profit_per_pair for r in rows]
    total = float(sum(profits))
    wins = int(sum(1 for x in profits if x > 0))
    losses = int(sum(1 for x in profits if x < 0))
    avg = (total / len(profits)) if profits else None
    mn = (min(profits) if profits else None)
    mx = (max(profits) if profits else None)
    return BacktestSummary(
        series=str(series_ticker),
        start_ts=int(start_ts),
        end_ts=int(end_ts),
        markets_scanned=int(len(mkts)),
        signals=int(len(rows)),
        wins=wins,
        losses=losses,
        total_profit=total,
        avg_profit=float(avg) if avg is not None else None,
        min_profit=float(mn) if mn is not None else None,
        max_profit=float(mx) if mx is not None else None,
    )


def main() -> int:
    p = argparse.ArgumentParser(
        prog="kalshi_arbitrage.backtest",
        description=(
            "Backtest (historical) 'lock spread' opportunities using Kalshi 1-minute candlesticks. "
            "For a single market, locked arb only occurs when the YES book is crossed (bid > ask)."
        ),
    )
    p.add_argument("--series", default="KXBTC15M", help="Series ticker (default: KXBTC15M).")
    p.add_argument(
        "--start",
        default="",
        help='UTC start time (RFC3339 like "2026-01-10T00:00:00Z" or "YYYY-mm-dd HH:MM").',
    )
    p.add_argument(
        "--end",
        default="",
        help='UTC end time (RFC3339 like "2026-01-11T00:00:00Z" or "YYYY-mm-dd HH:MM").',
    )
    p.add_argument("--lookback-minutes", type=int, default=720, help="If start/end omitted, look back N minutes.")
    p.add_argument("--fee", type=float, default=0.01, help="Fee per contract per leg in $.")
    p.add_argument("--min-profit", type=float, default=0.01, help="Minimum profit per pair (net) in $.")
    p.add_argument("--max-markets", type=int, default=200, help="Safety cap on number of markets to scan.")
    p.add_argument("--output", choices=["summary", "jsonl", "csv"], default="summary", help="Output format.")
    p.add_argument("--csv-path", default="backtest.csv", help="CSV output path (when --output csv).")
    args = p.parse_args()

    end_ts = _to_ts_utc(args.end) if args.end else _now_ts()
    start_ts = _to_ts_utc(args.start) if args.start else (end_ts - int(args.lookback_minutes) * 60)

    mkts, rows = compute_backtest_rows(
        series_ticker=str(args.series),
        start_ts=start_ts,
        end_ts=end_ts,
        fee_per_contract=float(args.fee),
        min_profit_per_pair=float(args.min_profit),
        max_markets=int(args.max_markets),
    )

    if args.output == "jsonl":
        for r in rows:
            print(json.dumps(asdict(r), sort_keys=True))
        return 0

    if args.output == "csv":
        with open(args.csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()) if rows else ["market_ticker"])
            w.writeheader()
            for r in rows:
                w.writerow(asdict(r))
        print(f"wrote {len(rows)} rows to {args.csv_path}")
        return 0

    # summary
    profits = [r.profit_per_pair for r in rows]
    total = sum(profits)
    wins = sum(1 for x in profits if x > 0)
    losses = sum(1 for x in profits if x < 0)
    print(f"=== Backtest: lock-spread opportunities ({args.series}) ===")
    print(f"range_utc: {datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat()} -> {datetime.fromtimestamp(end_ts, tz=timezone.utc).isoformat()}")
    print(f"fee_per_leg=${float(args.fee):.4f} min_profit_per_pair=${float(args.min_profit):.4f}")
    print(f"markets_scanned={len(mkts)} signals={len(rows)} total_profit=${total:.4f}")
    print(f"wins={wins} losses={losses}")
    if profits:
        print(f"avg_profit=${(total/len(profits)):.6f} min=${min(profits):.6f} max=${max(profits):.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

