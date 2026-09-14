"""Market-structure features (spec section 10).

Converts chart-pattern concepts into measurable, deterministic variables
(fractal swing points, VWAP, breakout distance) instead of subjective visual
pattern recognition -- the spec explicitly requires this.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from tradingbot.data.models import Candle


@dataclass(frozen=True, slots=True)
class SwingPoint:
    index: int
    price: float
    kind: str  # "high" | "low"


def find_swing_points(candles: list[Candle], left: int = 2, right: int = 2) -> list[SwingPoint]:
    """Fractal swing highs/lows: a bar is a swing high if its high is the
    max within [i-left, i+right], analogously for lows. Only bars with
    `right` bars already closed after them qualify, so this never uses
    information unavailable at the time the swing is confirmed."""
    points: list[SwingPoint] = []
    n = len(candles)
    for i in range(left, n - right):
        window = candles[i - left : i + right + 1]
        if candles[i].high == max(c.high for c in window):
            points.append(SwingPoint(index=i, price=candles[i].high, kind="high"))
        if candles[i].low == min(c.low for c in window):
            points.append(SwingPoint(index=i, price=candles[i].low, kind="low"))
    return points


class StructureState(str, Enum):
    UPTREND = "uptrend_hh_hl"
    DOWNTREND = "downtrend_lh_ll"
    RANGE = "range"
    INDETERMINATE = "indeterminate"


def classify_structure(candles: list[Candle], left: int = 2, right: int = 2) -> StructureState:
    points = find_swing_points(candles, left, right)
    highs = [p for p in points if p.kind == "high"]
    lows = [p for p in points if p.kind == "low"]
    if len(highs) < 2 or len(lows) < 2:
        return StructureState.INDETERMINATE

    higher_highs = highs[-1].price > highs[-2].price
    higher_lows = lows[-1].price > lows[-2].price
    lower_highs = highs[-1].price < highs[-2].price
    lower_lows = lows[-1].price < lows[-2].price

    if higher_highs and higher_lows:
        return StructureState.UPTREND
    if lower_highs and lower_lows:
        return StructureState.DOWNTREND
    return StructureState.RANGE


def vwap(candles: list[Candle]) -> float | None:
    total_pv = sum(((c.high + c.low + c.close) / 3.0) * c.volume for c in candles)
    total_v = sum(c.volume for c in candles)
    if total_v == 0:
        return None
    return total_pv / total_v


def recent_high_low(candles: list[Candle], lookback: int) -> tuple[float, float] | None:
    if len(candles) < lookback:
        return None
    window = candles[-lookback:]
    return max(c.high for c in window), min(c.low for c in window)


@dataclass(frozen=True, slots=True)
class BreakoutSignal:
    direction: str          # "up" | "down"
    level: float
    distance_pct: float


def detect_breakout(candles: list[Candle], lookback: int = 20, confirm_close: bool = True) -> BreakoutSignal | None:
    """Breakout of the prior `lookback`-bar range, confirmed by close (not
    wick) to reduce false positives from a single spike."""
    if len(candles) < lookback + 1:
        return None
    prior = candles[-(lookback + 1) : -1]
    last = candles[-1]
    hi = max(c.high for c in prior)
    lo = min(c.low for c in prior)
    ref_price = last.close if confirm_close else last.high
    if ref_price > hi:
        return BreakoutSignal(direction="up", level=hi, distance_pct=(ref_price - hi) / hi * 100)
    ref_price_low = last.close if confirm_close else last.low
    if ref_price_low < lo:
        return BreakoutSignal(direction="down", level=lo, distance_pct=(lo - ref_price_low) / lo * 100)
    return None


def detect_failed_breakout(candles: list[Candle], lookback: int = 20, confirm_bars: int = 2) -> str | None:
    """A breakout that reverses back inside the range within `confirm_bars`
    closes -- i.e. a liquidity sweep rather than genuine continuation."""
    if len(candles) < lookback + confirm_bars + 1:
        return None
    range_window = candles[-(lookback + confirm_bars + 1) : -confirm_bars - 1]
    hi = max(c.high for c in range_window)
    lo = min(c.low for c in range_window)
    breakout_bar = candles[-confirm_bars - 1]
    follow_through = candles[-confirm_bars:]

    if breakout_bar.high > hi and all(c.close < hi for c in follow_through):
        return "failed_breakout_up"
    if breakout_bar.low < lo and all(c.close > lo for c in follow_through):
        return "failed_breakout_down"
    return None


def vwap_reclaim(candles: list[Candle]) -> str | None:
    """Detects a close crossing back above/below VWAP after being on the
    other side -- a common scalp entry trigger (spec setup #5)."""
    if len(candles) < 3:
        return None
    v = vwap(candles[:-1])
    if v is None:
        return None
    prev_close = candles[-2].close
    last_close = candles[-1].close
    if prev_close < v <= last_close:
        return "reclaim_above"
    if prev_close > v >= last_close:
        return "reject_below"
    return None
