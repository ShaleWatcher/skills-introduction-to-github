from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional

from .models import TopOfBook


class Strategy(str, Enum):
    BUY_YES_BOTH = "buy_yes_both"
    BUY_NO_BOTH = "buy_no_both"
    SELL_YES_BOTH = "sell_yes_both"
    SELL_NO_BOTH = "sell_no_both"


@dataclass(frozen=True, slots=True)
class ArbOpportunity:
    """
    Represents a *locked* (risk-free under perfect execution) $1 payout trade.

    For mutually exclusive + collectively exhaustive outcomes (UP/DOWN):
    - Buy YES on both => payout is always $1
    - Buy NO on both  => payout is always $1
    - Sell YES on both => you owe $1 at settlement
    - Sell NO on both  => you owe $1 at settlement
    """

    strategy: Strategy
    profit_per_pair: float  # in dollars, net of fees
    max_pairs_at_top: int
    legs: tuple[str, str]  # ("UP:YES@ask", "DOWN:YES@ask"), etc.


def _min_int(a: int, b: int) -> int:
    return a if a < b else b


def _as_fee(fee_per_contract: float) -> float:
    return max(0.0, float(fee_per_contract))


def find_up_down_arbs(
    up: TopOfBook,
    down: TopOfBook,
    *,
    fee_per_contract: float = 0.0,
    min_profit_per_pair: float = 0.0,
) -> list[ArbOpportunity]:
    """
    Detect locked arbitrage between an UP market and its complementary DOWN market.

    Assumes each contract settles to $1 if its side is correct, else $0.
    Returned opportunities are computed from top-of-book quotes and sizes.
    """

    up = up.normalized()
    down = down.normalized()

    fee = _as_fee(fee_per_contract)
    min_profit = float(min_profit_per_pair)

    opportunities: list[ArbOpportunity] = []

    # BUY YES on both (payout always $1)
    if up.yes_ask is not None and down.yes_ask is not None:
        cost = up.yes_ask + down.yes_ask + 2.0 * fee
        profit = 1.0 - cost
        if profit >= min_profit:
            opportunities.append(
                ArbOpportunity(
                    strategy=Strategy.BUY_YES_BOTH,
                    profit_per_pair=profit,
                    max_pairs_at_top=_min_int(up.yes_ask_size, down.yes_ask_size),
                    legs=("UP:YES@ask", "DOWN:YES@ask"),
                )
            )

    # BUY NO on both (payout always $1)
    if up.no_ask is not None and down.no_ask is not None:
        cost = up.no_ask + down.no_ask + 2.0 * fee
        profit = 1.0 - cost
        if profit >= min_profit:
            opportunities.append(
                ArbOpportunity(
                    strategy=Strategy.BUY_NO_BOTH,
                    profit_per_pair=profit,
                    max_pairs_at_top=_min_int(up.no_ask_size, down.no_ask_size),
                    legs=("UP:NO@ask", "DOWN:NO@ask"),
                )
            )

    # SELL YES on both (liability always $1)
    if up.yes_bid is not None and down.yes_bid is not None:
        revenue = up.yes_bid + down.yes_bid - 2.0 * fee
        profit = revenue - 1.0
        if profit >= min_profit:
            opportunities.append(
                ArbOpportunity(
                    strategy=Strategy.SELL_YES_BOTH,
                    profit_per_pair=profit,
                    max_pairs_at_top=_min_int(up.yes_bid_size, down.yes_bid_size),
                    legs=("UP:YES@bid", "DOWN:YES@bid"),
                )
            )

    # SELL NO on both (liability always $1)
    if up.no_bid is not None and down.no_bid is not None:
        revenue = up.no_bid + down.no_bid - 2.0 * fee
        profit = revenue - 1.0
        if profit >= min_profit:
            opportunities.append(
                ArbOpportunity(
                    strategy=Strategy.SELL_NO_BOTH,
                    profit_per_pair=profit,
                    max_pairs_at_top=_min_int(up.no_bid_size, down.no_bid_size),
                    legs=("UP:NO@bid", "DOWN:NO@bid"),
                )
            )

    # Highest profit first.
    opportunities.sort(key=lambda o: o.profit_per_pair, reverse=True)
    return opportunities


def best_arb(
    opportunities: Iterable[ArbOpportunity],
) -> Optional[ArbOpportunity]:
    best: Optional[ArbOpportunity] = None
    for opp in opportunities:
        if best is None or opp.profit_per_pair > best.profit_per_pair:
            best = opp
    return best

