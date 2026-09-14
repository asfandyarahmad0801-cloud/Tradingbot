from __future__ import annotations

import pytest

from tradingbot.config import UniverseConfig
from tradingbot.universe.discovery import UniverseDiscovery
from tests.conftest import make_range_candles, make_spec


class FakeExchangeClient:
    """Duck-typed stand-in for ExchangeClient -- no network access, so
    universe-filter logic can be tested deterministically."""

    def __init__(self, specs, books, candles):
        self._specs = specs
        self._books = books
        self._candles = candles

    async def fetch_contract_specs(self):
        return self._specs

    async def fetch_order_book(self, symbol, depth=50):
        return self._books[symbol]

    async def fetch_ohlcv(self, symbol, timeframe, limit=200, since=None):
        return self._candles[symbol][-limit:]


def _book(symbol, mid, spread_bps, depth_usd):
    from tradingbot.data.models import OrderBookLevel, OrderBookSnapshot

    # Single level right at the touch, sized so depth_within_bps(..., 10)
    # returns exactly `depth_usd` regardless of asset price -- avoids
    # coupling the fixture to the depth-window threshold used by the code
    # under test.
    half = mid * spread_bps / 10_000 / 2
    qty = depth_usd / mid
    bids = (OrderBookLevel(mid - half, qty),)
    asks = (OrderBookLevel(mid + half, qty),)
    return OrderBookSnapshot(symbol=symbol, exchange_ts_ms=0, local_ts_ms=0, bids=bids, asks=asks)


@pytest.mark.asyncio
async def test_liquid_symbol_is_eligible():
    symbol = "GOOD/USDT:USDT"
    spec = make_spec(symbol)
    candles = make_range_candles(symbol, n=120, mid_price=100.0)
    for c in candles:
        object.__setattr__(c, "quote_volume", 200_000.0)  # ensure ample volume
    book = _book(symbol, 100.0, spread_bps=2.0, depth_usd=200_000.0)
    client = FakeExchangeClient([spec], {symbol: book}, {symbol: candles})

    discovery = UniverseDiscovery(client, UniverseConfig(min_quote_volume_24h_usd=1_000_000, max_spread_bps=8, min_orderbook_depth_usd_within_10bps=50_000, min_contract_age_days=0, max_price_staleness_seconds=10**12))
    entries = await discovery.scan()
    assert len(entries) == 1
    assert entries[0].eligible, entries[0].rejection_reasons


@pytest.mark.asyncio
async def test_wide_spread_symbol_is_rejected():
    symbol = "WIDE/USDT:USDT"
    spec = make_spec(symbol)
    candles = make_range_candles(symbol, n=120, mid_price=100.0)
    for c in candles:
        object.__setattr__(c, "quote_volume", 200_000.0)
    book = _book(symbol, 100.0, spread_bps=50.0, depth_usd=200_000.0)  # way beyond max_spread_bps
    client = FakeExchangeClient([spec], {symbol: book}, {symbol: candles})

    discovery = UniverseDiscovery(client, UniverseConfig(max_spread_bps=8))
    entries = await discovery.scan()
    assert not entries[0].eligible
    assert any("spread_too_wide" in r for r in entries[0].rejection_reasons)


@pytest.mark.asyncio
async def test_thin_depth_symbol_is_rejected():
    symbol = "THIN/USDT:USDT"
    spec = make_spec(symbol)
    candles = make_range_candles(symbol, n=120, mid_price=100.0)
    for c in candles:
        object.__setattr__(c, "quote_volume", 200_000.0)
    book = _book(symbol, 100.0, spread_bps=2.0, depth_usd=1_000.0)  # thin book
    client = FakeExchangeClient([spec], {symbol: book}, {symbol: candles})

    discovery = UniverseDiscovery(client, UniverseConfig(min_orderbook_depth_usd_within_10bps=50_000))
    entries = await discovery.scan()
    assert not entries[0].eligible
    assert any("insufficient_depth" in r for r in entries[0].rejection_reasons)


@pytest.mark.asyncio
async def test_coin_margined_excluded_when_configured():
    symbol = "INV/USD:BTC"
    spec = make_spec(symbol)
    object.__setattr__(spec, "is_coin_margined", True)
    object.__setattr__(spec, "quote", "USD")
    candles = make_range_candles(symbol, n=120, mid_price=100.0)
    book = _book(symbol, 100.0, spread_bps=2.0, depth_usd=200_000.0)
    client = FakeExchangeClient([spec], {symbol: book}, {symbol: candles})

    discovery = UniverseDiscovery(client, UniverseConfig(exclude_coin_margined=True, quote_currencies=["USDT"]))
    entries = await discovery.scan()
    assert not entries[0].eligible
    assert any("coin_margined_excluded" in r for r in entries[0].rejection_reasons)


@pytest.mark.asyncio
async def test_small_cap_coin_is_not_rejected_just_for_being_small_cap():
    """Spec section 3: a coin must not be excluded solely for being
    small-cap -- only for failing objective liquidity/execution checks."""
    symbol = "SMALLCAP/USDT:USDT"
    spec = make_spec(symbol)
    candles = make_range_candles(symbol, n=120, mid_price=0.5)
    for c in candles:
        object.__setattr__(c, "quote_volume", 60_000.0)  # modest but sufficient volume
    book = _book(symbol, 0.5, spread_bps=6.0, depth_usd=60_000.0)
    client = FakeExchangeClient([spec], {symbol: book}, {symbol: candles})

    discovery = UniverseDiscovery(
        client,
        UniverseConfig(min_quote_volume_24h_usd=5_000_000 * 0.001, max_spread_bps=8, min_orderbook_depth_usd_within_10bps=50_000, min_contract_age_days=0, max_price_staleness_seconds=10**12),
    )
    entries = await discovery.scan()
    assert entries[0].eligible, entries[0].rejection_reasons
