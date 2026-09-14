"""Core immutable data models shared across the system.

All timestamps are UTC epoch milliseconds unless noted. Every model that
originates from an exchange records both `exchange_ts_ms` (the timestamp the
exchange attaches to the event) and `local_ts_ms` (when this process received
it), so latency can be measured and no-lookahead can be enforced in
backtests: a signal computed "as of" some time may only see records whose
`exchange_ts_ms` is <= that time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class MarginMode(str, Enum):
    CROSS = "cross"
    ISOLATED = "isolated"


class PositionMode(str, Enum):
    ONE_WAY = "one_way"
    HEDGE = "hedge"


class ContractStatus(str, Enum):
    TRADING = "trading"
    SUSPENDED = "suspended"
    DELISTED = "delisted"
    PRE_LAUNCH = "pre_launch"
    MAINTENANCE = "maintenance"
    UNKNOWN = "unknown"


class Side(str, Enum):
    LONG = "long"
    SHORT = "short"


@dataclass(frozen=True, slots=True)
class ContractSpec:
    """Exchange-reported specification for one perpetual contract.

    This is the ground truth used everywhere else (position sizing,
    execution, risk) for rounding and limits -- never hard-code tick/lot
    sizes per symbol.
    """

    symbol: str                 # unified symbol, e.g. "BTC/USDT:USDT"
    base: str
    quote: str
    settle: str
    exchange_id: str
    status: ContractStatus
    tick_size: float
    lot_size: float
    min_order_qty: float
    max_order_qty: float | None
    min_notional: float
    price_precision: int
    qty_precision: int
    max_leverage: float
    funding_interval_hours: float
    margin_mode: MarginMode
    position_mode: PositionMode
    is_coin_margined: bool
    listed_at_ms: int | None = None
    maker_fee_bps: float = 2.0
    taker_fee_bps: float = 5.0


@dataclass(frozen=True, slots=True)
class Candle:
    symbol: str
    timeframe: str
    exchange_ts_ms: int          # candle open time as reported by exchange
    local_ts_ms: int             # when this process received/closed the candle
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float
    trades_count: int | None = None
    taker_buy_base_volume: float | None = None
    taker_buy_quote_volume: float | None = None
    is_closed: bool = True


@dataclass(frozen=True, slots=True)
class OrderBookLevel:
    price: float
    qty: float


@dataclass(frozen=True, slots=True)
class OrderBookSnapshot:
    symbol: str
    exchange_ts_ms: int
    local_ts_ms: int
    bids: tuple[OrderBookLevel, ...]   # sorted best-first (descending price)
    asks: tuple[OrderBookLevel, ...]   # sorted best-first (ascending price)
    mark_price: float | None = None
    index_price: float | None = None
    sequence: int | None = None

    @property
    def best_bid(self) -> float | None:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> float | None:
        return self.asks[0].price if self.asks else None

    @property
    def mid_price(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2.0

    @property
    def spread_bps(self) -> float | None:
        if self.best_bid is None or self.best_ask is None or self.mid_price in (None, 0):
            return None
        return (self.best_ask - self.best_bid) / self.mid_price * 10_000

    def depth_within_bps(self, side: str, bps: float) -> float:
        """Sum of quote-currency notional resting within `bps` of mid on one side."""
        mid = self.mid_price
        if mid is None:
            return 0.0
        threshold = mid * bps / 10_000
        levels = self.bids if side == "bid" else self.asks
        total = 0.0
        for lvl in levels:
            if abs(lvl.price - mid) > threshold:
                break
            total += lvl.price * lvl.qty
        return total

    def imbalance(self, depth_levels: int = 10) -> float | None:
        """(bid_qty - ask_qty) / (bid_qty + ask_qty) over the top N levels, in [-1, 1]."""
        bid_qty = sum(l.qty for l in self.bids[:depth_levels])
        ask_qty = sum(l.qty for l in self.asks[:depth_levels])
        denom = bid_qty + ask_qty
        if denom == 0:
            return None
        return (bid_qty - ask_qty) / denom


@dataclass(frozen=True, slots=True)
class Trade:
    symbol: str
    exchange_ts_ms: int
    local_ts_ms: int
    price: float
    qty: float
    side: str                     # "buy" (taker bought) or "sell" (taker sold)
    trade_id: str | None = None

    @property
    def quote_qty(self) -> float:
        return self.price * self.qty


@dataclass(frozen=True, slots=True)
class FundingRate:
    symbol: str
    exchange_ts_ms: int
    local_ts_ms: int
    rate: float                    # e.g. 0.0001 == 1 bp per interval
    next_funding_ts_ms: int
    interval_hours: float


@dataclass(frozen=True, slots=True)
class OpenInterest:
    symbol: str
    exchange_ts_ms: int
    local_ts_ms: int
    open_interest_contracts: float
    open_interest_usd: float


@dataclass(frozen=True, slots=True)
class Liquidation:
    symbol: str
    exchange_ts_ms: int
    local_ts_ms: int
    side: str                      # side of the liquidated position: "long" or "short"
    price: float
    qty: float

    @property
    def notional(self) -> float:
        return self.price * self.qty


@dataclass(frozen=True, slots=True)
class NewsEvent:
    published_ts_ms: int
    received_ts_ms: int
    source: str
    headline: str
    category: str
    symbols: tuple[str, ...] = field(default_factory=tuple)
    credibility: float = 0.5       # 0-1, source-quality prior
    sentiment: float = 0.0         # -1..1
    importance: float = 0.0        # 0..1


@dataclass(frozen=True, slots=True)
class MacroEvent:
    scheduled_ts_ms: int
    name: str
    country: str
    importance: str                # "low" | "medium" | "high"
    actual: float | None = None
    forecast: float | None = None
    previous: float | None = None
    released_ts_ms: int | None = None
