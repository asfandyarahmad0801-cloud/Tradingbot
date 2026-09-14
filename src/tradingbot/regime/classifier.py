"""Market regime classification (spec section 21).

A regime is expressed as a composite (trend regime x volatility regime x a
set of risk flags) rather than one mutually-exclusive label, because e.g. a
coin can simultaneously be in a weak uptrend, high volatility, AND a
low-liquidity state -- collapsing that into one enum would throw away
information the setup engine needs. `RegimeSnapshot.allows(setup regimes)`
is what each setup's `allowed_trend_regimes` is checked against.

Operates at both market-wide (pass BTC candles) and individual-coin level,
per the spec's requirement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from tradingbot.data.models import Candle
from tradingbot.features.market_structure import StructureState, classify_structure
from tradingbot.features.volatility import realized_volatility, volatility_percentile


class TrendRegime(str, Enum):
    STRONG_BULLISH = "strong_bullish_trend"
    WEAK_BULLISH = "weak_bullish_trend"
    RANGE = "range"
    WEAK_BEARISH = "weak_bearish_trend"
    STRONG_BEARISH = "strong_bearish_trend"


class VolatilityRegime(str, Enum):
    LOW = "low_volatility"
    NORMAL = "normal_volatility"
    HIGH = "high_volatility"


class RiskFlag(str, Enum):
    PANIC_LIQUIDATION = "panic_liquidation_regime"
    EVENT_DRIVEN = "event_driven_regime"
    MANIPULATION_RISK = "manipulation_risk_regime"
    LOW_LIQUIDITY = "low_liquidity_regime"
    CORRELATION_BREAKDOWN = "correlation_breakdown_regime"


@dataclass(frozen=True, slots=True)
class RegimeSnapshot:
    trend: TrendRegime
    volatility: VolatilityRegime
    structure: StructureState
    flags: frozenset[RiskFlag] = field(default_factory=frozenset)

    def allows(self, allowed_trends: set[TrendRegime], blocked_flags: set[RiskFlag] | None = None) -> bool:
        if self.trend not in allowed_trends:
            return False
        if blocked_flags and self.flags & blocked_flags:
            return False
        return True


def classify_trend(candles: list[Candle], fast_period: int = 20, slow_period: int = 50) -> TrendRegime:
    if len(candles) < slow_period + 1:
        return TrendRegime.RANGE
    closes = [c.close for c in candles]
    fast_ma = sum(closes[-fast_period:]) / fast_period
    slow_ma = sum(closes[-slow_period:]) / slow_period
    structure = classify_structure(candles)

    spread_pct = (fast_ma - slow_ma) / slow_ma * 100 if slow_ma else 0.0

    if structure == StructureState.UPTREND and spread_pct > 1.0:
        return TrendRegime.STRONG_BULLISH
    if structure == StructureState.UPTREND or spread_pct > 0.2:
        return TrendRegime.WEAK_BULLISH
    if structure == StructureState.DOWNTREND and spread_pct < -1.0:
        return TrendRegime.STRONG_BEARISH
    if structure == StructureState.DOWNTREND or spread_pct < -0.2:
        return TrendRegime.WEAK_BEARISH
    return TrendRegime.RANGE


def classify_volatility_regime(candles: list[Candle], history_window: int = 200) -> VolatilityRegime:
    if len(candles) < 30:
        return VolatilityRegime.NORMAL
    current_vol = realized_volatility(candles[-30:])
    if current_vol is None:
        return VolatilityRegime.NORMAL
    hist_vols = []
    step = 5
    for end in range(30, len(candles), step):
        v = realized_volatility(candles[max(0, end - 30) : end])
        if v is not None:
            hist_vols.append(v)
    if not hist_vols:
        return VolatilityRegime.NORMAL
    pct = volatility_percentile(current_vol, hist_vols[-history_window:])
    if pct is None:
        return VolatilityRegime.NORMAL
    if pct >= 80:
        return VolatilityRegime.HIGH
    if pct <= 20:
        return VolatilityRegime.LOW
    return VolatilityRegime.NORMAL


def classify_regime(
    candles: list[Candle],
    depth_usd: float,
    min_healthy_depth_usd: float,
    abnormal_move_score: float = 0.0,
    manipulation_score_threshold: float = 70.0,
    liquidation_cascade_active: bool = False,
    macro_event_window_active: bool = False,
    correlation_breakdown_active: bool = False,
) -> RegimeSnapshot:
    trend = classify_trend(candles)
    vol = classify_volatility_regime(candles)
    structure = classify_structure(candles)

    flags: set[RiskFlag] = set()
    if liquidation_cascade_active:
        flags.add(RiskFlag.PANIC_LIQUIDATION)
    if macro_event_window_active:
        flags.add(RiskFlag.EVENT_DRIVEN)
    if abnormal_move_score >= manipulation_score_threshold:
        flags.add(RiskFlag.MANIPULATION_RISK)
    if depth_usd < min_healthy_depth_usd:
        flags.add(RiskFlag.LOW_LIQUIDITY)
    if correlation_breakdown_active:
        flags.add(RiskFlag.CORRELATION_BREAKDOWN)

    return RegimeSnapshot(trend=trend, volatility=vol, structure=structure, flags=frozenset(flags))
