"""Volatility features.

Every stop-loss and leverage decision downstream depends on these -- spec
section 9 explicitly forbids a fixed stop distance across coins. All
functions take `candles` already restricted to what would have been known
at signal time (no-lookahead is the caller's responsibility, enforced in the
backtester by only ever slicing history up to `as_of`).
"""
from __future__ import annotations

import math

import numpy as np

from tradingbot.data.models import Candle


def true_ranges(candles: list[Candle]) -> list[float]:
    trs = []
    prev_close = None
    for c in candles:
        if prev_close is None:
            trs.append(c.high - c.low)
        else:
            trs.append(max(c.high - c.low, abs(c.high - prev_close), abs(c.low - prev_close)))
        prev_close = c.close
    return trs


def atr(candles: list[Candle], period: int = 14) -> float | None:
    trs = true_ranges(candles)
    if len(trs) < period:
        return None
    return float(np.mean(trs[-period:]))


def log_returns(candles: list[Candle]) -> list[float]:
    rets = []
    for a, b in zip(candles, candles[1:]):
        if a.close > 0 and b.close > 0:
            rets.append(math.log(b.close / a.close))
    return rets


def realized_volatility(candles: list[Candle], annualize_periods_per_year: float | None = None) -> float | None:
    """Stdev of log returns over the given candle window. If
    `annualize_periods_per_year` is given, scales to an annualized figure;
    otherwise returns the raw per-bar volatility, which is what should be
    compared against expected scalp move size."""
    rets = log_returns(candles)
    if len(rets) < 2:
        return None
    vol = float(np.std(rets, ddof=1))
    if annualize_periods_per_year:
        vol *= math.sqrt(annualize_periods_per_year)
    return vol


def bollinger_bandwidth(candles: list[Candle], period: int = 20, num_std: float = 2.0) -> float | None:
    if len(candles) < period:
        return None
    closes = np.array([c.close for c in candles[-period:]])
    mean = closes.mean()
    std = closes.std(ddof=1)
    if mean == 0:
        return None
    upper = mean + num_std * std
    lower = mean - num_std * std
    return float((upper - lower) / mean)


def volatility_percentile(current_vol: float, history: list[float]) -> float | None:
    """Percentile rank (0-100) of `current_vol` within `history`."""
    if not history:
        return None
    arr = np.array(history)
    return float((arr < current_vol).mean() * 100.0)


def is_volatility_squeeze(bandwidths: list[float], lookback: int = 50, percentile_threshold: float = 20.0) -> bool:
    if len(bandwidths) < lookback:
        return False
    current = bandwidths[-1]
    hist = bandwidths[-lookback:-1]
    pct = volatility_percentile(current, hist)
    return pct is not None and pct <= percentile_threshold


def stop_distance_from_atr(atr_value: float, multiplier: float = 1.5) -> float:
    return atr_value * multiplier
