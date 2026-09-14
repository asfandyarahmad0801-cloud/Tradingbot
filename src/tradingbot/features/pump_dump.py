"""Pump/dump abnormal-movement detection (spec sections 12-13).

Produces a 0-100 risk score with itemized reasons. This score is a RISK
INPUT to the setup/expectancy engine, not an automatic trade trigger and not
an automatic veto: spec sections 12-13 are explicit that a valid, liquid,
risk-controlled momentum setup may still be traded on a pump, and a dump may
still be faded with an exhaustion-reversal setup, provided the risk engine
approves size/leverage. Only when the score exceeds
`config.pump_dump.*_score_block_threshold` does the setup engine hard-block
new entries (implemented in `setups/base.py`).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from tradingbot.data.models import Candle, Liquidation, Trade
from tradingbot.features.orderflow import trade_size_stats, volume_acceleration


@dataclass(frozen=True, slots=True)
class AbnormalMoveScore:
    score: float                     # 0-100
    direction: str                    # "up" | "down" | "none"
    reasons: list[str] = field(default_factory=list)


def _price_change_pct(candles: list[Candle], lookback: int) -> float:
    if len(candles) < lookback + 1:
        return 0.0
    start = candles[-(lookback + 1)].close
    if start == 0:
        return 0.0
    return (candles[-1].close - start) / start * 100


def compute_abnormal_move_score(
    candles: list[Candle],
    recent_trades: list[Trade],
    prior_trades: list[Trade],
    spread_bps_now: float | None,
    spread_bps_baseline: float | None,
    oi_change_pct: float | None,
    funding_change_bps: float | None,
    recent_liquidations: list[Liquidation],
    lookback_bars: int = 10,
) -> AbnormalMoveScore:
    reasons: list[str] = []
    score = 0.0

    price_change = _price_change_pct(candles, lookback_bars)
    direction = "up" if price_change > 0 else "down" if price_change < 0 else "none"

    # 1. Price acceleration (0-25)
    accel_points = min(abs(price_change) * 2.5, 25.0)
    if accel_points > 5:
        reasons.append(f"price_moved_{price_change:+.2f}pct_over_{lookback_bars}_bars")
    score += accel_points

    # 2. Volume acceleration (0-25)
    vol_ratio = volume_acceleration(recent_trades, prior_trades)
    if vol_ratio is not None:
        vol_points = min(max(vol_ratio - 1.0, 0.0) * 8.0, 25.0)
        if vol_points > 5:
            reasons.append(f"volume_acceleration_{vol_ratio:.1f}x")
        score += vol_points

    # 3. Spread expansion (0-15) -- liquidity withdrawal is a manipulation tell.
    if spread_bps_now is not None and spread_bps_baseline and spread_bps_baseline > 0:
        expansion = spread_bps_now / spread_bps_baseline
        if expansion > 1.3:
            spread_points = min((expansion - 1.0) * 15.0, 15.0)
            reasons.append(f"spread_expanded_{expansion:.1f}x_baseline")
            score += spread_points

    # 4. Trade-size concentration (0-15) -- a handful of oversized prints driving the move.
    stats = trade_size_stats(recent_trades, window_seconds=max(lookback_bars * 60, 1))
    if stats and stats.trade_count > 0:
        concentration = stats.large_trade_count / stats.trade_count
        if concentration > 0.05:
            conc_points = min(concentration * 60.0, 15.0)
            reasons.append(f"large_trade_concentration_{concentration:.0%}")
            score += conc_points

    # 5. OI expansion without proportional price confirmation, or extreme OI change (0-10)
    if oi_change_pct is not None and abs(oi_change_pct) > 5:
        oi_points = min(abs(oi_change_pct) / 2, 10.0)
        reasons.append(f"oi_change_{oi_change_pct:+.1f}pct")
        score += oi_points

    # 6. Funding dislocation (0-5)
    if funding_change_bps is not None and abs(funding_change_bps) > 5:
        reasons.append(f"funding_shift_{funding_change_bps:+.1f}bps")
        score += min(abs(funding_change_bps) / 2, 5.0)

    # 7. Liquidation clustering in the move direction (0-5)
    if recent_liquidations:
        notional = sum(l.notional for l in recent_liquidations)
        if notional > 0:
            reasons.append(f"liquidation_cluster_{notional:,.0f}usd")
            score += min(notional / 500_000 * 5.0, 5.0)

    return AbnormalMoveScore(score=min(score, 100.0), direction=direction, reasons=reasons)


def classify_move_likely_cause(
    abnormal: AbnormalMoveScore,
    spread_bps_now: float | None,
    depth_usd: float,
    min_healthy_depth_usd: float,
    has_corroborating_news: bool = False,
) -> str:
    """Coarse classification of what an abnormal move probably is. This is a
    heuristic prior for the setup engine, NOT a certainty -- it must be
    combined with the setup's own required confirmations (spec section 12)."""
    if has_corroborating_news:
        return "news_driven"
    if depth_usd < min_healthy_depth_usd and abnormal.score > 60:
        return "low_liquidity_manipulation_risk"
    if abnormal.score >= 80:
        return "extreme_abnormal_activity_unclear_cause"
    if abnormal.score >= 50:
        return "coordinated_speculation_or_squeeze"
    if abnormal.score >= 25:
        return "organic_momentum_or_breakout"
    return "normal_activity"
