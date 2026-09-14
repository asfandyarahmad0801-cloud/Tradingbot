from __future__ import annotations

from tradingbot.data.models import Trade
from tradingbot.features import indicators, market_structure, orderflow, volatility
from tests.conftest import make_range_candles, make_trending_candles


def test_atr_positive_for_normal_series():
    candles = make_trending_candles(n=60)
    value = volatility.atr(candles, period=14)
    assert value is not None and value > 0


def test_atr_none_when_insufficient_history():
    candles = make_trending_candles(n=5)
    assert volatility.atr(candles, period=14) is None


def test_realized_volatility_higher_for_noisier_series():
    calm = make_trending_candles(n=100, noise_amp=0.001, seed=1)
    noisy = make_trending_candles(n=100, noise_amp=0.5, seed=1)
    v_calm = volatility.realized_volatility(calm)
    v_noisy = volatility.realized_volatility(noisy)
    assert v_noisy > v_calm


def test_rsi_bounded_0_100():
    candles = make_trending_candles(n=60)
    r = indicators.rsi(candles)
    assert r is not None
    assert 0.0 <= r <= 100.0


def test_uptrend_has_high_rsi_downtrend_has_low_rsi():
    up = make_trending_candles(n=60, drift_per_bar=0.5, noise_amp=0.01)
    down = make_trending_candles(n=60, drift_per_bar=-0.5, noise_amp=0.01)
    assert indicators.rsi(up) > 60
    assert indicators.rsi(down) < 40


def test_vwap_within_price_range():
    candles = make_range_candles(n=60)
    v = market_structure.vwap(candles)
    lows = min(c.low for c in candles)
    highs = max(c.high for c in candles)
    assert v is not None
    assert lows <= v <= highs


def test_detect_breakout_up():
    candles = make_range_candles(n=40, amplitude=1.0)
    # Append a bar that closes clearly above the recent range.
    last = candles[-1]
    breakout_bar = last.__class__(
        symbol=last.symbol, timeframe=last.timeframe, exchange_ts_ms=last.exchange_ts_ms + 60_000,
        local_ts_ms=last.local_ts_ms + 60_000, open=last.close, high=last.close + 10, low=last.close,
        close=last.close + 9, volume=1000, quote_volume=1000 * (last.close + 9),
    )
    result = market_structure.detect_breakout(candles + [breakout_bar], lookback=20)
    assert result is not None
    assert result.direction == "up"


def _zigzag_uptrend_candles(n_legs: int = 5) -> list:
    """Explicit higher-highs/higher-lows zigzag so fractal swing detection
    (window +/-2 bars) has clear, well-separated swing points -- each leg is
    long enough (3 bars up, 3 bars down) that consecutive extrema don't fall
    inside each other's detection window (a monotonic drift + small noise
    series often produces too few/no local extrema for the fractal
    definition to detect any swings at all)."""
    from tradingbot.data.models import Candle

    candles = []
    price = 100.0
    ts = 1_700_000_000_000
    for _leg in range(n_legs):
        for _ in range(3):
            price += 5.0
            candles.append(Candle("TEST/USDT:USDT", "1m", ts, ts, price, price + 0.3, price - 0.3, price, 100, 100 * price))
            ts += 60_000
        for _ in range(3):
            price -= 2.0
            candles.append(Candle("TEST/USDT:USDT", "1m", ts, ts, price, price + 0.3, price - 0.3, price, 100, 100 * price))
            ts += 60_000
    return candles


def test_classify_structure_uptrend_for_zigzag_higher_highs_higher_lows():
    candles = _zigzag_uptrend_candles()
    state = market_structure.classify_structure(candles)
    assert state == market_structure.StructureState.UPTREND


def test_taker_imbalance_all_buys_is_one():
    trades = [Trade(symbol="X", exchange_ts_ms=i, local_ts_ms=i, price=100, qty=1, side="buy") for i in range(5)]
    assert orderflow.taker_imbalance(trades) == 1.0


def test_taker_imbalance_none_when_no_trades():
    assert orderflow.taker_imbalance([]) is None


def test_cumulative_volume_delta_sign():
    buys = [Trade(symbol="X", exchange_ts_ms=i, local_ts_ms=i, price=100, qty=2, side="buy") for i in range(3)]
    sells = [Trade(symbol="X", exchange_ts_ms=i, local_ts_ms=i, price=100, qty=1, side="sell") for i in range(3)]
    cvd = orderflow.cumulative_volume_delta(buys + sells)
    assert cvd > 0


def test_classify_price_volume_state_all_four_combinations():
    assert orderflow.classify_price_volume_state(1, 1) == "price_up_volume_up"
    assert orderflow.classify_price_volume_state(1, -1) == "price_up_volume_down"
    assert orderflow.classify_price_volume_state(-1, 1) == "price_down_volume_up"
    assert orderflow.classify_price_volume_state(-1, -1) == "price_down_volume_down"
