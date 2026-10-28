"""Thin async wrapper around ccxt for perpetual-futures market data and orders.

Why ccxt: it gives us one unified interface across exchanges for market
discovery, OHLCV, order books and order placement, which is what "scan the
whole eligible perpetual universe" requires without hand-rolling a REST
client per exchange. Its cost is that it is not the lowest-latency option --
see docs/LIMITATIONS.md for where a native SDK / websocket-first pipeline
would eventually be needed for sub-second execution.

This module never decides trading logic. It only fetches data and translates
raw exchange payloads into the dataclasses in `tradingbot.data.models`, and
places orders exactly as instructed by the execution layer.
"""
from __future__ import annotations

import os

import time
from typing import Any

import ccxt.async_support as ccxt_async

from tradingbot.data.models import (
    Candle,
    ContractSpec,
    ContractStatus,
    FundingRate,
    MarginMode,
    OpenInterest,
    OrderBookLevel,
    OrderBookSnapshot,
    PositionMode,
    Trade,
)


def _now_ms() -> int:
    return int(time.time() * 1000)


class ExchangeClient:
    """Wraps one ccxt exchange instance configured for USDT/USDC-margined perpetuals."""

    def __init__(
        self,
        exchange_id: str,
        api_key: str = "",
        api_secret: str = "",
        sandbox: bool = True,
        rate_limit_ms: int = 50,
    ) -> None:
        exchange_cls = getattr(ccxt_async, exchange_id)
        params: dict[str, Any] = {
            "apiKey": api_key or None,
            "secret": api_secret or None,
            "enableRateLimit": True,
            "rateLimit": rate_limit_ms,
            # only perpetual swaps are traded; skip loading spot/option catalogues
            "options": {"defaultType": "swap", "fetchMarkets": {"types": ["swap"]}},
        }
        # Honour HTTP(S)_PROXY and a custom CA bundle when the host requires them
        # (aiohttp ignores proxy env vars unless trust_env is set).
        if os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"):
            params["aiohttp_trust_env"] = True
        ca = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
        if ca:
            params["cafile"] = ca
        self.exchange: ccxt_async.Exchange = exchange_cls(params)
        if sandbox:
            try:
                self.exchange.set_sandbox_mode(True)
            except Exception:
                # Not every exchange/ccxt version supports sandbox mode; the
                # caller must ensure sandbox credentials point at testnet
                # endpoints in that case, and paper mode never routes here.
                pass
        self.exchange_id = exchange_id

    async def close(self) -> None:
        await self.exchange.close()

    async def load_markets(self, reload: bool = False) -> dict[str, Any]:
        return await self.exchange.load_markets(reload)

    async def fetch_contract_specs(self) -> list[ContractSpec]:
        """Discover the full perpetual-swap universe with specs, as currently listed."""
        markets = await self.load_markets(reload=True)
        specs: list[ContractSpec] = []
        for symbol, m in markets.items():
            if not m.get("swap"):
                continue
            is_coin_margined = bool(m.get("inverse"))
            limits = m.get("limits", {}) or {}
            amount_limits = limits.get("amount", {}) or {}
            cost_limits = limits.get("cost", {}) or {}
            precision = m.get("precision", {}) or {}
            info = m.get("info", {}) or {}

            status = ContractStatus.TRADING if m.get("active") else ContractStatus.SUSPENDED
            raw_status = str(info.get("status", "")).upper()
            if raw_status in ("DELISTED", "CLOSE"):
                status = ContractStatus.DELISTED
            elif raw_status in ("PENDING_TRADING", "PRE_TRADE", "SETTLING"):
                status = ContractStatus.PRE_LAUNCH
            elif raw_status == "TRADING":
                status = ContractStatus.TRADING

            tick_size = precision.get("price")
            lot_size = precision.get("amount")
            # ccxt sometimes reports precision as decimal-place counts rather
            # than step sizes depending on exchange; normalize defensively.
            if tick_size and tick_size >= 1:
                tick_size = 10 ** (-tick_size)
            if lot_size and lot_size >= 1:
                lot_size = 10 ** (-lot_size)

            funding_interval_hours = 8.0
            try:
                funding_interval_hours = float(info.get("fundingIntervalHours", 8.0))
            except (TypeError, ValueError):
                pass

            specs.append(
                ContractSpec(
                    symbol=symbol,
                    base=m.get("base", ""),
                    quote=m.get("quote", ""),
                    settle=m.get("settle", m.get("quote", "")),
                    exchange_id=self.exchange_id,
                    status=status,
                    tick_size=float(tick_size or 0.0),
                    lot_size=float(lot_size or 0.0),
                    min_order_qty=float(amount_limits.get("min") or 0.0),
                    max_order_qty=(
                        float(amount_limits["max"]) if amount_limits.get("max") is not None else None
                    ),
                    min_notional=float(cost_limits.get("min") or 0.0),
                    price_precision=m.get("precision", {}).get("price", 8) or 8,
                    qty_precision=m.get("precision", {}).get("amount", 8) or 8,
                    max_leverage=float((m.get("limits", {}).get("leverage", {}) or {}).get("max") or 20.0),
                    funding_interval_hours=funding_interval_hours,
                    margin_mode=MarginMode.CROSS,
                    position_mode=PositionMode.ONE_WAY,
                    is_coin_margined=is_coin_margined,
                    maker_fee_bps=float(m.get("maker", 0.0002)) * 10_000,
                    taker_fee_bps=float(m.get("taker", 0.0005)) * 10_000,
                )
            )
        return specs

    def _contract_size(self, symbol: str) -> float:
        """Exchanges such as OKX quote amounts in contracts; convert to base units
        so depth/volume mean the same thing on every venue."""
        m = (self.exchange.markets or {}).get(symbol) or {}
        return float(m.get("contractSize") or 1.0)

    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 200, since: int | None = None) -> list[Candle]:
        raw = await self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit, since=since)
        local_ts = _now_ms()
        candles = []
        cs = self._contract_size(symbol)
        for ts, o, h, l, c, v in raw:
            v = float(v) * cs
            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    exchange_ts_ms=int(ts),
                    local_ts_ms=local_ts,
                    open=float(o),
                    high=float(h),
                    low=float(l),
                    close=float(c),
                    volume=float(v),
                    quote_volume=float(v) * float(c),
                )
            )
        return candles

    async def fetch_order_book(self, symbol: str, depth: int = 50) -> OrderBookSnapshot:
        raw = await self.exchange.fetch_order_book(symbol, limit=depth)
        local_ts = _now_ms()
        exch_ts = raw.get("timestamp") or local_ts
        cs = self._contract_size(symbol)
        # levels may carry extra fields (OKX: price, qty, liquidated orders, order count)
        bids = tuple(OrderBookLevel(price=float(lv[0]), qty=float(lv[1]) * cs) for lv in raw.get("bids", []))
        asks = tuple(OrderBookLevel(price=float(lv[0]), qty=float(lv[1]) * cs) for lv in raw.get("asks", []))
        return OrderBookSnapshot(
            symbol=symbol,
            exchange_ts_ms=int(exch_ts),
            local_ts_ms=local_ts,
            bids=bids,
            asks=asks,
        )

    async def fetch_trades(self, symbol: str, limit: int = 200, since: int | None = None) -> list[Trade]:
        raw = await self.exchange.fetch_trades(symbol, limit=limit, since=since)
        local_ts = _now_ms()
        trades = []
        cs = self._contract_size(symbol)
        for t in raw:
            trades.append(
                Trade(
                    symbol=symbol,
                    exchange_ts_ms=int(t["timestamp"]),
                    local_ts_ms=local_ts,
                    price=float(t["price"]),
                    qty=float(t["amount"]) * cs,
                    side=t.get("side") or "buy",
                    trade_id=str(t.get("id")) if t.get("id") is not None else None,
                )
            )
        return trades

    async def fetch_funding_rate(self, symbol: str) -> FundingRate | None:
        if not self.exchange.has.get("fetchFundingRate"):
            return None
        raw = await self.exchange.fetch_funding_rate(symbol)
        local_ts = _now_ms()
        return FundingRate(
            symbol=symbol,
            exchange_ts_ms=int(raw.get("timestamp") or local_ts),
            local_ts_ms=local_ts,
            rate=float(raw.get("fundingRate") or 0.0),
            next_funding_ts_ms=int(raw.get("fundingTimestamp") or local_ts),
            interval_hours=8.0,
        )

    async def fetch_open_interest(self, symbol: str) -> OpenInterest | None:
        if not self.exchange.has.get("fetchOpenInterest"):
            return None
        raw = await self.exchange.fetch_open_interest(symbol)
        local_ts = _now_ms()
        oi_contracts = float(raw.get("openInterestAmount") or raw.get("openInterest") or 0.0)
        oi_usd = float(raw.get("openInterestValue") or 0.0)
        return OpenInterest(
            symbol=symbol,
            exchange_ts_ms=int(raw.get("timestamp") or local_ts),
            local_ts_ms=local_ts,
            open_interest_contracts=oi_contracts,
            open_interest_usd=oi_usd,
        )

    async def create_order(self, symbol: str, order_type: str, side: str, amount: float, price: float | None = None, params: dict | None = None) -> dict[str, Any]:
        return await self.exchange.create_order(symbol, order_type, side, amount, price, params or {})

    async def cancel_order(self, order_id: str, symbol: str) -> dict[str, Any]:
        return await self.exchange.cancel_order(order_id, symbol)

    async def fetch_positions(self, symbols: list[str] | None = None) -> list[dict[str, Any]]:
        return await self.exchange.fetch_positions(symbols)

    async def fetch_balance(self) -> dict[str, Any]:
        return await self.exchange.fetch_balance()

    async def set_leverage(self, leverage: float, symbol: str) -> Any:
        return await self.exchange.set_leverage(int(leverage), symbol)
