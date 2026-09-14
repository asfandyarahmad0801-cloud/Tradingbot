"""Classic technical indicators, kept deliberately as SUPPORTING features.

Spec section 11: these must never be used as standalone signals, and
indicators derived from the same price series (e.g. several moving averages)
must not be double-counted as independent confirmations in the scorer.
"""
from __future__ import annotations

import numpy as np

from tradingbot.data.models import Candle


def _closes(candles: list[Candle]) -> np.ndarray:
    return np.array([c.close for c in candles], dtype=float)


def sma(candles: list[Candle], period: int) -> float | None:
    closes = _closes(candles)
    if len(closes) < period:
        return None
    return float(closes[-period:].mean())


def ema_series(values: np.ndarray, period: int) -> np.ndarray:
    alpha = 2.0 / (period + 1.0)
    out = np.empty_like(values)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def ema(candles: list[Candle], period: int) -> float | None:
    closes = _closes(candles)
    if len(closes) < period:
        return None
    return float(ema_series(closes, period)[-1])


def rsi(candles: list[Candle], period: int = 14) -> float | None:
    closes = _closes(candles)
    if len(closes) < period + 1:
        return None
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = gains[-period:].mean()
    avg_loss = losses[-period:].mean()
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100 - 100 / (1 + rs))


def macd(candles: list[Candle], fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[float, float, float] | None:
    closes = _closes(candles)
    if len(closes) < slow + signal:
        return None
    fast_ema = ema_series(closes, fast)
    slow_ema = ema_series(closes, slow)
    macd_line = fast_ema - slow_ema
    signal_line = ema_series(macd_line, signal)
    hist = macd_line - signal_line
    return float(macd_line[-1]), float(signal_line[-1]), float(hist[-1])


def adx(candles: list[Candle], period: int = 14) -> float | None:
    if len(candles) < period * 2:
        return None
    highs = np.array([c.high for c in candles])
    lows = np.array([c.low for c in candles])
    closes = np.array([c.close for c in candles])

    up_move = highs[1:] - highs[:-1]
    down_move = lows[:-1] - lows[1:]
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = np.maximum.reduce([
        highs[1:] - lows[1:],
        np.abs(highs[1:] - closes[:-1]),
        np.abs(lows[1:] - closes[:-1]),
    ])
    atr = _wilder_smooth(tr, period)
    plus_di = 100 * _wilder_smooth(plus_dm, period) / np.where(atr == 0, np.nan, atr)
    minus_di = 100 * _wilder_smooth(minus_dm, period) / np.where(atr == 0, np.nan, atr)
    dx = 100 * np.abs(plus_di - minus_di) / np.where((plus_di + minus_di) == 0, np.nan, (plus_di + minus_di))
    dx = dx[~np.isnan(dx)]
    if len(dx) < period:
        return None
    return float(dx[-period:].mean())


def _wilder_smooth(values: np.ndarray, period: int) -> np.ndarray:
    out = np.empty_like(values, dtype=float)
    out[:period] = np.nan
    if len(values) < period:
        return out
    out[period - 1] = values[:period].sum()
    for i in range(period, len(values)):
        out[i] = out[i - 1] - (out[i - 1] / period) + values[i]
    return out


def stochastic(candles: list[Candle], period: int = 14) -> float | None:
    if len(candles) < period:
        return None
    window = candles[-period:]
    hi = max(c.high for c in window)
    lo = min(c.low for c in window)
    if hi == lo:
        return 50.0
    return float((window[-1].close - lo) / (hi - lo) * 100)


def obv(candles: list[Candle]) -> float | None:
    if len(candles) < 2:
        return None
    total = 0.0
    for a, b in zip(candles, candles[1:]):
        if b.close > a.close:
            total += b.volume
        elif b.close < a.close:
            total -= b.volume
    return total


def roc(candles: list[Candle], period: int = 10) -> float | None:
    if len(candles) < period + 1:
        return None
    past = candles[-(period + 1)].close
    if past == 0:
        return None
    return (candles[-1].close - past) / past * 100


def choppiness_index(candles: list[Candle], period: int = 14) -> float | None:
    if len(candles) < period + 1:
        return None
    from tradingbot.features.volatility import true_ranges

    window = candles[-(period + 1):]
    trs = true_ranges(window)[1:]
    atr_sum = sum(trs)
    hi = max(c.high for c in window)
    lo = min(c.low for c in window)
    rng = hi - lo
    if rng <= 0 or atr_sum <= 0:
        return None
    import math

    return float(100 * math.log10(atr_sum / rng) / math.log10(period))


def donchian_channels(candles: list[Candle], period: int = 20) -> tuple[float, float] | None:
    if len(candles) < period:
        return None
    window = candles[-period:]
    return max(c.high for c in window), min(c.low for c in window)


def keltner_channels(candles: list[Candle], period: int = 20, atr_period: int = 10, multiplier: float = 2.0) -> tuple[float, float, float] | None:
    from tradingbot.features.volatility import atr as atr_fn

    mid = ema(candles, period)
    band = atr_fn(candles, atr_period)
    if mid is None or band is None:
        return None
    return mid + multiplier * band, mid, mid - multiplier * band
