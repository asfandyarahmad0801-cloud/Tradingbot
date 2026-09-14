"""Fallback microstructure synthesis for backtesting when real historical
order-book / tick data is not supplied.

IMPORTANT LIMITATION (documented in docs/LIMITATIONS.md): genuine
order-book and trade-level backtesting requires recorded L2 snapshots and
tick data, which most free/public APIs do not provide historically at
scale. When the caller has such data, pass it directly into the backtester
instead of using this module. Absent it, these functions approximate order
flow and depth from OHLCV so the same setup code can run unmodified in
backtest and live -- results from setups that lean heavily on real order-flow
(momentum continuation, liquidation reversal) are therefore indicative only
and must be treated with more skepticism than setups driven mainly by
candle-level structure (breakout, mean reversion, VWAP).
"""
from __future__ import annotations

from tradingbot.data.models import Candle, OrderBookLevel, OrderBookSnapshot, Trade


def synthesize_order_book(candle: Candle, assumed_spread_bps: float, assumed_depth_usd: float) -> OrderBookSnapshot:
    """`assumed_depth_usd` is meant to represent total resting notional
    within 10bps of mid (that's the window `depth_within_bps(..., 10)` and
    the regime/liquidity checks use). All 5 synthetic levels are therefore
    packed within a few bps of the touch -- comfortably inside that 10bps
    window for any realistic `assumed_spread_bps` -- so the configured
    depth figure is actually the depth callers measure, instead of only a
    fraction of it silently disappearing outside the window."""
    mid = candle.close
    half_spread = mid * assumed_spread_bps / 10_000 / 2
    best_bid = mid - half_spread
    best_ask = mid + half_spread
    depth_qty = (assumed_depth_usd / mid) if mid > 0 else 0.0
    level_step_bps = 1.0  # 1bp between levels -> 5 levels span 4bps beyond the touch
    bids = tuple(OrderBookLevel(price=best_bid * (1 - i * level_step_bps / 10_000), qty=depth_qty / 5) for i in range(5))
    asks = tuple(OrderBookLevel(price=best_ask * (1 + i * level_step_bps / 10_000), qty=depth_qty / 5) for i in range(5))
    return OrderBookSnapshot(
        symbol=candle.symbol,
        exchange_ts_ms=candle.exchange_ts_ms,
        local_ts_ms=candle.local_ts_ms,
        bids=bids,
        asks=asks,
        mark_price=mid,
        index_price=mid,
    )


def synthesize_trades(candle: Candle) -> list[Trade]:
    """Splits one candle into two synthetic taker trades (buy/sell) sized by
    `taker_buy_base_volume` when available, else a split biased by how much
    of the bar's range the body occupied (a strong full-bodied bullish
    candle implies more persistent buy-side pressure than a small-bodied
    one, a doji implies none). This recovers a coarse taker-imbalance signal
    from OHLCV alone; it is NOT a substitute for real trade prints -- see
    docs/LIMITATIONS.md."""
    if candle.volume <= 0:
        return []
    if candle.taker_buy_base_volume is not None:
        buy_vol = candle.taker_buy_base_volume
    else:
        bar_range = candle.high - candle.low
        body_strength = (candle.close - candle.open) / bar_range if bar_range > 0 else 0.0
        body_strength = max(-1.0, min(1.0, body_strength))
        bias = 0.5 + 0.4 * body_strength  # in [0.1, 0.9]
        buy_vol = candle.volume * bias
    sell_vol = max(candle.volume - buy_vol, 0.0)

    trades = []
    if buy_vol > 0:
        trades.append(
            Trade(
                symbol=candle.symbol,
                exchange_ts_ms=candle.exchange_ts_ms,
                local_ts_ms=candle.local_ts_ms,
                price=candle.close,
                qty=buy_vol,
                side="buy",
            )
        )
    if sell_vol > 0:
        trades.append(
            Trade(
                symbol=candle.symbol,
                exchange_ts_ms=candle.exchange_ts_ms,
                local_ts_ms=candle.local_ts_ms,
                price=candle.close,
                qty=sell_vol,
                side="sell",
            )
        )
    return trades


def resample_candles(candles: list[Candle], factor: int, timeframe_label: str) -> list[Candle]:
    """Aggregates `factor` consecutive source candles into one. Only emits a
    resampled candle once `factor` source candles are available (no partial/
    forming bars), which is what prevents this from leaking a
    still-forming higher-timeframe candle into a signal computed on the
    lower timeframe."""
    out: list[Candle] = []
    for start in range(0, len(candles) - factor + 1, factor):
        chunk = candles[start : start + factor]
        out.append(
            Candle(
                symbol=chunk[0].symbol,
                timeframe=timeframe_label,
                exchange_ts_ms=chunk[0].exchange_ts_ms,
                local_ts_ms=chunk[-1].local_ts_ms,
                open=chunk[0].open,
                high=max(c.high for c in chunk),
                low=min(c.low for c in chunk),
                close=chunk[-1].close,
                volume=sum(c.volume for c in chunk),
                quote_volume=sum(c.quote_volume for c in chunk),
            )
        )
    return out
