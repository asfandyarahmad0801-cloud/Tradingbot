"""Leverage selection and liquidation-price estimation (spec section 26).

Leverage is treated strictly as a risk amplifier, never an edge generator
(spec section 56): the selection procedure here starts from the stop
distance the setup actually needs and asks "what leverage keeps liquidation
safely beyond that stop", not "what's the maximum leverage available".

Liquidation-price formula: this uses the standard simplified isolated-margin
approximation (ignoring the small effect of trading fees baked into some
exchanges' exact maintenance-margin tables). It is deliberately conservative
by using the maintenance margin rate as a subtracted buffer, and is a
starting estimate only -- the execution layer must always fetch the
exchange's own reported liquidation price after a fill and reconcile
against it (spec section 44), never trust this estimate alone once a
position is live.
"""
from __future__ import annotations

from dataclasses import dataclass

from tradingbot.data.models import ContractSpec, Side


def estimate_liquidation_price(
    entry_price: float,
    side: Side,
    leverage: float,
    maintenance_margin_rate: float = 0.005,
) -> float:
    if leverage <= 0:
        raise ValueError("leverage must be > 0")
    inverse_leverage = 1.0 / leverage
    if side == Side.LONG:
        return entry_price * (1.0 - inverse_leverage + maintenance_margin_rate)
    return entry_price * (1.0 + inverse_leverage - maintenance_margin_rate)


def liquidation_distance_pct(entry_price: float, liquidation_price: float) -> float:
    if entry_price == 0:
        return 0.0
    return abs(entry_price - liquidation_price) / entry_price * 100


@dataclass(frozen=True, slots=True)
class LeverageDecision:
    leverage: float
    liquidation_price: float
    liquidation_distance_multiple_of_stop: float
    rejected: bool
    reasons: tuple[str, ...] = ()


def select_leverage(
    entry_price: float,
    stop_price: float,
    side: Side,
    spec: ContractSpec,
    max_position_leverage_config: float,
    min_liquidation_distance_multiple_of_stop: float,
    maintenance_margin_rate: float = 0.005,
    volatility_multiplier: float = 1.0,
    event_window_multiplier: float = 1.0,
    leverage_step: float = 0.5,
) -> LeverageDecision:
    """Search downward from the allowed maximum leverage for the highest
    leverage that still keeps the liquidation price at least
    `min_liquidation_distance_multiple_of_stop` stop-distances away from
    entry. `volatility_multiplier` / `event_window_multiplier` in (0, 1]
    scale the ceiling down further (spec: volatility- and event-based
    leverage reduction)."""
    stop_distance = abs(entry_price - stop_price)
    if stop_distance <= 0:
        return LeverageDecision(0.0, entry_price, 0.0, True, ("zero_or_negative_stop_distance",))

    max_allowed = min(spec.max_leverage, max_position_leverage_config) * volatility_multiplier * event_window_multiplier
    if max_allowed <= 0:
        return LeverageDecision(0.0, entry_price, 0.0, True, ("max_allowed_leverage_is_zero",))

    candidate = max_allowed
    while candidate >= leverage_step:
        liq_price = estimate_liquidation_price(entry_price, side, candidate, maintenance_margin_rate)
        distance = abs(entry_price - liq_price)
        multiple = distance / stop_distance
        if multiple >= min_liquidation_distance_multiple_of_stop:
            return LeverageDecision(
                leverage=round(candidate, 2),
                liquidation_price=liq_price,
                liquidation_distance_multiple_of_stop=multiple,
                rejected=False,
            )
        candidate -= leverage_step

    # Even minimum leverage doesn't satisfy the safety margin -- reject the trade
    # rather than silently accepting an unsafe liquidation distance.
    liq_price = estimate_liquidation_price(entry_price, side, leverage_step, maintenance_margin_rate)
    distance = abs(entry_price - liq_price)
    multiple = distance / stop_distance
    return LeverageDecision(
        leverage=leverage_step,
        liquidation_price=liq_price,
        liquidation_distance_multiple_of_stop=multiple,
        rejected=True,
        reasons=(f"even_min_leverage_{leverage_step}x_gives_liq_distance_{multiple:.2f}x_stop_below_required_{min_liquidation_distance_multiple_of_stop}x",),
    )
