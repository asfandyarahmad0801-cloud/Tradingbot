"""Setup 6: Range-bound mean reversion.

Mechanism: inside a measured range (no directional trend regime), price
reaching a statistical extreme (RSI) at the range boundary has historically
tended to revert toward the range midpoint/VWAP, because there is no
sustained directional order flow to extend it. This setup deliberately
requires the RANGE regime -- taking mean-reversion trades inside a trend is
one of the most common ways scalpers get run over (spec section 21).

Failure conditions: the range regime classification lags a genuine breakout
in progress; low-liquidity coins where "the range boundary" is really just
thin order-book noise.
"""
from __future__ import annotations

from tradingbot.data.models import Side
from tradingbot.features.indicators import rsi
from tradingbot.features.market_structure import recent_high_low, vwap
from tradingbot.features.volatility import atr
from tradingbot.regime.classifier import TrendRegime
from tradingbot.setups.base import MarketSnapshot, Setup, Signal, TakeProfitLevel


class MeanReversionSetup(Setup):
    name = "range_mean_reversion"
    allowed_trend_regimes = {TrendRegime.RANGE}
    max_holding_seconds = 600
    min_reward_to_risk = 1.3
    rsi_oversold = 30.0
    rsi_overbought = 70.0
    lookback_bars = 30
    boundary_proximity_pct = 0.3   # must be within this % of range extreme

    def detect(self, snapshot: MarketSnapshot) -> Signal | None:
        candles = snapshot.candles_entry_tf
        if len(candles) < self.lookback_bars + 15:
            return None

        r = rsi(candles, period=14)
        rng = recent_high_low(candles, self.lookback_bars)
        v = vwap(candles[-self.lookback_bars:])
        atr_val = atr(candles, period=14)
        if r is None or rng is None or v is None or atr_val is None or atr_val <= 0:
            return None

        hi, lo = rng
        last_close = candles[-1].close
        near_low = (last_close - lo) / lo * 100 <= self.boundary_proximity_pct if lo else False
        near_high = (hi - last_close) / hi * 100 <= self.boundary_proximity_pct if hi else False

        reasons = [f"rsi={r:.1f}", f"range=[{lo:.6g},{hi:.6g}]", f"vwap={v:.6g}"]

        if r <= self.rsi_oversold and near_low:
            stop = lo - atr_val * 0.8
            r_dist = last_close - stop
            if r_dist <= 0 or v <= last_close:
                return None
            target_r_multiple = (v - last_close) / r_dist
            return Signal(
                symbol=snapshot.symbol,
                setup_name=self.name,
                direction=Side.LONG,
                entry_price=last_close,
                stop_price=stop,
                take_profit_levels=(TakeProfitLevel(target_r_multiple, 1.0),),
                max_holding_seconds=self.max_holding_seconds,
                confidence=min(50 + (self.rsi_oversold - r), 90),
                reasons=tuple(reasons + ["near_range_low", f"target=vwap({v:.6g})"]),
                invalidation_conditions=("close_below_range_low_with_volume",),
                as_of_ms=snapshot.as_of_ms,
            )

        if r >= self.rsi_overbought and near_high:
            stop = hi + atr_val * 0.8
            r_dist = stop - last_close
            if r_dist <= 0 or v >= last_close:
                return None
            target_r_multiple = (last_close - v) / r_dist
            return Signal(
                symbol=snapshot.symbol,
                setup_name=self.name,
                direction=Side.SHORT,
                entry_price=last_close,
                stop_price=stop,
                take_profit_levels=(TakeProfitLevel(target_r_multiple, 1.0),),
                max_holding_seconds=self.max_holding_seconds,
                confidence=min(50 + (r - self.rsi_overbought), 90),
                reasons=tuple(reasons + ["near_range_high", f"target=vwap({v:.6g})"]),
                invalidation_conditions=("close_above_range_high_with_volume",),
                as_of_ms=snapshot.as_of_ms,
            )
        return None
