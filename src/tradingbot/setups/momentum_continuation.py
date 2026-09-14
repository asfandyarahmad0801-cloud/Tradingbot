"""Setup 1: Order-flow momentum continuation.

Mechanism: in a trending market, persistent aggressive one-sided taker flow
(measured over a rolling window, never a single trade) combined with price
holding above/below VWAP suggests the path of least resistance continues
short-term. This is a well-documented microstructure effect (order-flow
imbalance predicts short-horizon returns) but decays fast and is prone to
false signals in choppy/low-liquidity conditions -- hence the trend-regime
and liquidity gates in `Setup.evaluate`.

Failure conditions: imbalance reverses immediately after entry (flow was a
one-off sweep, not persistent pressure); trend regime was misclassified
(range disguised as trend).
"""
from __future__ import annotations

from tradingbot.data.models import Side
from tradingbot.features.market_structure import StructureState, vwap
from tradingbot.features.orderflow import taker_imbalance
from tradingbot.features.volatility import atr
from tradingbot.regime.classifier import TrendRegime
from tradingbot.setups.base import MarketSnapshot, Setup, Signal, TakeProfitLevel

DEFAULT_TPS = (TakeProfitLevel(1.0, 0.5), TakeProfitLevel(2.0, 0.5))


class MomentumContinuationSetup(Setup):
    name = "order_flow_momentum_continuation"
    allowed_trend_regimes = {TrendRegime.STRONG_BULLISH, TrendRegime.WEAK_BULLISH, TrendRegime.STRONG_BEARISH, TrendRegime.WEAK_BEARISH}
    max_holding_seconds = 300
    min_reward_to_risk = 1.3
    imbalance_threshold = 0.25
    atr_stop_multiplier = 1.2

    def detect(self, snapshot: MarketSnapshot) -> Signal | None:
        candles = snapshot.candles_entry_tf
        if len(candles) < 30:
            return None

        imbalance = taker_imbalance(snapshot.recent_trades)
        if imbalance is None:
            return None

        v = vwap(candles[-50:])
        if v is None:
            return None

        last_close = candles[-1].close
        atr_val = atr(candles, period=14)
        if atr_val is None or atr_val <= 0:
            return None

        stop_dist = atr_val * self.atr_stop_multiplier
        is_bullish_trend = snapshot.regime.trend in (TrendRegime.STRONG_BULLISH, TrendRegime.WEAK_BULLISH)
        is_bearish_trend = snapshot.regime.trend in (TrendRegime.STRONG_BEARISH, TrendRegime.WEAK_BEARISH)

        reasons = [
            f"trend_regime={snapshot.regime.trend.value}",
            f"taker_imbalance={imbalance:+.2f}",
            f"price_vs_vwap={'above' if last_close > v else 'below'}",
        ]

        if is_bullish_trend and imbalance >= self.imbalance_threshold and last_close > v:
            return Signal(
                symbol=snapshot.symbol,
                setup_name=self.name,
                direction=Side.LONG,
                entry_price=last_close,
                stop_price=last_close - stop_dist,
                take_profit_levels=DEFAULT_TPS,
                max_holding_seconds=self.max_holding_seconds,
                confidence=min(60 + imbalance * 80, 95),
                reasons=tuple(reasons),
                invalidation_conditions=("taker_imbalance_reverses_negative", "close_back_below_vwap"),
                as_of_ms=snapshot.as_of_ms,
            )

        if is_bearish_trend and imbalance <= -self.imbalance_threshold and last_close < v:
            return Signal(
                symbol=snapshot.symbol,
                setup_name=self.name,
                direction=Side.SHORT,
                entry_price=last_close,
                stop_price=last_close + stop_dist,
                take_profit_levels=DEFAULT_TPS,
                max_holding_seconds=self.max_holding_seconds,
                confidence=min(60 + abs(imbalance) * 80, 95),
                reasons=tuple(reasons),
                invalidation_conditions=("taker_imbalance_reverses_positive", "close_back_above_vwap"),
                as_of_ms=snapshot.as_of_ms,
            )
        return None
