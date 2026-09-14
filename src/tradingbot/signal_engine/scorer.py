"""Multi-factor signal scoring (spec section 23).

Design choice: essential, setup-specific confirmations already gate whether
`Setup.detect` returns a Signal at all (spec section 24 -- a setup must not
require every slow-moving contextual signal to agree). This scorer produces
a SEPARATE, general market-quality/confirmation score on top of that signal,
combining fast-moving factors we can actually compute from connected data
(liquidity, execution quality, volatility fit, BTC-regime alignment,
abnormal-move risk) with optional slow-moving factors (macro, sentiment,
on-chain, news) that default to a neutral 50 when no provider is configured
-- so their absence never silently drags the score up or down, and never
blocks a trade that the setup itself already validated.

Weights are configuration, not hidden constants, precisely so they can be
tuned and walk-forward validated rather than hand-picked once and frozen
(spec section 23).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from tradingbot.regime.classifier import RegimeSnapshot, RiskFlag, TrendRegime, VolatilityRegime
from tradingbot.setups.base import MarketSnapshot, Signal

NEUTRAL = 50.0


@dataclass(frozen=True, slots=True)
class ScoreWeights:
    setup_confidence: float = 0.30
    liquidity_execution: float = 0.20
    volatility_fit: float = 0.15
    btc_regime_alignment: float = 0.10
    abnormal_move_risk: float = 0.10
    macro: float = 0.05
    sentiment: float = 0.05
    onchain: float = 0.05

    def total(self) -> float:
        return (
            self.setup_confidence + self.liquidity_execution + self.volatility_fit
            + self.btc_regime_alignment + self.abnormal_move_risk + self.macro
            + self.sentiment + self.onchain
        )


@dataclass(frozen=True, slots=True)
class ComponentScores:
    setup_confidence: float
    liquidity_execution: float
    volatility_fit: float
    btc_regime_alignment: float
    abnormal_move_risk: float
    macro: float = NEUTRAL
    sentiment: float = NEUTRAL
    onchain: float = NEUTRAL


@dataclass(frozen=True, slots=True)
class SignalScore:
    components: ComponentScores
    composite_score: float          # 0-100
    reasons: tuple[str, ...] = field(default_factory=tuple)


def _liquidity_execution_score(snapshot: MarketSnapshot, max_spread_bps: float, min_depth_usd: float) -> tuple[float, str]:
    spread = snapshot.spread_bps
    if spread is None:
        return 0.0, "no_spread_data"
    spread_score = max(0.0, 100.0 * (1.0 - spread / max(max_spread_bps, 1e-9)))
    depth_score = min(100.0, 100.0 * snapshot.depth_usd / max(min_depth_usd, 1e-9))
    score = 0.5 * spread_score + 0.5 * depth_score
    return score, f"spread={spread:.2f}bps_depth={snapshot.depth_usd:,.0f}usd"


def _volatility_fit_score(regime: RegimeSnapshot) -> tuple[float, str]:
    # Scalping needs SOME volatility to overcome costs, but not chaos.
    mapping = {VolatilityRegime.LOW: 40.0, VolatilityRegime.NORMAL: 90.0, VolatilityRegime.HIGH: 60.0}
    return mapping[regime.volatility], f"volatility_regime={regime.volatility.value}"


def _btc_alignment_score(signal: Signal, btc_regime: RegimeSnapshot | None) -> tuple[float, str]:
    if btc_regime is None:
        return NEUTRAL, "no_btc_regime_data"
    bullish = {TrendRegime.STRONG_BULLISH, TrendRegime.WEAK_BULLISH}
    bearish = {TrendRegime.STRONG_BEARISH, TrendRegime.WEAK_BEARISH}
    from tradingbot.data.models import Side

    if RiskFlag.PANIC_LIQUIDATION in btc_regime.flags:
        return 20.0, "btc_in_panic_liquidation_regime"
    if signal.direction == Side.LONG and btc_regime.trend in bearish:
        return 30.0, "long_against_bearish_btc_regime"
    if signal.direction == Side.SHORT and btc_regime.trend in bullish:
        return 30.0, "short_against_bullish_btc_regime"
    if signal.direction == Side.LONG and btc_regime.trend in bullish:
        return 85.0, "long_with_bullish_btc_regime"
    if signal.direction == Side.SHORT and btc_regime.trend in bearish:
        return 85.0, "short_with_bearish_btc_regime"
    return 65.0, "btc_regime_neutral"


def _abnormal_move_risk_score(snapshot: MarketSnapshot) -> tuple[float, str]:
    score = max(0.0, 100.0 - snapshot.abnormal_move.score)
    return score, f"abnormal_move_score={snapshot.abnormal_move.score:.0f}"


def score_signal(
    snapshot: MarketSnapshot,
    signal: Signal,
    max_spread_bps: float,
    min_depth_usd: float,
    weights: ScoreWeights | None = None,
    macro_score: float | None = None,
    sentiment_score: float | None = None,
    onchain_score: float | None = None,
) -> SignalScore:
    weights = weights or ScoreWeights()
    reasons: list[str] = []

    liq_score, r1 = _liquidity_execution_score(snapshot, max_spread_bps, min_depth_usd)
    vol_score, r2 = _volatility_fit_score(snapshot.regime)
    btc_score, r3 = _btc_alignment_score(signal, snapshot.btc_regime)
    abnormal_score, r4 = _abnormal_move_risk_score(snapshot)
    reasons.extend([r1, r2, r3, r4])

    components = ComponentScores(
        setup_confidence=signal.confidence,
        liquidity_execution=liq_score,
        volatility_fit=vol_score,
        btc_regime_alignment=btc_score,
        abnormal_move_risk=abnormal_score,
        macro=macro_score if macro_score is not None else NEUTRAL,
        sentiment=sentiment_score if sentiment_score is not None else NEUTRAL,
        onchain=onchain_score if onchain_score is not None else NEUTRAL,
    )

    total_weight = weights.total()
    composite = (
        components.setup_confidence * weights.setup_confidence
        + components.liquidity_execution * weights.liquidity_execution
        + components.volatility_fit * weights.volatility_fit
        + components.btc_regime_alignment * weights.btc_regime_alignment
        + components.abnormal_move_risk * weights.abnormal_move_risk
        + components.macro * weights.macro
        + components.sentiment * weights.sentiment
        + components.onchain * weights.onchain
    ) / total_weight

    return SignalScore(components=components, composite_score=composite, reasons=tuple(reasons))
