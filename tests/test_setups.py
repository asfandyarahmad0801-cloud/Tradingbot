from __future__ import annotations

from tradingbot.data.models import OrderBookLevel, OrderBookSnapshot, Side, Trade
from tradingbot.features.pump_dump import compute_abnormal_move_score
from tradingbot.regime.classifier import classify_regime
from tradingbot.setups.base import MarketSnapshot
from tradingbot.setups.breakout import BreakoutSetup
from tradingbot.setups.mean_reversion import MeanReversionSetup
from tradingbot.setups.momentum_continuation import MomentumContinuationSetup
from tests.conftest import make_range_candles, make_spec, make_trending_candles


def _book(last_price: float, spread_bps: float = 4.0) -> OrderBookSnapshot:
    half = last_price * spread_bps / 10_000 / 2
    return OrderBookSnapshot(
        symbol="TEST/USDT:USDT", exchange_ts_ms=0, local_ts_ms=0,
        bids=(OrderBookLevel(last_price - half, 100.0),),
        asks=(OrderBookLevel(last_price + half, 100.0),),
    )


def _snapshot(candles, trades, prior_trades=None) -> MarketSnapshot:
    book = _book(candles[-1].close)
    abnormal = compute_abnormal_move_score(candles, trades, prior_trades or [], book.spread_bps, 4.0, None, None, [])
    regime = classify_regime(candles, depth_usd=1_000_000, min_healthy_depth_usd=10_000, abnormal_move_score=abnormal.score)
    return MarketSnapshot(
        symbol="TEST/USDT:USDT", as_of_ms=candles[-1].exchange_ts_ms, spec=make_spec(),
        candles_entry_tf=candles, candles_confirm_tf=candles, candles_context_tf=candles,
        order_book=book, recent_trades=trades, prior_trades=prior_trades or [],
        funding=None, open_interest_now=None, open_interest_prior=None, recent_liquidations=[],
        regime=regime, btc_regime=None, abnormal_move=abnormal, spread_bps=book.spread_bps,
        depth_usd=min(book.depth_within_bps("bid", 10), book.depth_within_bps("ask", 10)),
    )


def _buy_trades(n: int, price: float) -> list[Trade]:
    return [Trade(symbol="TEST/USDT:USDT", exchange_ts_ms=i, local_ts_ms=i, price=price, qty=10, side="buy") for i in range(n)]


def _sell_trades(n: int, price: float) -> list[Trade]:
    return [Trade(symbol="TEST/USDT:USDT", exchange_ts_ms=i, local_ts_ms=i, price=price, qty=10, side="sell") for i in range(n)]


def test_momentum_continuation_fires_long_in_uptrend_with_buy_pressure():
    candles = make_trending_candles(n=80, drift_per_bar=0.3, noise_amp=0.01)
    trades = _buy_trades(20, candles[-1].close)
    snapshot = _snapshot(candles, trades)
    signal = MomentumContinuationSetup().evaluate(snapshot)
    assert signal is not None
    assert signal.direction == Side.LONG
    assert signal.stop_price < signal.entry_price


def test_momentum_continuation_does_not_fire_against_the_trend():
    candles = make_trending_candles(n=80, drift_per_bar=0.3, noise_amp=0.01)  # uptrend
    trades = _sell_trades(20, candles[-1].close)  # selling pressure against an uptrend
    snapshot = _snapshot(candles, trades)
    signal = MomentumContinuationSetup().evaluate(snapshot)
    assert signal is None


def test_momentum_continuation_no_signal_with_no_trades():
    candles = make_trending_candles(n=80, drift_per_bar=0.3, noise_amp=0.01)
    snapshot = _snapshot(candles, [])
    assert MomentumContinuationSetup().evaluate(snapshot) is None


def test_breakout_requires_volume_confirmation():
    candles = make_range_candles(n=40, amplitude=1.0)
    last = candles[-1]
    breakout_bar = last.__class__(
        symbol=last.symbol, timeframe=last.timeframe, exchange_ts_ms=last.exchange_ts_ms + 60_000,
        local_ts_ms=last.local_ts_ms + 60_000, open=last.close, high=last.close + 10, low=last.close,
        close=last.close + 9, volume=1000, quote_volume=1000 * (last.close + 9),
    )
    full = candles + [breakout_bar]

    # No volume acceleration: recent == prior -> setup should NOT fire.
    flat_trades = _buy_trades(5, full[-1].close)
    snapshot_no_confirm = _snapshot(full, flat_trades, prior_trades=flat_trades)
    assert BreakoutSetup().detect(snapshot_no_confirm) is None

    # Strong volume acceleration -> setup should fire long.
    big_recent = _buy_trades(50, full[-1].close)
    tiny_prior = _buy_trades(2, full[-1].close)
    snapshot_confirm = _snapshot(full, big_recent, prior_trades=tiny_prior)
    signal = BreakoutSetup().detect(snapshot_confirm)
    assert signal is not None
    assert signal.direction == Side.LONG


def test_mean_reversion_only_fires_in_range_regime():
    trending = make_trending_candles(n=80, drift_per_bar=0.3, noise_amp=0.01)
    snapshot = _snapshot(trending, [])
    assert MeanReversionSetup().evaluate(snapshot) is None  # regime is trending, not range
