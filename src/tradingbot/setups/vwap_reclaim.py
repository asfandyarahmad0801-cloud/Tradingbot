"""Setup 5: VWAP reclaim / rejection.

Mechanism: VWAP is a widely-watched intraday fair-value reference for both
discretionary and algorithmic participants; a close reclaiming it from below
(or rejecting it from above) after testing the other side often marks a
short-term shift in who is in control. Because so many participants
reference VWAP, it is one of the less manipulable structure levels (spec
section 10) relative to an arbitrary support/resistance line.

Failure conditions: reclaim happens on very low volume (no real
participation, may re-fail immediately); happens against a strong opposing
higher-timeframe trend.
"""
from __future__ import annotations

from tradingbot.data.models import Side
from tradingbot.features.market_structure import vwap_reclaim
from tradingbot.features.orderflow import taker_imbalance
from tradingbot.features.volatility import atr
from tradingbot.regime.classifier import TrendRegime
from tradingbot.setups.base import MarketSnapshot, Setup, Signal, TakeProfitLevel

DEFAULT_TPS = (TakeProfitLevel(1.0, 0.5), TakeProfitLevel(1.8, 0.5))


class VwapReclaimSetup(Setup):
    name = "vwap_reclaim_or_rejection"
    allowed_trend_regimes = {TrendRegime.RANGE, TrendRegime.WEAK_BULLISH, TrendRegime.WEAK_BEARISH}
    max_holding_seconds = 300
    min_reward_to_risk = 1.3

    def detect(self, snapshot: MarketSnapshot) -> Signal | None:
        candles = snapshot.candles_entry_tf
        if len(candles) < 20:
            return None

        event = vwap_reclaim(candles)
        if event is None:
            return None

        imbalance = taker_imbalance(snapshot.recent_trades)
        atr_val = atr(candles, period=14)
        if atr_val is None or atr_val <= 0:
            return None

        last_close = candles[-1].close
        recent_low = min(c.low for c in candles[-10:])
        recent_high = max(c.high for c in candles[-10:])
        reasons = [f"vwap_event={event}"]
        if imbalance is not None:
            reasons.append(f"taker_imbalance={imbalance:+.2f}")

        if event == "reclaim_above" and (imbalance is None or imbalance > 0):
            stop = min(recent_low, last_close - atr_val)
            return Signal(
                symbol=snapshot.symbol,
                setup_name=self.name,
                direction=Side.LONG,
                entry_price=last_close,
                stop_price=stop,
                take_profit_levels=DEFAULT_TPS,
                max_holding_seconds=self.max_holding_seconds,
                confidence=60.0,
                reasons=tuple(reasons),
                invalidation_conditions=("close_back_below_vwap",),
                as_of_ms=snapshot.as_of_ms,
            )

        if event == "reject_below" and (imbalance is None or imbalance < 0):
            stop = max(recent_high, last_close + atr_val)
            return Signal(
                symbol=snapshot.symbol,
                setup_name=self.name,
                direction=Side.SHORT,
                entry_price=last_close,
                stop_price=stop,
                take_profit_levels=DEFAULT_TPS,
                max_holding_seconds=self.max_holding_seconds,
                confidence=60.0,
                reasons=tuple(reasons),
                invalidation_conditions=("close_back_above_vwap",),
                as_of_ms=snapshot.as_of_ms,
            )
        return None
