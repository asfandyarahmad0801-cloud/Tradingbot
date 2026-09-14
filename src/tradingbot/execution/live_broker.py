"""Live broker (spec sections 31, 41, 43).

Deliberately the most guarded module in the codebase: it can only be
constructed with `confirm_live=True`, which `main.py` sets solely when
`config.mode == "live"` AND the operator has passed the explicit live-mode
CLI confirmation. There is no code path that reaches real order placement
by accident from paper or backtest mode.

API key handling: keys come from `Secrets` (env-only, see config.py) and are
never logged; this module never prints `request` bodies containing them
(ccxt itself keeps them out of order payload logs).
"""
from __future__ import annotations

import time

from tradingbot.data.exchange_client import ExchangeClient
from tradingbot.data.models import Side
from tradingbot.execution.broker_base import Broker, OrderRequest, OrderResult, OrderStatus, OrderType


def _now_ms() -> int:
    return int(time.time() * 1000)


_ORDER_TYPE_MAP = {
    OrderType.LIMIT: "limit",
    OrderType.LIMIT_POST_ONLY: "limit",
    OrderType.MARKET: "market",
    OrderType.STOP_MARKET: "stop_market",
    OrderType.STOP_LIMIT: "stop",
    OrderType.TAKE_PROFIT_MARKET: "take_profit_market",
}


class LiveBroker(Broker):
    def __init__(self, client: ExchangeClient, confirm_live: bool) -> None:
        if not confirm_live:
            raise RuntimeError(
                "LiveBroker requires explicit confirm_live=True. This guard exists so live "
                "order placement can never be reached accidentally from paper/backtest code paths."
            )
        self.client = client

    async def place_order(self, request: OrderRequest) -> OrderResult:
        submitted_ts = _now_ms()
        ccxt_type = _ORDER_TYPE_MAP[request.order_type]
        params: dict = {}
        if request.reduce_only:
            params["reduceOnly"] = True
        if request.order_type == OrderType.LIMIT_POST_ONLY:
            params["postOnly"] = True

        try:
            raw = await self.client.create_order(
                symbol=request.symbol,
                order_type=ccxt_type,
                side="buy" if request.side == Side.LONG else "sell",
                amount=request.qty,
                price=request.price,
                params=params,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as a rejected OrderResult, never swallowed
            ack_ts = _now_ms()
            return OrderResult(
                order_id="", status=OrderStatus.REJECTED, requested_qty=request.qty, filled_qty=0.0,
                avg_fill_price=None, fees_paid_quote=0.0, submitted_ts_ms=submitted_ts, ack_ts_ms=ack_ts,
                fill_ts_ms=None, reasons=(f"exchange_error:{exc!r}",),
            )

        ack_ts = _now_ms()
        filled = float(raw.get("filled") or 0.0)
        status_raw = str(raw.get("status") or "").lower()
        status = {
            "closed": OrderStatus.FILLED, "open": OrderStatus.NEW, "canceled": OrderStatus.CANCELED,
            "rejected": OrderStatus.REJECTED, "expired": OrderStatus.EXPIRED,
        }.get(status_raw, OrderStatus.PARTIALLY_FILLED if 0 < filled < request.qty else OrderStatus.NEW)

        return OrderResult(
            order_id=str(raw.get("id", "")), status=status, requested_qty=request.qty, filled_qty=filled,
            avg_fill_price=float(raw["average"]) if raw.get("average") else None,
            fees_paid_quote=float((raw.get("fee") or {}).get("cost") or 0.0),
            submitted_ts_ms=submitted_ts, ack_ts_ms=ack_ts,
            fill_ts_ms=int(raw["timestamp"]) if filled > 0 and raw.get("timestamp") else None,
        )

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        try:
            await self.client.cancel_order(order_id, symbol)
            return True
        except Exception:  # noqa: BLE001
            return False

    async def get_position(self, symbol: str) -> dict | None:
        positions = await self.client.fetch_positions([symbol])
        for p in positions:
            if float(p.get("contracts") or 0) != 0:
                return p
        return None

    async def get_balance(self) -> float:
        balance = await self.client.fetch_balance()
        usdt = balance.get("USDT", {})
        return float(usdt.get("total") or 0.0)

    async def set_leverage(self, symbol: str, leverage: float) -> None:
        await self.client.set_leverage(leverage, symbol)
