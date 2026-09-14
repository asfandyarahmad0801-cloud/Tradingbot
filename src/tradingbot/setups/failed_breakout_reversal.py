"""Setup 20 / 4: Liquidity sweep and reclaim (failed breakout reversal).

Mechanism: price pokes beyond a visible range extreme -- often exactly where
resting stop orders / liquidations cluster -- then fails to hold and closes
back inside the range within a couple of bars. This is consistent with a
liquidity sweep (stops run, then absorbed) rather than a genuine breakout,
and is one of the more manipulation-resistant setups precisely because it
requires the false move to have already happened and reversed, rather than
predicting a move (spec section 49: don't try to front-run manipulators,
trade the aftermath once it's confirmed).

Failure conditions: the "failed" breakout is actually just early -- price
resumes beyond the sweep after a brief pause (this is why the stop sits
beyond the sweep extreme, not at entry).
"""
from __future__ import annotations

from tradingbot.data.models import Side
from tradingbot.features.market_structure import detect_failed_breakout
from tradingbot.features.volatility import atr
from tradingbot.regime.classifier import TrendRegime
from tradingbot.setups.base import MarketSnapshot, Setup, Signal, TakeProfitLevel

DEFAULT_TPS = (TakeProfitLevel(1.0, 0.5), TakeProfitLevel(2.0, 0.5))


class FailedBreakoutReversalSetup(Setup):
    name = "liquidity_sweep_and_reclaim"
    allowed_trend_regimes = {TrendRegime.RANGE, TrendRegime.WEAK_BULLISH, TrendRegime.WEAK_BEARISH}
    max_holding_seconds = 450
    min_reward_to_risk = 1.4
    lookback_bars = 20
    confirm_bars = 2

    def allow_high_abnormal_move(self) -> bool:
        return True

    def detect(self, snapshot: MarketSnapshot) -> Signal | None:
        candles = snapshot.candles_entry_tf
        if len(candles) < self.lookback_bars + self.confirm_bars + 5:
            return None

        result = detect_failed_breakout(candles, lookback=self.lookback_bars, confirm_bars=self.confirm_bars)
        if result is None:
            return None

        atr_val = atr(candles, period=14)
        if atr_val is None or atr_val <= 0:
            return None

        last_close = candles[-1].close
        sweep_bar = candles[-self.confirm_bars - 1]
        reasons = [f"pattern={result}"]

        if result == "failed_breakout_up":
            # Swept above range, failed, reversing down -> short.
            stop = sweep_bar.high + atr_val * 0.3
            return Signal(
                symbol=snapshot.symbol,
                setup_name=self.name,
                direction=Side.SHORT,
                entry_price=last_close,
                stop_price=stop,
                take_profit_levels=DEFAULT_TPS,
                max_holding_seconds=self.max_holding_seconds,
                confidence=62.0,
                reasons=tuple(reasons),
                invalidation_conditions=("close_back_above_sweep_high",),
                as_of_ms=snapshot.as_of_ms,
            )

        if result == "failed_breakout_down":
            # Swept below range, failed, reversing up -> long.
            stop = sweep_bar.low - atr_val * 0.3
            return Signal(
                symbol=snapshot.symbol,
                setup_name=self.name,
                direction=Side.LONG,
                entry_price=last_close,
                stop_price=stop,
                take_profit_levels=DEFAULT_TPS,
                max_holding_seconds=self.max_holding_seconds,
                confidence=62.0,
                reasons=tuple(reasons),
                invalidation_conditions=("close_back_below_sweep_low",),
                as_of_ms=snapshot.as_of_ms,
            )
        return None
