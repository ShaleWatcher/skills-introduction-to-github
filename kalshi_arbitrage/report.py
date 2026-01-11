from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from .backtest import fetch_market_candlesticks
from .kalshi import KALSHI_PUBLIC_BASE_URL, list_markets


def _now_ts() -> int:
    return int(time.time())


def _parse_rfc3339(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def _dollars(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(x)
    except Exception:
        return None


@dataclass(frozen=True, slots=True)
class MarketWindowReport:
    ticker: str
    status: str
    open_time: str
    close_time: str
    triggered: bool
    triggers: int
    best_profit_per_contract: Optional[float]
    total_profit_1ct: float


def _per_minute_spread_arb_profit(yes_bid: float, yes_ask: float, *, fee_per_contract: float) -> float:
    """
    Approximate immediate spread-arb profit within a single market:
        buy at ask, sell at bid  => profit = bid - ask - 2*fee

    This is NOT the YES+NO lock payout; it's a crossed-book / spread capture check.
    """

    fee = max(0.0, float(fee_per_contract))
    return float(yes_bid) - float(yes_ask) - 2.0 * fee


def report_for_market(
    *,
    series_ticker: str,
    ticker: str,
    status: str,
    open_time: str,
    close_time: str,
    fee_per_contract: float,
    min_profit: float,
) -> MarketWindowReport:
    open_ts = int(_parse_rfc3339(open_time).timestamp())
    close_ts = int(_parse_rfc3339(close_time).timestamp())

    # Pull 1-min candles across the window.
    resp = fetch_market_candlesticks(
        series_ticker=series_ticker,
        market_ticker=ticker,
        start_ts=open_ts - 60,
        end_ts=close_ts + 60,
        period_interval=1,
        base_url=KALSHI_PUBLIC_BASE_URL,
    )
    candles = resp.get("candlesticks", []) or []

    best: Optional[float] = None
    triggers = 0
    total_profit = 0.0

    for c in candles:
        bid = _dollars(((c.get("yes_bid") or {}).get("close_dollars")))
        ask = _dollars(((c.get("yes_ask") or {}).get("close_dollars")))
        if bid is None or ask is None:
            continue
        p = _per_minute_spread_arb_profit(bid, ask, fee_per_contract=fee_per_contract)
        if p >= float(min_profit):
            triggers += 1
            total_profit += p  # assumes 1 contract executed per trigger
            best = p if best is None else max(best, p)

    return MarketWindowReport(
        ticker=ticker,
        status=status,
        open_time=open_time,
        close_time=close_time,
        triggered=triggers > 0,
        triggers=triggers,
        best_profit_per_contract=best,
        total_profit_1ct=float(total_profit),
    )


def main() -> int:
    p = argparse.ArgumentParser(
        prog="kalshi_arbitrage.report",
        description="Report whether the model would have triggered over the last N minutes of 15m windows.",
    )
    p.add_argument("--series", default="KXBTC15M", help="Series ticker (default: KXBTC15M).")
    p.add_argument("--minutes", type=int, default=120, help="Lookback minutes (default: 120).")
    p.add_argument("--fee", type=float, default=0.01, help="Fee per contract per leg in $.")
    p.add_argument(
        "--min-profit",
        type=float,
        default=0.0,
        help="Minimum profit per contract per trigger in $ (default: 0.0).",
    )
    args = p.parse_args()

    now = _now_ts()
    start = now - int(args.minutes) * 60

    # Closed windows in lookback range.
    closed = list_markets(
        series_ticker=str(args.series),
        min_close_ts=int(start),
        max_close_ts=int(now),
        status="",  # time filtering
    )
    # Current/open windows (may be 0 or 1 typically).
    open_mkts = list_markets(
        series_ticker=str(args.series),
        min_close_ts=int(now - 6 * 60 * 60),
        max_close_ts=int(now + 6 * 60 * 60),
        status="open",
    )

    # Deduplicate by ticker (the range queries can overlap).
    by_ticker: dict[str, dict[str, Any]] = {}
    for m in closed + open_mkts:
        t = m.get("ticker")
        if t:
            by_ticker[str(t)] = m

    mkts = list(by_ticker.values())
    mkts.sort(key=lambda m: (m.get("close_time") or "", m.get("open_time") or ""))

    reports: list[MarketWindowReport] = []
    for m in mkts:
        t = m.get("ticker")
        ot = m.get("open_time")
        ct = m.get("close_time")
        if not t or not ot or not ct:
            continue
        reports.append(
            report_for_market(
                series_ticker=str(args.series),
                ticker=str(t),
                status=str(m.get("status") or ""),
                open_time=str(ot),
                close_time=str(ct),
                fee_per_contract=float(args.fee),
                min_profit=float(args.min_profit),
            )
        )

    # Print.
    print(f"=== Report: {args.series} last {args.minutes} minutes (plus current open) ===")
    print(f"assumption: execute 1 contract per trigger; profit = yes_bid - yes_ask - 2*fee")
    print(f"fee_per_leg=${float(args.fee):.4f} min_profit=${float(args.min_profit):.4f}")
    print("---")
    if not reports:
        print("no markets found in range")
        return 0
    print("ticker | status | open_time | close_time | triggered | triggers | best_profit | total_profit(1ct)")
    for r in reports:
        best = "-" if r.best_profit_per_contract is None else f"{r.best_profit_per_contract:.4f}"
        print(
            f"{r.ticker} | {r.status} | {r.open_time} | {r.close_time} | "
            f"{'YES' if r.triggered else 'NO'} | {r.triggers} | {best} | {r.total_profit_1ct:.4f}"
        )

    total = sum(r.total_profit_1ct for r in reports)
    print("---")
    print(f"total_profit_across_windows(1ct)=${total:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

