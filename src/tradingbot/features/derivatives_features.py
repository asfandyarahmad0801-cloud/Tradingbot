"""Derivatives (funding / open interest / liquidation) features.

Spec sections 7-8: funding and OI are context/cost signals, never standalone
buy/sell triggers, so this module only produces classifications and cost
estimates -- the setup engine decides whether/how to use them.
"""
from __future__ import annotations

from dataclasses import dataclass

from tradingbot.data.models import FundingRate, Liquidation, OpenInterest


def estimate_funding_cost_bps(
    funding: FundingRate,
    position_open_ts_ms: int,
    expected_close_ts_ms: int,
) -> float:
    """Estimated funding cost in bps of notional over the expected holding
    window. Charges a funding payment ONLY if `expected_close_ts_ms` is at or
    after `funding.next_funding_ts_ms` -- a scalp expected to close before
    the next funding timestamp must not be charged a full interval (spec
    section 7)."""
    if expected_close_ts_ms < funding.next_funding_ts_ms:
        return 0.0
    interval_ms = funding.interval_hours * 3600 * 1000
    if interval_ms <= 0:
        return 0.0
    elapsed_past_funding = expected_close_ts_ms - funding.next_funding_ts_ms
    payments = 1 + int(elapsed_past_funding // interval_ms)
    return abs(funding.rate) * 10_000 * payments


def is_funding_extreme(rate: float, history: list[float], percentile: float = 90.0) -> bool:
    if not history:
        return abs(rate) > 0.001  # > 1bp per interval fallback threshold
    import numpy as np

    threshold = float(np.percentile(np.abs(history), percentile))
    return abs(rate) >= threshold


@dataclass(frozen=True, slots=True)
class OiPriceState:
    label: str
    interpretation: str


def classify_oi_price(price_change_pct: float, oi_change_pct: float, threshold: float = 0.05) -> OiPriceState:
    price_up = price_change_pct > threshold
    price_down = price_change_pct < -threshold
    oi_up = oi_change_pct > threshold
    oi_down = oi_change_pct < -threshold

    if price_up and oi_up:
        return OiPriceState("price_up_oi_up", "new money entering longs; trend-confirming but can crowd into a squeeze")
    if price_up and oi_down:
        return OiPriceState("price_up_oi_down", "short covering, not fresh demand; move may lack follow-through")
    if price_down and oi_up:
        return OiPriceState("price_down_oi_up", "new shorts entering; trend-confirming but can crowd into a squeeze")
    if price_down and oi_down:
        return OiPriceState("price_down_oi_down", "long liquidation/unwind, not fresh selling; move may exhaust")
    return OiPriceState("neutral", "no clear directional conviction from OI change")


def liquidation_pressure(
    liquidations: list[Liquidation],
    avg_volume_notional: float,
    market_depth_usd: float,
) -> dict[str, float]:
    long_liq = sum(l.notional for l in liquidations if l.side == "long")
    short_liq = sum(l.notional for l in liquidations if l.side == "short")
    total = long_liq + short_liq
    return {
        "long_liquidations_usd": long_liq,
        "short_liquidations_usd": short_liq,
        "net_liquidation_bias": (short_liq - long_liq) / total if total > 0 else 0.0,
        "liquidations_to_volume_ratio": total / avg_volume_notional if avg_volume_notional > 0 else 0.0,
        "liquidations_to_depth_ratio": total / market_depth_usd if market_depth_usd > 0 else 0.0,
    }


def classify_liquidation_event(
    pressure: dict[str, float],
    price_change_pct_since_start: float,
    volume_ratio_threshold: float = 3.0,
) -> str:
    """Rough heuristic classification per spec section 8: is this
    exhaustion, continuation risk, or a liquidity vacuum? This is a starting
    heuristic that MUST be validated against historical liquidation/price
    outcomes before being trusted (see docs/RESEARCH.md)."""
    ratio = pressure["liquidations_to_volume_ratio"]
    bias = pressure["net_liquidation_bias"]
    if ratio < 0.5:
        return "insignificant"
    if ratio >= volume_ratio_threshold:
        if abs(price_change_pct_since_start) > 1.0:
            return "possible_exhaustion_reversal"
        return "liquidity_vacuum_high_slippage_risk"
    if bias > 0.3 and price_change_pct_since_start < 0:
        return "short_liquidation_continuation_risk_up"
    if bias < -0.3 and price_change_pct_since_start > 0:
        return "long_liquidation_continuation_risk_down"
    return "moderate_no_strong_signal"
