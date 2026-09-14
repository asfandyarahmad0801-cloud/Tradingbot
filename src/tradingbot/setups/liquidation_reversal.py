"""Setup 7: Liquidation exhaustion reversal.

Mechanism: a forced-selling (long liquidation) or forced-buying (short
liquidation) cascade can push price beyond where genuine supply/demand
would have taken it, because liquidations are involuntary and
price-insensitive. Once the cascade's notional relative to volume/depth is
large AND price has already moved materially, the marginal liquidation
supply/demand is likely close to exhausted -- classified here via
`classify_liquidation_event`. This does NOT fire on liquidation size alone
(spec section 8 explicitly forbids that): it requires the exhaustion
classification, not just "continuation risk" or "liquidity vacuum".

Failure conditions: cascade is still early/ongoing (continuation risk
misclassified as exhaustion); depth is so thin that even a "small" reversal
cannot be executed without ruinous slippage.
"""
from __future__ import annotations

from tradingbot.data.models import Side
from tradingbot.features.derivatives_features import classify_liquidation_event, liquidation_pressure
from tradingbot.features.volatility import atr
from tradingbot.regime.classifier import TrendRegime
from tradingbot.setups.base import MarketSnapshot, Setup, Signal, TakeProfitLevel

DEFAULT_TPS = (TakeProfitLevel(1.0, 0.5), TakeProfitLevel(2.0, 0.5))


class LiquidationReversalSetup(Setup):
    name = "liquidation_exhaustion_reversal"
    allowed_trend_regimes = {
        TrendRegime.STRONG_BULLISH, TrendRegime.WEAK_BULLISH,
        TrendRegime.RANGE,
        TrendRegime.WEAK_BEARISH, TrendRegime.STRONG_BEARISH,
    }
    max_holding_seconds = 300
    min_reward_to_risk = 1.4
    lookback_bars = 10

    def allow_high_abnormal_move(self) -> bool:
        return True

    def detect(self, snapshot: MarketSnapshot) -> Signal | None:
        candles = snapshot.candles_entry_tf
        if len(candles) < self.lookback_bars + 5 or not snapshot.recent_liquidations:
            return None

        avg_volume_notional = sum(c.quote_volume for c in candles[-self.lookback_bars:]) / self.lookback_bars
        pressure = liquidation_pressure(snapshot.recent_liquidations, avg_volume_notional, snapshot.depth_usd)

        start_price = candles[-self.lookback_bars].close
        last_close = candles[-1].close
        price_change_pct = (last_close - start_price) / start_price * 100 if start_price else 0.0

        classification = classify_liquidation_event(pressure, price_change_pct)
        if classification != "possible_exhaustion_reversal":
            return None

        atr_val = atr(candles, period=14)
        if atr_val is None or atr_val <= 0:
            return None

        recent_extreme_high = max(c.high for c in candles[-self.lookback_bars:])
        recent_extreme_low = min(c.low for c in candles[-self.lookback_bars:])
        reasons = [
            f"liquidation_classification={classification}",
            f"net_liquidation_bias={pressure['net_liquidation_bias']:+.2f}",
            f"price_change_over_window={price_change_pct:+.2f}pct",
        ]

        # Cascade of longs being liquidated (net_liquidation_bias > 0 means
        # short liquidations dominate; < 0 means long liquidations dominate)
        # pushed price down -> fade with a long once exhaustion is detected.
        if price_change_pct < 0 and pressure["net_liquidation_bias"] < -0.2:
            stop = recent_extreme_low - atr_val * 0.5
            return Signal(
                symbol=snapshot.symbol,
                setup_name=self.name,
                direction=Side.LONG,
                entry_price=last_close,
                stop_price=stop,
                take_profit_levels=DEFAULT_TPS,
                max_holding_seconds=self.max_holding_seconds,
                confidence=65.0,
                reasons=tuple(reasons),
                invalidation_conditions=("new_low_with_continued_liquidations",),
                as_of_ms=snapshot.as_of_ms,
            )

        if price_change_pct > 0 and pressure["net_liquidation_bias"] > 0.2:
            stop = recent_extreme_high + atr_val * 0.5
            return Signal(
                symbol=snapshot.symbol,
                setup_name=self.name,
                direction=Side.SHORT,
                entry_price=last_close,
                stop_price=stop,
                take_profit_levels=DEFAULT_TPS,
                max_holding_seconds=self.max_holding_seconds,
                confidence=65.0,
                reasons=tuple(reasons),
                invalidation_conditions=("new_high_with_continued_liquidations",),
                as_of_ms=snapshot.as_of_ms,
            )
        return None
