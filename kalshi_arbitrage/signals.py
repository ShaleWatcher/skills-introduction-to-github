from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional

from .arbitrage import find_yes_no_arbs
from .kalshi import fetch_orderbook, list_markets, top_of_book_from_orderbook_response


def _now_ts() -> int:
    return int(time.time())


def _parse_rfc3339(s: str) -> datetime:
    # Kalshi uses "2026-01-10T20:30:00Z"
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


@dataclass(frozen=True, slots=True)
class LockSpreadSignal:
    ticker: str
    close_time: str
    yes_limit: float
    no_limit: float
    expected_profit_per_pair: float
    max_pairs_at_top: int


def signal_for_ticker(
    ticker: str,
    *,
    fee_per_contract: float,
    min_profit_per_pair: float,
    depth: int,
) -> Optional[LockSpreadSignal]:
    ob = fetch_orderbook(ticker, depth=depth)
    tob = top_of_book_from_orderbook_response(ob)

    # We want the *locked spread* execution: BUY YES + BUY NO.
    opps = find_yes_no_arbs(
        tob,
        fee_per_contract=fee_per_contract,
        min_profit_per_pair=min_profit_per_pair,
    )
    buy_both = next((o for o in opps if o.legs == ("MKT:YES@ask", "MKT:NO@ask")), None)
    if buy_both is None or buy_both.max_pairs_at_top <= 0:
        return None

    if tob.yes_ask is None or tob.no_ask is None:
        return None

    return LockSpreadSignal(
        ticker=ticker,
        close_time="",
        yes_limit=float(tob.yes_ask),
        no_limit=float(tob.no_ask),
        expected_profit_per_pair=float(buy_both.profit_per_pair),
        max_pairs_at_top=int(buy_both.max_pairs_at_top),
    )


def run_once(
    *,
    series_ticker: str,
    lookahead_minutes: int,
    fee_per_contract: float,
    min_profit_per_pair: float,
    depth: int,
    output: str,
) -> int:
    now = _now_ts()
    max_ts = now + int(lookahead_minutes) * 60

    mkts = list_markets(
        series_ticker=series_ticker,
        min_close_ts=now - 60,  # include currently-open markets
        max_close_ts=max_ts,
        status="",  # allow time filtering across statuses
    )

    rows: list[LockSpreadSignal] = []
    for m in mkts:
        ticker = m.get("ticker")
        if not ticker:
            continue
        sig = signal_for_ticker(
            ticker,
            fee_per_contract=fee_per_contract,
            min_profit_per_pair=min_profit_per_pair,
            depth=depth,
        )
        if sig is None:
            continue
        # attach close_time for sorting/printing
        if m.get("close_time"):
            sig = LockSpreadSignal(**{**asdict(sig), "close_time": str(m["close_time"])})
        rows.append(sig)

    # Sort by soonest close time (then highest profit).
    def sort_key(r: LockSpreadSignal):
        try:
            t = _parse_rfc3339(r.close_time).timestamp() if r.close_time else float("inf")
        except Exception:
            t = float("inf")
        return (t, -r.expected_profit_per_pair)

    rows.sort(key=sort_key)

    if output == "jsonl":
        for r in rows:
            print(json.dumps(asdict(r), sort_keys=True))
    else:
        print(f"=== LOCK-SPREAD signals for {series_ticker} (next {lookahead_minutes} min) ===")
        if not rows:
            print("no signals")
            return 0
        print("ticker | close_time | yes_limit | no_limit | profit/pair | max_pairs_at_top")
        for r in rows:
            print(
                f"{r.ticker} | {r.close_time or '-'} | {r.yes_limit:.4f} | {r.no_limit:.4f} | "
                f"{r.expected_profit_per_pair:.4f} | {r.max_pairs_at_top}"
            )

    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        prog="kalshi_arbitrage.signals",
        description="Generate execution signals to lock the YES/NO spread for forward 15-minute windows.",
    )
    p.add_argument("--series", default="KXBTC15M", help="Kalshi series ticker (default: KXBTC15M).")
    p.add_argument("--lookahead-minutes", type=int, default=120, help="How far forward to scan for windows.")
    p.add_argument("--fee", type=float, default=0.01, help="Fee per contract per leg in $.")
    p.add_argument("--min-profit", type=float, default=0.01, help="Min profit per paired trade (net) in $.")
    p.add_argument("--depth", type=int, default=1, help="Orderbook depth to fetch (1-100).")
    p.add_argument("--output", choices=["table", "jsonl"], default="table", help="Output format.")
    p.add_argument("--interval", type=float, default=0.0, help="If >0, poll repeatedly every N seconds.")
    args = p.parse_args()

    if args.interval and args.interval > 0:
        while True:
            run_once(
                series_ticker=str(args.series),
                lookahead_minutes=int(args.lookahead_minutes),
                fee_per_contract=float(args.fee),
                min_profit_per_pair=float(args.min_profit),
                depth=int(args.depth),
                output=str(args.output),
            )
            time.sleep(float(args.interval))
    else:
        return run_once(
            series_ticker=str(args.series),
            lookahead_minutes=int(args.lookahead_minutes),
            fee_per_contract=float(args.fee),
            min_profit_per_pair=float(args.min_profit),
            depth=int(args.depth),
            output=str(args.output),
        )


if __name__ == "__main__":
    raise SystemExit(main())

