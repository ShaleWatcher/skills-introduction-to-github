from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .models import TopOfBook


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


@dataclass(frozen=True, slots=True)
class GBMParams:
    """
    Geometric Brownian Motion:
        dS/S = mu dt + sigma dW
    """

    mu: float = 0.0
    sigma: float = 0.6  # BTC is volatile; tune as desired


def gbm_step(price: float, *, mu: float, sigma: float, dt_years: float, rng: random.Random) -> float:
    # Exact discretization: S_{t+dt} = S_t * exp((mu-0.5*sigma^2)*dt + sigma*sqrt(dt)*Z)
    z = rng.gauss(0.0, 1.0)
    drift = (mu - 0.5 * sigma * sigma) * dt_years
    diffusion = sigma * math.sqrt(dt_years) * z
    return price * math.exp(drift + diffusion)


def prob_finish_up_vs_anchor(
    *,
    spot_now: float,
    anchor_spot: float,
    tau_years: float,
    mu: float,
    sigma: float,
) -> float:
    """
    P(S_T > anchor_spot | S_t = spot_now) under GBM assumptions.

    For a "UP vs DOWN" contract anchored to the starting price, this gives the
    *fair* UP probability as time evolves.
    """

    if tau_years <= 0.0:
        return 1.0 if spot_now > anchor_spot else 0.0
    if sigma <= 0.0:
        # Deterministic drift-only.
        forward = spot_now * math.exp(mu * tau_years)
        return 1.0 if forward > anchor_spot else 0.0

    denom = sigma * math.sqrt(tau_years)
    num = math.log(anchor_spot / spot_now) - (mu - 0.5 * sigma * sigma) * tau_years
    z = num / denom
    # P(S_T > anchor) = 1 - Phi(z)
    return max(0.0, min(1.0, 1.0 - normal_cdf(z)))


@dataclass(frozen=True, slots=True)
class MicrostructureParams:
    """
    Simple synthetic orderbook model:
    - mid deviates from fair by a small noise term
    - a fixed spread is applied around the mid
    - NO prices are derived as 1 - YES (to avoid single-market internal arb)
    """

    spread: float = 0.01  # $0.01 wide market
    mid_noise: float = 0.03  # random deviation from fair mid (drives cross-market mispricing)
    depth: int = 200  # top-of-book size for each side


def synth_market_from_fair(
    fair_yes: float,
    *,
    params: MicrostructureParams,
    rng: random.Random,
) -> TopOfBook:
    # Add noise and clamp away from 0/1 so the spread fits.
    mid = fair_yes + rng.uniform(-params.mid_noise, params.mid_noise)
    mid = max(0.001 + params.spread / 2.0, min(0.999 - params.spread / 2.0, mid))

    half = params.spread / 2.0
    yes_bid = mid - half
    yes_ask = mid + half

    # Derive NO prices from YES mid; apply same spread.
    no_mid = 1.0 - mid
    no_bid = no_mid - half
    no_ask = no_mid + half

    d = max(0, int(params.depth))
    return TopOfBook(
        yes_bid=yes_bid,
        yes_bid_size=d,
        yes_ask=yes_ask,
        yes_ask_size=d,
        no_bid=no_bid,
        no_bid_size=d,
        no_ask=no_ask,
        no_ask_size=d,
    )

