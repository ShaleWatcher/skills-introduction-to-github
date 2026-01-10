from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


def _clamp_price(price: float) -> float:
    # Prices are in dollars for a $1-settled contract.
    if price < 0.0:
        return 0.0
    if price > 1.0:
        return 1.0
    return price


@dataclass(frozen=True, slots=True)
class TopOfBook:
    """
    Minimal top-of-book view for a binary ($0/$1) market.

    All prices are in dollars (0.00 - 1.00). Sizes are contract counts.
    If a quote is unavailable, the price is None and size is 0.
    """

    yes_bid: Optional[float] = None
    yes_bid_size: int = 0
    yes_ask: Optional[float] = None
    yes_ask_size: int = 0

    no_bid: Optional[float] = None
    no_bid_size: int = 0
    no_ask: Optional[float] = None
    no_ask_size: int = 0

    def normalized(self) -> "TopOfBook":
        # Clamp (defensively) and ensure sizes are non-negative ints.
        return TopOfBook(
            yes_bid=_clamp_price(self.yes_bid) if self.yes_bid is not None else None,
            yes_bid_size=max(0, int(self.yes_bid_size)),
            yes_ask=_clamp_price(self.yes_ask) if self.yes_ask is not None else None,
            yes_ask_size=max(0, int(self.yes_ask_size)),
            no_bid=_clamp_price(self.no_bid) if self.no_bid is not None else None,
            no_bid_size=max(0, int(self.no_bid_size)),
            no_ask=_clamp_price(self.no_ask) if self.no_ask is not None else None,
            no_ask_size=max(0, int(self.no_ask_size)),
        )

