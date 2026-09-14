from __future__ import annotations

from tradingbot.data.models import OrderBookLevel, OrderBookSnapshot
from tradingbot.data.validation import check_candles, check_orderbook, has_critical
from tests.conftest import make_trending_candles


def test_clean_candles_produce_no_critical_issues():
    candles = make_trending_candles(n=60)
    issues = check_candles("X", candles, timeframe_seconds=60, now_ms=candles[-1].exchange_ts_ms + 1000)
    assert not has_critical(issues)


def test_missing_candles_flagged_as_critical():
    assert has_critical(check_candles("X", [], timeframe_seconds=60))


def test_stale_data_flagged():
    candles = make_trending_candles(n=30)
    far_future = candles[-1].exchange_ts_ms + 1_000_000
    issues = check_candles("X", candles, timeframe_seconds=60, max_staleness_seconds=30, now_ms=far_future)
    assert has_critical(issues)
    assert any(i.check == "stale_data" for i in issues)


def test_gap_detected():
    candles = make_trending_candles(n=30)
    # Remove a candle in the middle to create a gap.
    gapped = candles[:15] + candles[17:]
    issues = check_candles("X", gapped, timeframe_seconds=60, now_ms=gapped[-1].exchange_ts_ms + 1000)
    assert any(i.check == "gap" for i in issues)


def test_duplicate_timestamp_detected():
    candles = make_trending_candles(n=10)
    dup = candles + [candles[-1]]
    issues = check_candles("X", dup, timeframe_seconds=60, now_ms=dup[-1].exchange_ts_ms + 1000)
    assert any(i.check == "duplicate_candle" for i in issues)


def test_crossed_book_detected():
    book = OrderBookSnapshot(
        symbol="X", exchange_ts_ms=0, local_ts_ms=0,
        bids=(OrderBookLevel(price=101.0, qty=1.0),),
        asks=(OrderBookLevel(price=100.0, qty=1.0),),
    )
    issues = check_orderbook("X", book, now_ms=0)
    assert has_critical(issues)
    assert any(i.check == "crossed_book" for i in issues)


def test_empty_book_detected():
    book = OrderBookSnapshot(symbol="X", exchange_ts_ms=0, local_ts_ms=0, bids=(), asks=())
    issues = check_orderbook("X", book, now_ms=0)
    assert has_critical(issues)
