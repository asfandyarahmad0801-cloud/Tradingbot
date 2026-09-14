"""Paper-trading broker (spec sections 42-43).

Simulates fees, slippage, spread, latency, partial fills, and order
rejection so paper results are a meaningful rehearsal of live execution
rather than a frictionless fantasy. Reads real market data (the live order
book) but never sends real orders anywhere.
"""
from __future__ import annotations

import random
import time
import uuid
from dataclasses import dataclass, field

from tradingbot.data.exchange_client import ExchangeClient
from tradingbot.data.models import ContractSpec, Side
from tradingbot.execution.broker_base import Broker, OrderRequest, OrderResult, OrderStatus, OrderType


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass(slots=True)
class PaperBrokerConfig:
    starting_balance: float = 10_000.0
    simulated_latency_ms_range: tuple[int, int] = (50, 250)
    market_order_slippage_bps: float = 3.0
    limit_fill_probability: float = 0.9      # probability a passive limit order fills at all
    rejection_probability: float = 0.01
    partial_fill_probability: float = 0.05
    min_partial_fill_fraction: float = 0.3


@dataclass(slots=True)
class _PaperPosition:
    symbol: str
    side: Side
    qty: float
    entry_price: float
    leverage: float


@dataclass(slots=True)
class _PendingTrigger:
    order_id: str
    request: OrderRequest
    submitted_ts_ms: int


