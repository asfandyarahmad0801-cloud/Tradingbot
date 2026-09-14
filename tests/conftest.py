from __future__ import annotations

import math

import pytest

from tradingbot.data.models import Candle, ContractSpec, ContractStatus, MarginMode, PositionMode


def make_spec(symbol: str = "TEST/USDT:USDT", max_leverage: float = 20.0) -> ContractSpec:
    return ContractSpec(
        symbol=symbol, base="TEST", quote="USDT", settle="USDT", exchange_id="binanceusdm",
        status=ContractStatus.TRADING, tick_size=0.0001, lot_size=0.001, min_order_qty=0.001,
        max_order_qty=None, min_notional=5.0, price_precision=4, qty_precision=3,
        max_leverage=max_leverage, funding_interval_hours=8.0, margin_mode=MarginMode.ISOLATED,
        position_mode=PositionMode.ONE_WAY, is_coin_margined=False, maker_fee_bps=2.0, taker_fee_bps=5.0,
    )


def make_trending_candles(
    symbol: str = "TEST/USDT:USDT",
    n: int = 100,
    start_price: float = 100.0,
    drift_per_bar: float = 0.05,
    noise_amp: float = 0.02,
    start_ts_ms: int = 1_700_000_000_000,
    timeframe_ms: int = 60_000,
    seed: int = 7,
) -> list[Candle]:
    import random

    rng = random.Random(seed)
    candles = []
    price = start_price
    for i in range(n):
        open_ = price
        price = max(price + drift_per_bar + rng.uniform(-noise_amp, noise_amp), 0.01)
        close = price
        high = max(open_, close) + abs(rng.uniform(0, noise_amp))
        low = min(open_, close) - abs(rng.uniform(0, noise_amp))
        volume = 1000 + rng.uniform(-50, 50)
        candles.append(
            Candle(
                symbol=symbol, timeframe="1m", exchange_ts_ms=start_ts_ms + i * timeframe_ms,
                local_ts_ms=start_ts_ms + i * timeframe_ms, open=open_, high=high, low=low, close=close,
                volume=volume, quote_volume=volume * close,
            )
        )
    return candles


def make_range_candles(
    symbol: str = "TEST/USDT:USDT",
    n: int = 100,
    mid_price: float = 100.0,
    amplitude: float = 1.0,
    start_ts_ms: int = 1_700_000_000_000,
    timeframe_ms: int = 60_000,
) -> list[Candle]:
    candles = []
    for i in range(n):
        price = mid_price + amplitude * math.sin(i / 5.0)
        prev_price = mid_price + amplitude * math.sin((i - 1) / 5.0) if i > 0 else price
        high = max(price, prev_price) + 0.05
        low = min(price, prev_price) - 0.05
        candles.append(
            Candle(
                symbol=symbol, timeframe="1m", exchange_ts_ms=start_ts_ms + i * timeframe_ms,
                local_ts_ms=start_ts_ms + i * timeframe_ms, open=prev_price, high=high, low=low, close=price,
                volume=500.0, quote_volume=500.0 * price,
            )
        )
    return candles


@pytest.fixture
def spec() -> ContractSpec:
    return make_spec()
