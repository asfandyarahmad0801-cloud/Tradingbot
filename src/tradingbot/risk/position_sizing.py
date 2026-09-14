"""Risk-based position sizing (spec section 27).

Explicitly NOT "buy $X because confidence = Y%". Size is derived from how
much of the account the operator is willing to lose if the stop is hit,
divided by the stop distance -- then clamped by every hard limit the
exchange and the risk config impose. Leverage only determines how much
margin that notional consumes, never the notional itself.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from tradingbot.data.models import ContractSpec, Side


@dataclass(frozen=True, slots=True)
class PositionSizeResult:
    qty: float
    notional: float
    margin_required: float
    risk_amount: float
    rejected: bool
    reasons: tuple[str, ...] = ()


def _round_down_to_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    return math.floor(value / step) * step


def compute_position_size(
    equity: float,
    risk_pct: float,
    entry_price: float,
    stop_price: float,
    leverage: float,
    spec: ContractSpec,
    max_notional_usd: float,
    slippage_buffer_pct: float = 0.0,
) -> PositionSizeResult:
    reasons: list[str] = []
    stop_distance = abs(entry_price - stop_price)
    if stop_distance <= 0 or entry_price <= 0:
        return PositionSizeResult(0.0, 0.0, 0.0, 0.0, True, ("invalid_entry_or_stop_price",))

    # Widen the effective stop distance slightly to account for expected
    # worst-case slippage on the stop fill, so realized loss doesn't
    # systematically exceed the intended risk budget.
    effective_stop_distance = stop_distance * (1 + slippage_buffer_pct / 100.0)

    risk_amount = equity * risk_pct / 100.0
    qty_raw = risk_amount / effective_stop_distance

    notional_raw = qty_raw * entry_price
    if notional_raw > max_notional_usd:
        qty_raw = max_notional_usd / entry_price
        reasons.append(f"capped_by_max_notional:{max_notional_usd:,.0f}usd")

    qty = _round_down_to_step(qty_raw, spec.lot_size) if spec.lot_size > 0 else qty_raw

    if qty < spec.min_order_qty:
        return PositionSizeResult(0.0, 0.0, 0.0, risk_amount, True, (f"qty_below_min_order_qty:{qty}<{spec.min_order_qty}",))
    if spec.max_order_qty is not None and qty > spec.max_order_qty:
        qty = spec.max_order_qty
        reasons.append("capped_by_exchange_max_order_qty")

    notional = qty * entry_price
    if notional < spec.min_notional:
        return PositionSizeResult(0.0, 0.0, 0.0, risk_amount, True, (f"notional_below_min_notional:{notional:.2f}<{spec.min_notional}",))

    margin_required = notional / leverage if leverage > 0 else notional

    return PositionSizeResult(
        qty=qty,
        notional=notional,
        margin_required=margin_required,
        risk_amount=risk_amount,
        rejected=False,
        reasons=tuple(reasons),
    )


def worst_case_loss_with_slippage(
    qty: float,
    entry_price: float,
    stop_price: float,
    side: Side,
    extra_slippage_bps: float,
) -> float:
    """Worst-case realized loss in quote currency if the stop fills
    `extra_slippage_bps` beyond the intended stop price (spec section 27)."""
    slip = entry_price * extra_slippage_bps / 10_000
    if side == Side.LONG:
        worst_exit = stop_price - slip
        return qty * (entry_price - worst_exit)
    worst_exit = stop_price + slip
    return qty * (worst_exit - entry_price)
