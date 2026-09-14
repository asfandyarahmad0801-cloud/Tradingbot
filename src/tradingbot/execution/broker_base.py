"""Broker abstraction (spec section 31/42).

Paper and live brokers implement the same interface so the rest of the
system (order manager, scanner, dashboard) never branches on mode -- the
only place mode is decided is which concrete Broker gets constructed
(see `main.py`).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

from tradingbot.data.models import Side


class OrderType(str, Enum):
    LIMIT = "limit"
    LIMIT_POST_ONLY = "limit_post_only"
    MARKET = "market"
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"
    TAKE_PROFIT_MARKET = "take_profit_market"


class OrderStatus(str, Enum):
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class OrderRequest:
    symbol: str
    side: Side
    order_type: OrderType
    qty: float
    price: float | None = None
    reduce_only: bool = False
    client_order_id: str | None = None


@dataclass(frozen=True, slots=True)
class OrderResult:
    order_id: str
    status: OrderStatus
    requested_qty: float
    filled_qty: float
    avg_fill_price: float | None
    fees_paid_quote: float
    submitted_ts_ms: int
    ack_ts_ms: int
    fill_ts_ms: int | None
    reasons: tuple[str, ...] = field(default_factory=tuple)


class Broker(ABC):
    @abstractmethod
    async def place_order(self, request: OrderRequest) -> OrderResult: ...

    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> bool: ...

    @abstractmethod
    async def get_position(self, symbol: str) -> dict | None: ...

    @abstractmethod
    async def get_balance(self) -> float: ...

    @abstractmethod
    async def set_leverage(self, symbol: str, leverage: float) -> None: ...
