from __future__ import annotations

import argparse
import random
import statistics
from dataclasses import dataclass

from .arbitrage import Strategy, best_arb, find_up_down_arbs
from .models import TopOfBook
from .scenarios import GBMParams, MicrostructureParams, gbm_step, prob_finish_up_vs_anchor, synth_market_from_fair


@dataclass(slots=True)
class SimResult:
    pnl: float
    trades: int
    pairs: int
    final_spot: float


def _pair_cost(up: TopOfBook, down: TopOfBook, *, strategy: Strategy, fee_per_contract: float) -> float:
    fee = max(0.0, float(fee_per_contract))
    if strategy == Strategy.BUY_YES_BOTH:
        if up.yes_ask is None or down.yes_ask is None:
            return float("inf")
        return up.yes_ask + down.yes_ask + 2.0 * fee
    if strategy == Strategy.BUY_NO_BOTH:
        if up.no_ask is None or down.no_ask is None:
            return float("inf")
        return up.no_ask + down.no_ask + 2.0 * fee
    raise ValueError(f"Unsupported strategy in simulator: {strategy}")


def run_one_sim(
    *,
    seed: int,
    start_cash: float,
    start_spot: float,
    horizon_days: float,
    steps: int,
    gbm: GBMParams,
    micro: MicrostructureParams,
    fee_per_contract: float,
    min_profit_per_pair: float,
    max_pairs_per_trade: int,
) -> SimResult:
    rng = random.Random(seed)

    anchor_spot = float(start_spot)
    spot = float(start_spot)
    cash = float(start_cash)

    total_cost = 0.0
    total_payout = 0.0
    trades = 0
    pairs = 0

    steps = max(1, int(steps))
    horizon_years = float(horizon_days) / 365.0
    dt_years = horizon_years / steps

    for i in range(steps):
        tau = max(0.0, horizon_years - i * dt_years)
        fair_up = prob_finish_up_vs_anchor(
            spot_now=spot,
            anchor_spot=anchor_spot,
            tau_years=tau,
            mu=gbm.mu,
            sigma=gbm.sigma,
        )

        # Independent noise per market creates cross-market discrepancies.
        up = synth_market_from_fair(fair_up, params=micro, rng=rng)
        down = synth_market_from_fair(1.0 - fair_up, params=micro, rng=rng)

        opps = find_up_down_arbs(
            up,
            down,
            fee_per_contract=fee_per_contract,
            min_profit_per_pair=min_profit_per_pair,
        )

        # Sim focuses on "locked" buys (capital-limited, no margin model).
        opp = best_arb([o for o in opps if o.strategy in (Strategy.BUY_YES_BOTH, Strategy.BUY_NO_BOTH)])
        if opp is not None and opp.max_pairs_at_top > 0:
            pair_cost = _pair_cost(up, down, strategy=opp.strategy, fee_per_contract=fee_per_contract)
            if pair_cost > 0.0:
                affordable = int(cash // pair_cost)
                qty = min(int(max_pairs_per_trade), int(opp.max_pairs_at_top), affordable)
                if qty > 0:
                    cost = pair_cost * qty
                    cash -= cost
                    total_cost += cost
                    total_payout += 1.0 * qty
                    trades += 1
                    pairs += qty

        # Advance BTC spot.
        spot = gbm_step(spot, mu=gbm.mu, sigma=gbm.sigma, dt_years=dt_years, rng=rng)

    # Settle all paired positions at expiry.
    cash += total_payout
    pnl = cash - start_cash
    return SimResult(pnl=pnl, trades=trades, pairs=pairs, final_spot=spot)


def main() -> int:
    p = argparse.ArgumentParser(
        prog="kalshi_arbitrage.simulate",
        description="Simulate locked arbitrage frequency for Kalshi-style UP/DOWN contracts.",
    )
    p.add_argument("--sims", type=int, default=500, help="Number of Monte Carlo runs.")
    p.add_argument("--steps", type=int, default=390, help="Steps per run (e.g. 390 ~ 1-min bars in US session).")
    p.add_argument("--horizon-days", type=float, default=1.0, help="Contract horizon in days.")
    p.add_argument("--start-spot", type=float, default=50000.0, help="Initial BTC spot price for the run.")
    p.add_argument("--start-cash", type=float, default=1000.0, help="Starting cash (USD) for the arbitrage bot.")

    p.add_argument("--mu", type=float, default=0.0, help="GBM drift (annualized).")
    p.add_argument("--sigma", type=float, default=0.6, help="GBM vol (annualized).")

    p.add_argument("--spread", type=float, default=0.01, help="Synthetic market spread in $ (0-1).")
    p.add_argument("--mid-noise", type=float, default=0.03, help="Synthetic mid noise in $ (0-1).")
    p.add_argument("--depth", type=int, default=200, help="Top-of-book size per side.")

    p.add_argument("--fee", type=float, default=0.01, help="Fee per contract per leg in $.")
    p.add_argument("--min-profit", type=float, default=0.0, help="Minimum profit per paired trade in $.")
    p.add_argument("--max-pairs-per-trade", type=int, default=50, help="Cap size per opportunity.")

    p.add_argument("--seed", type=int, default=1, help="Base RNG seed; each sim uses seed+i.")

    args = p.parse_args()

    gbm = GBMParams(mu=args.mu, sigma=args.sigma)
    micro = MicrostructureParams(spread=args.spread, mid_noise=args.mid_noise, depth=args.depth)

    results: list[SimResult] = []
    for i in range(max(1, int(args.sims))):
        results.append(
            run_one_sim(
                seed=int(args.seed) + i,
                start_cash=float(args.start_cash),
                start_spot=float(args.start_spot),
                horizon_days=float(args.horizon_days),
                steps=int(args.steps),
                gbm=gbm,
                micro=micro,
                fee_per_contract=float(args.fee),
                min_profit_per_pair=float(args.min_profit),
                max_pairs_per_trade=int(args.max_pairs_per_trade),
            )
        )

    pnls = [r.pnl for r in results]
    trades = [r.trades for r in results]
    pairs = [r.pairs for r in results]

    mean_pnl = statistics.mean(pnls) if pnls else 0.0
    stdev_pnl = statistics.pstdev(pnls) if len(pnls) > 1 else 0.0
    mean_trades = statistics.mean(trades) if trades else 0.0
    mean_pairs = statistics.mean(pairs) if pairs else 0.0
    win_rate = sum(1 for x in pnls if x > 0.0) / len(pnls) if pnls else 0.0

    print("=== Kalshi UP/DOWN locked-arb simulation ===")
    print(f"sims={len(results)} steps={args.steps} horizon_days={args.horizon_days}")
    print(f"micro: spread={args.spread:.4f} mid_noise={args.mid_noise:.4f} depth={args.depth}")
    print(f"fees: fee_per_contract=${args.fee:.4f} min_profit_per_pair=${args.min_profit:.4f}")
    print(f"capital: start_cash=${args.start_cash:.2f} max_pairs_per_trade={args.max_pairs_per_trade}")
    print("---")
    print(f"mean_pnl=${mean_pnl:.4f} stdev_pnl=${stdev_pnl:.4f} win_rate={win_rate:.1%}")
    print(f"mean_trades={mean_trades:.2f} mean_pairs={mean_pairs:.2f}")
    print(f"min_pnl=${min(pnls):.4f} max_pnl=${max(pnls):.4f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

