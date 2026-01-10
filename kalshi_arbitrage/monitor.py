from __future__ import annotations

import argparse
import json
import time
import urllib.request
from dataclasses import asdict
from typing import Any

from .arbitrage import best_arb, find_up_down_arbs
from .models import TopOfBook


def _load_json(source: str) -> dict[str, Any]:
    if source.startswith("http://") or source.startswith("https://"):
        with urllib.request.urlopen(source, timeout=10) as resp:
            data = resp.read()
        return json.loads(data.decode("utf-8"))
    with open(source, "r", encoding="utf-8") as f:
        return json.load(f)


def _tob_from_json(obj: dict[str, Any], *, units: str) -> TopOfBook:
    def get_float(key: str) -> float | None:
        v = obj.get(key, None)
        if v is None:
            return None
        return float(v)

    def get_int(key: str) -> int:
        v = obj.get(key, 0)
        try:
            return int(v)
        except Exception:
            return 0

    scale = 0.01 if units == "cents" else 1.0
    return TopOfBook(
        yes_bid=(get_float("yes_bid") * scale if get_float("yes_bid") is not None else None),
        yes_bid_size=get_int("yes_bid_size"),
        yes_ask=(get_float("yes_ask") * scale if get_float("yes_ask") is not None else None),
        yes_ask_size=get_int("yes_ask_size"),
        no_bid=(get_float("no_bid") * scale if get_float("no_bid") is not None else None),
        no_bid_size=get_int("no_bid_size"),
        no_ask=(get_float("no_ask") * scale if get_float("no_ask") is not None else None),
        no_ask_size=get_int("no_ask_size"),
    )


def main() -> int:
    p = argparse.ArgumentParser(
        prog="kalshi_arbitrage.monitor",
        description="Poll two UP/DOWN top-of-book snapshots and print locked arb opportunities.",
    )
    p.add_argument("--up", required=True, help="Path or URL to UP top-of-book JSON.")
    p.add_argument("--down", required=True, help="Path or URL to DOWN top-of-book JSON.")
    p.add_argument("--units", choices=["dollars", "cents"], default="dollars", help="Input price units.")
    p.add_argument("--fee", type=float, default=0.01, help="Fee per contract per leg in $.")
    p.add_argument("--min-profit", type=float, default=0.0, help="Minimum profit per pair in $.")
    p.add_argument("--interval", type=float, default=1.0, help="Polling interval in seconds.")
    args = p.parse_args()

    while True:
        up = _tob_from_json(_load_json(args.up), units=args.units)
        down = _tob_from_json(_load_json(args.down), units=args.units)

        opps = find_up_down_arbs(
            up,
            down,
            fee_per_contract=float(args.fee),
            min_profit_per_pair=float(args.min_profit),
        )
        opp = best_arb(opps)

        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        if opp is None:
            print(f"[{ts}] no locked arb")
        else:
            print(
                f"[{ts}] {opp.strategy} profit_per_pair=${opp.profit_per_pair:.4f} "
                f"max_pairs_at_top={opp.max_pairs_at_top} legs={opp.legs}"
            )

        time.sleep(max(0.1, float(args.interval)))


if __name__ == "__main__":
    raise SystemExit(main())

