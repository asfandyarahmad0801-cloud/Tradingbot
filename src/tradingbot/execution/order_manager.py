"""Order manager: entry + mandatory protection (spec sections 29, 31, 44).

The rule this module exists to enforce: a position must NEVER be left
without a protective stop working on the exchange. If the stop order fails
to place after entry fills, the position is closed immediately via an
emergency market order rather than left naked -- liquidation must never be
used as a substitute stop-loss (spec section 29).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from tradingbot.data.models import Side
from tradingbot.execution.broker_base import Broker, OrderRequest, OrderResult, OrderStatus, OrderType
from tradingbot.setups.base import Signal

logger = logging.getLogger("tradingbot.execution")


@dataclass(slots=True)
class ManagedEntryResult:
    entry_result: OrderResult
    stop_result: OrderResult | None
    take_profit_results: list[OrderResult]
    protected: bool
    emergency_exit_result: OrderResult | None = None


class OrderManager:
    def __init__(self, broker: Broker, default_order_type: OrderType = OrderType.LIMIT_POST_ONLY) -> None:
        self.broker = broker
        self.default_order_type = default_order_type

    async def enter_with_protection(self, signal: Signal, qty: float) -> ManagedEntryResult:
        entry_request = OrderRequest(
            symbol=signal.symbol,
            side=signal.direction,
            order_type=self.default_order_type,
            qty=qty,
            price=signal.entry_price if self.default_order_type != OrderType.MARKET else None,
        )
        entry_result = await self.broker.place_order(entry_request)

        if entry_result.filled_qty <= 0:
            return ManagedEntryResult(entry_result, None, [], protected=True)

        filled_qty = entry_result.filled_qty
        opposite_side = Side.SHORT if signal.direction == Side.LONG else Side.LONG

        stop_request = OrderRequest(
            symbol=signal.symbol, side=opposite_side, order_type=OrderType.STOP_MARKET,
            qty=filled_qty, price=signal.stop_price, reduce_only=True,
        )
        stop_result = await self.broker.place_order(stop_request)

        stop_placed = stop_result.status in (OrderStatus.NEW, OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED)
        if not stop_placed:
            logger.critical(
                "UNPROTECTED_POSITION_EMERGENCY_EXIT symbol=%s reason=stop_order_failed:%s",
                signal.symbol, stop_result.reasons,
            )
            emergency_request = OrderRequest(
                symbol=signal.symbol, side=opposite_side, order_type=OrderType.MARKET,
                qty=filled_qty, reduce_only=True,
            )
            emergency_result = await self.broker.place_order(emergency_request)
            return ManagedEntryResult(entry_result, stop_result, [], protected=False, emergency_exit_result=emergency_result)

        tp_results = []
        for tp in signal.take_profit_levels:
            tp_qty = filled_qty * tp.fraction
            if tp_qty <= 0:
                continue
            tp_price = (
                signal.entry_price + tp.r_multiple * signal.risk_per_unit
                if signal.direction == Side.LONG
                else signal.entry_price - tp.r_multiple * signal.risk_per_unit
            )
            tp_request = OrderRequest(
                symbol=signal.symbol, side=opposite_side, order_type=OrderType.TAKE_PROFIT_MARKET,
                qty=tp_qty, price=tp_price, reduce_only=True,
            )
            tp_results.append(await self.broker.place_order(tp_request))

        return ManagedEntryResult(entry_result, stop_result, tp_results, protected=True)

    async def emergency_close_all(self, symbol: str, side: Side, qty: float) -> OrderResult:
        opposite_side = Side.SHORT if side == Side.LONG else Side.LONG
        request = OrderRequest(symbol=symbol, side=opposite_side, order_type=OrderType.MARKET, qty=qty, reduce_only=True)
        return await self.broker.place_order(request)
