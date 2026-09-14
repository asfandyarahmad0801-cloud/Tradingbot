"""Setup 2: Breakout with volume confirmation.

Mechanism: a close beyond a well-established range, accompanied by genuine
volume/trade-flow acceleration (not just a thin wick), suggests a
liquidity-driven regime shift rather than noise. Volume confirmation is the
key filter that historically separates breakouts that continue from those
that immediately fail (see docs/RESEARCH.md).

Failure conditions: breakout without volume confirmation (very common on
illiquid alts -- one large order can print a new high with no follow
through); breakout directly into a known resistance/liquidity cluster.
"""
from __future__ import annotations

from tradingbot.data.models import Side
from tradingbot.features.market_structure import detect_breakout
from tradingbot.features.orderflow import volume_acceleration
from tradingbot.features.volatility import atr
from tradingbot.regime.classifier import TrendRegime, VolatilityRegime
from tradingbot.setups.base import MarketSnapshot, Setup, Signal, TakeProfitLevel

DEFAULT_TPS = (TakeProfitLevel(1.0, 0.5), TakeProfitLevel(2.5, 0.5))


class BreakoutSetup(Setup):
    name = "breakout_volume_confirmed"
    allowed_trend_regimes = {TrendRegime.RANGE, TrendRegime.WEAK_BULLISH, TrendRegime.WEAK_BEARISH}
    max_holding_seconds = 600
    min_reward_to_risk = 1.5
    min_volume_acceleration = 1.5
    lookback_bars = 20

    def allow_high_abnormal_move(self) -> bool:
        # Breakouts are legitimately accompanied by elevated abnormal-move
        # scores; the setup's own volume/liquidity checks substitute for the
        # generic pump-score hard block.
        return True

    def detect(self, snapshot: MarketSnapshot) -> Signal | None:
        candles = snapshot.candles_entry_tf
        if len(candles) < self.lookback_bars + 5:
            return None

        breakout = detect_breakout(candles, lookback=self.lookback_bars, confirm_close=True)
        if breakout is None:
            return None

        vol_ratio = volume_acceleration(snapshot.recent_trades, snapshot.prior_trades)
        if vol_ratio is None or vol_ratio < self.min_volume_acceleration:
            return None

        # A low-volatility squeeze preceding the breakout meaningfully raises
        # conviction (spec: "volatility expansion after compression").
        squeeze_bonus = 10.0 if snapshot.regime.volatility == VolatilityRegime.LOW else 0.0

        atr_val = atr(candles, period=14)
        if atr_val is None or atr_val <= 0:
            return None

        last_close = candles[-1].close
        reasons = [
            f"breakout_{breakout.direction}_of_{self.lookback_bars}bar_range",
            f"level={breakout.level:.6g}",
            f"volume_acceleration={vol_ratio:.2f}x",
        ]

        if breakout.direction == "up":
            stop = min(breakout.level - atr_val * 0.5, last_close - atr_val * 1.0)
            return Signal(
                symbol=snapshot.symbol,
                setup_name=self.name,
                direction=Side.LONG,
                entry_price=last_close,
                stop_price=stop,
                take_profit_levels=DEFAULT_TPS,
                max_holding_seconds=self.max_holding_seconds,
                confidence=min(55 + vol_ratio * 10 + squeeze_bonus, 95),
                reasons=tuple(reasons),
                invalidation_conditions=("close_back_below_breakout_level",),
                as_of_ms=snapshot.as_of_ms,
            )
        else:
            stop = max(breakout.level + atr_val * 0.5, last_close + atr_val * 1.0)
            return Signal(
                symbol=snapshot.symbol,
                setup_name=self.name,
                direction=Side.SHORT,
                entry_price=last_close,
                stop_price=stop,
                take_profit_levels=DEFAULT_TPS,
                max_holding_seconds=self.max_holding_seconds,
                confidence=min(55 + vol_ratio * 10 + squeeze_bonus, 95),
                reasons=tuple(reasons),
                invalidation_conditions=("close_back_above_breakdown_level",),
                as_of_ms=snapshot.as_of_ms,
            )
