from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

from .models import TopOfBook


KALSHI_PUBLIC_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"


def ticker_from_kalshi_url(url: str) -> str:
    """
    Extract the market ticker from a Kalshi market URL like:
        https://kalshi.com/markets/<category>/<event>/<ticker>
    """

    parsed = urllib.parse.urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        raise ValueError("Could not parse ticker from URL path")
    return parts[-1]


@dataclass(frozen=True, slots=True)
class KalshiOrderbookTop:
    yes_bid: Optional[float]
    yes_bid_size: int
    no_bid: Optional[float]
    no_bid_size: int


def _best_bid(levels: Any) -> tuple[Optional[float], int]:
    """
    Kalshi orderbook levels are [price_in_cents, count] (or null if empty).
    """

    if not levels:
        return None, 0
    # Expect levels sorted best-to-worse (highest first).
    try:
        price_cents, count = levels[0]
        return float(price_cents) / 100.0, int(count)
    except Exception:
        return None, 0


def fetch_orderbook(
    ticker: str,
    *,
    depth: int = 1,
    base_url: str = KALSHI_PUBLIC_BASE_URL,
    timeout_s: float = 10.0,
) -> dict[str, Any]:
    """
    Fetch the current orderbook for a market ticker.

    Note: This uses Kalshi's documented public base URL. Some endpoints may be
    publicly accessible (HTTP 200) even without trading authentication.
    """

    q = urllib.parse.urlencode({"depth": str(int(depth))})
    url = f"{base_url}/markets/{ticker}/orderbook?{q}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        data = resp.read()
    return json.loads(data.decode("utf-8"))


def top_of_book_from_orderbook_response(resp: dict[str, Any]) -> TopOfBook:
    """
    Convert Kalshi GetMarketOrderbookResponse -> TopOfBook.

    Kalshi's orderbook endpoint exposes *bids* for YES and NO. For a binary
    contract, the implied asks can be derived:
      yes_ask = 1 - no_bid
      no_ask  = 1 - yes_bid

    Sizes for implied asks are taken from the opposite best-bid size.
    """

    ob = (resp or {}).get("orderbook", {}) or {}
    yes_levels = ob.get("yes", None)
    no_levels = ob.get("no", None)

    yes_bid, yes_bid_size = _best_bid(yes_levels)
    no_bid, no_bid_size = _best_bid(no_levels)

    yes_ask = (1.0 - no_bid) if no_bid is not None else None
    no_ask = (1.0 - yes_bid) if yes_bid is not None else None

    return TopOfBook(
        yes_bid=yes_bid,
        yes_bid_size=yes_bid_size,
        yes_ask=yes_ask,
        yes_ask_size=no_bid_size if yes_ask is not None else 0,
        no_bid=no_bid,
        no_bid_size=no_bid_size,
        no_ask=no_ask,
        no_ask_size=yes_bid_size if no_ask is not None else 0,
    ).normalized()

