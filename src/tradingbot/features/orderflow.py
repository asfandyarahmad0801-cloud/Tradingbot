"""Trade-flow (order-flow) features (spec section 6).

Computed over rolling windows of executed trades, never from a single trade
or isolated event -- one print tells you nothing about persistent pressure.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from tradingbot.data.models import Trade


def _is_buy(t: Trade) -> bool:
    return t.side == "buy"


def buy_sell_volumes(trades: list[Trade]) -> tuple[float, float]:
    buy = sum(t.quote_qty for t in trades if _is_buy(t))
    sell = sum(t.quote_qty for t in trades if not _is_buy(t))
    return buy, sell


def cumulative_volume_delta(trades: list[Trade]) -> float:
    buy, sell = buy_sell_volumes(trades)
    return buy - sell


def taker_imbalance(trades: list[Trade]) -> float | None:
    """(buy - sell) / (buy + sell) in [-1, 1]."""
    buy, sell = buy_sell_volumes(trades)
    denom = buy + sell
    if denom == 0:
        return None
    return (buy - sell) / denom


@dataclass(slots=True)
class TradeSizeStats:
    mean_quote: float
    p95_quote: float
    max_quote: float
    large_trade_count: int   # trades > 5x mean
    trade_count: int
    trades_per_second: float


def trade_size_stats(trades: list[Trade], window_seconds: float) -> TradeSizeStats | None:
    if not trades:
        return None
    sizes = np.array([t.quote_qty for t in trades])
    mean = float(sizes.mean())
    large_threshold = mean * 5.0
    return TradeSizeStats(
        mean_quote=mean,
        p95_quote=float(np.percentile(sizes, 95)),
        max_quote=float(sizes.max()),
        large_trade_count=int((sizes > large_threshold).sum()),
        trade_count=len(trades),
        trades_per_second=len(trades) / window_seconds if window_seconds > 0 else 0.0,
    )


def volume_acceleration(recent_trades: list[Trade], prior_trades: list[Trade]) -> float | None:
    """Ratio of recent window notional volume to the prior window of equal
    length. >1 means volume is accelerating. None if prior window is empty."""
    recent_vol = sum(t.quote_qty for t in recent_trades)
    prior_vol = sum(t.quote_qty for t in prior_trades)
    if prior_vol == 0:
        return None
    return recent_vol / prior_vol


def cvd_series(trades: list[Trade], bucket_seconds: float) -> list[tuple[int, float]]:
    """Bucketed CVD time series: list of (bucket_start_ms, cumulative_delta)."""
    if not trades:
        return []
    ordered = sorted(trades, key=lambda t: t.exchange_ts_ms)
    bucket_ms = int(bucket_seconds * 1000)
    start = ordered[0].exchange_ts_ms - (ordered[0].exchange_ts_ms % bucket_ms)
    buckets: dict[int, float] = {}
    for t in ordered:
        b = start + ((t.exchange_ts_ms - start) // bucket_ms) * bucket_ms
        delta = t.quote_qty if _is_buy(t) else -t.quote_qty
        buckets[b] = buckets.get(b, 0.0) + delta
    cumulative = 0.0
    series = []
    for b in sorted(buckets):
        cumulative += buckets[b]
        series.append((b, cumulative))
    return series


def cvd_price_divergence(cvd_series_vals: list[float], price_series: list[float]) -> str | None:
    """Detects simple bullish/bearish CVD-price divergence over the given
    aligned series (same length, chronological). Returns
    'bullish_divergence', 'bearish_divergence', or None."""
    if len(cvd_series_vals) < 2 or len(price_series) < 2:
        return None
    price_trend = price_series[-1] - price_series[0]
    cvd_trend = cvd_series_vals[-1] - cvd_series_vals[0]
    if price_trend < 0 and cvd_trend > 0:
        return "bullish_divergence"   # price falling while net buying pressure rising
    if price_trend > 0 and cvd_trend < 0:
        return "bearish_divergence"   # price rising while net selling pressure rising
    return None


def classify_price_volume_state(price_change: float, volume_change: float) -> str:
    """One of the four price/volume regime combinations (spec section 6)."""
    if price_change >= 0 and volume_change >= 0:
        return "price_up_volume_up"
    if price_change >= 0 and volume_change < 0:
        return "price_up_volume_down"
    if price_change < 0 and volume_change >= 0:
        return "price_down_volume_up"
    return "price_down_volume_down"