class PaperBroker(Broker):
    """`market_data_client` supplies real-time prices for realistic fills;
    no credentials on it are ever used to place orders.

    STOP_MARKET / TAKE_PROFIT_MARKET reduce-only orders are held as resting
    trigger orders (`self.pending_triggers`) rather than filled immediately
    on submission -- the caller must periodically await
    `check_pending_triggers()` (the scanner's position-monitor loop does
    this) so protective orders only execute once price actually reaches the
    trigger, matching how a real exchange's conditional orders behave."""

    def __init__(self, market_data_client: ExchangeClient, specs: dict[str, ContractSpec], config: PaperBrokerConfig | None = None) -> None:
        self.market_data_client = market_data_client
        self.specs = specs
        self.config = config or PaperBrokerConfig()
        self.balance = self.config.starting_balance
        self.positions: dict[str, _PaperPosition] = {}
        self.pending_triggers: dict[str, _PendingTrigger] = {}
        self._rng = random.Random(42)

    async def place_order(self, request: OrderRequest) -> OrderResult:
        submitted_ts = _now_ms()
        latency = self._rng.randint(*self.config.simulated_latency_ms_range)
        ack_ts = submitted_ts + latency

        if self._rng.random() < self.config.rejection_probability:
            return OrderResult(
                order_id=str(uuid.uuid4()), status=OrderStatus.REJECTED, requested_qty=request.qty,
                filled_qty=0.0, avg_fill_price=None, fees_paid_quote=0.0,
                submitted_ts_ms=submitted_ts, ack_ts_ms=ack_ts, fill_ts_ms=None,
                reasons=("simulated_exchange_rejection",),
            )

        if request.order_type in (OrderType.STOP_MARKET, OrderType.TAKE_PROFIT_MARKET) and request.reduce_only:
            order_id = str(uuid.uuid4())
            self.pending_triggers[order_id] = _PendingTrigger(order_id, request, submitted_ts)
            return OrderResult(
                order_id=order_id, status=OrderStatus.NEW, requested_qty=request.qty, filled_qty=0.0,
                avg_fill_price=None, fees_paid_quote=0.0, submitted_ts_ms=submitted_ts, ack_ts_ms=ack_ts,
                fill_ts_ms=None, reasons=("resting_trigger_order_armed",),
            )

        book = await self.market_data_client.fetch_order_book(request.symbol, depth=10)
        spec = self.specs.get(request.symbol)
        maker_fee_bps = spec.maker_fee_bps if spec else 2.0
        taker_fee_bps = spec.taker_fee_bps if spec else 5.0

        is_market = request.order_type in (OrderType.MARKET, OrderType.STOP_MARKET, OrderType.TAKE_PROFIT_MARKET)
        reference_price = book.best_ask if request.side == Side.LONG else book.best_bid
        if reference_price is None:
            return OrderResult(
                str(uuid.uuid4()), OrderStatus.REJECTED, request.qty, 0.0, None, 0.0,
                submitted_ts, ack_ts, None, ("no_orderbook_liquidity",),
            )

        if is_market:
            slip = reference_price * self.config.market_order_slippage_bps / 10_000
            fill_price = reference_price + slip if request.side == Side.LONG else reference_price - slip
            fee_bps = taker_fee_bps
            filled_qty = request.qty
        else:
            if self._rng.random() > self.config.limit_fill_probability:
                return OrderResult(
                    str(uuid.uuid4()), OrderStatus.NEW, request.qty, 0.0, None, 0.0,
                    submitted_ts, ack_ts, None, ("limit_order_not_yet_filled",),
                )
            fill_price = request.price if request.price is not None else reference_price
            fee_bps = maker_fee_bps
            filled_qty = request.qty

        status = OrderStatus.FILLED
        if self._rng.random() < self.config.partial_fill_probability:
            fraction = self._rng.uniform(self.config.min_partial_fill_fraction, 0.99)
            filled_qty = request.qty * fraction
            status = OrderStatus.PARTIALLY_FILLED

        notional = filled_qty * fill_price
        fees_paid = notional * fee_bps / 10_000
        fill_ts = ack_ts + self._rng.randint(0, 100)

        self._apply_fill(request, filled_qty, fill_price)

        return OrderResult(
            order_id=str(uuid.uuid4()), status=status, requested_qty=request.qty, filled_qty=filled_qty,
            avg_fill_price=fill_price, fees_paid_quote=fees_paid,
            submitted_ts_ms=submitted_ts, ack_ts_ms=ack_ts, fill_ts_ms=fill_ts,
        )

    def _apply_fill(self, request: OrderRequest, filled_qty: float, fill_price: float) -> None:
        existing = self.positions.get(request.symbol)
        if request.reduce_only and existing is not None:
            close_qty = min(filled_qty, existing.qty)
            pnl = (
                close_qty * (fill_price - existing.entry_price)
                if existing.side == Side.LONG
                else close_qty * (existing.entry_price - fill_price)
            )
            self.balance += pnl
            existing.qty -= close_qty
            if existing.qty <= 1e-12:
                del self.positions[request.symbol]
            return

        if existing is None:
            self.positions[request.symbol] = _PaperPosition(request.symbol, request.side, filled_qty, fill_price, 1.0)
        else:
            total_qty = existing.qty + filled_qty
            existing.entry_price = (existing.entry_price * existing.qty + fill_price * filled_qty) / total_qty
            existing.qty = total_qty

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        return self.pending_triggers.pop(order_id, None) is not None or True

    async def check_pending_triggers(self) -> list[tuple[str, str, OrderResult]]:
        """Polls current price for every resting stop/take-profit order and
        fills any whose trigger condition is met. Returns (symbol,
        order_type_value, OrderResult) triples for every trigger order
        filled this call, so the caller can log trade closes. Must be
        called periodically by the position-monitor loop for protective
        orders to ever execute."""
        fills: list[tuple[str, str, OrderResult]] = []
        for order_id, pending in list(self.pending_triggers.items()):
            req = pending.request
            try:
                book = await self.market_data_client.fetch_order_book(req.symbol, depth=5)
            except Exception:  # noqa: BLE001 - a transient data failure must not crash the monitor loop
                continue
            last_price = book.mid_price
            if last_price is None:
                continue

            existing = self.positions.get(req.symbol)
            if existing is None:
                del self.pending_triggers[order_id]
                continue

            triggered = False
            if req.order_type == OrderType.STOP_MARKET:
                triggered = last_price <= req.price if existing.side == Side.LONG else last_price >= req.price
            elif req.order_type == OrderType.TAKE_PROFIT_MARKET:
                triggered = last_price >= req.price if existing.side == Side.LONG else last_price <= req.price

            if not triggered:
                continue

            slip = last_price * self.config.market_order_slippage_bps / 10_000
            fill_price = last_price - slip if req.side == Side.LONG else last_price + slip
            fee_bps = self.specs.get(req.symbol).taker_fee_bps if self.specs.get(req.symbol) else 5.0
            notional = req.qty * fill_price
            fees_paid = notional * fee_bps / 10_000
            now = _now_ms()

            self._apply_fill(req, req.qty, fill_price)
            del self.pending_triggers[order_id]

            fills.append((
                req.symbol,
                req.order_type.value,
                OrderResult(
                    order_id=order_id, status=OrderStatus.FILLED, requested_qty=req.qty, filled_qty=req.qty,
                    avg_fill_price=fill_price, fees_paid_quote=fees_paid,
                    submitted_ts_ms=pending.submitted_ts_ms, ack_ts_ms=now, fill_ts_ms=now,
                ),
            ))
        return fills

    async def get_position(self, symbol: str) -> dict | None:
        pos = self.positions.get(symbol)
        if pos is None:
            return None
        return {"symbol": pos.symbol, "side": pos.side.value, "qty": pos.qty, "entry_price": pos.entry_price}

    async def get_balance(self) -> float:
        return self.balance

    async def set_leverage(self, symbol: str, leverage: float) -> None:
        if symbol in self.positions:
            self.positions[symbol].leverage = leverage
