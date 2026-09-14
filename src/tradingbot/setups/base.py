"""Setup detection base classes (spec section 22).

Each concrete setup is a small, explicit rule set: exact long/short entry
conditions, invalidation, stop/target logic, holding-time limit, and the
regimes it is allowed to run in. The engine does NOT require every possible
data source to agree (spec section 24) -- each setup declares which
confirmations are essential (checked in `detect`) versus which are merely
contextual scoring inputs (handled later by `signal_engine.scorer`).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Sequence

from tradingbot.data.models import Candle, ContractSpec, FundingRate, Liquidation, OpenInterest, OrderBookSnapshot, Side, Trade
from tradingbot.features.pump_dump import AbnormalMoveScore
from tradingbot.regime.classifier import RegimeSnapshot, RiskFlag, TrendRegime


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    """Everything a setup may look at, all restricted to information that
    would genuinely have been available at `as_of_ms` -- the caller (live
    scanner or backtester) is responsible for that cutoff."""

    symbol: str
    as_of_ms: int
    spec: ContractSpec
    candles_entry_tf: list[Candle]        # e.g. 1m, newest last, closed candles only
    candles_confirm_tf: list[Candle]      # e.g. 5m
    candles_context_tf: list[Candle]      # e.g. 1h
    order_book: OrderBookSnapshot
    recent_trades: list[Trade]
    prior_trades: list[Trade]             # equal-length window immediately before recent_trades
    funding: FundingRate | None
    open_interest_now: OpenInterest | None
    open_interest_prior: OpenInterest | None
    recent_liquidations: list[Liquidation]
    regime: RegimeSnapshot
    btc_regime: RegimeSnapshot | None
    abnormal_move: AbnormalMoveScore
    spread_bps: float | None
    depth_usd: float


@dataclass(frozen=True, slots=True)
class TakeProfitLevel:
    r_multiple: float
    fraction: float   # fraction of position to close at this level


@dataclass(frozen=True, slots=True)
class Signal:
    symbol: str
    setup_name: str
    direction: Side
    entry_price: float
    stop_price: float
    take_profit_levels: tuple[TakeProfitLevel, ...]
    max_holding_seconds: int
    confidence: float                      # 0-100, setup-internal confidence
    reasons: tuple[str, ...] = field(default_factory=tuple)
    invalidation_conditions: tuple[str, ...] = field(default_factory=tuple)
    as_of_ms: int = 0

    @property
    def risk_per_unit(self) -> float:
        return abs(self.entry_price - self.stop_price)

    def reward_to_risk(self) -> float:
        """Weighted average R-multiple across take-profit levels, weighted
        by the fraction of the position each level closes -- e.g. 50% at 1R
        and 50% at 2R is a 1.5 weighted reward-to-risk."""
        return sum(tp.r_multiple * tp.fraction for tp in self.take_profit_levels)


class Setup(ABC):
    """Base class for one scalping setup."""

    name: str
    allowed_trend_regimes: set[TrendRegime]
    blocked_risk_flags: set[RiskFlag] = {RiskFlag.MANIPULATION_RISK, RiskFlag.LOW_LIQUIDITY}
    max_holding_seconds: int = 300
    max_spread_bps: float = 8.0
    min_reward_to_risk: float = 1.3
    cooldown_seconds: int = 60
    pump_score_hard_block: float = 90.0
    dump_score_hard_block: float = 90.0

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        if not snapshot.regime.allows(self.allowed_trend_regimes, self.blocked_risk_flags):
            return None
        if snapshot.spread_bps is not None and snapshot.spread_bps > self.max_spread_bps:
            return None
        if snapshot.abnormal_move.score >= self.pump_score_hard_block and not self.allow_high_abnormal_move():
            return None

        signal = self.detect(snapshot)
        if signal is None:
            return None
        if signal.reward_to_risk() < self.min_reward_to_risk:
            return None
        return signal

    def allow_high_abnormal_move(self) -> bool:
        """Override to True for setups explicitly designed to trade
        momentum/liquidation events (spec section 12: a tested momentum
        setup MAY still trade a pump under controlled risk)."""
        return False

    @abstractmethod
    def detect(self, snapshot: MarketSnapshot) -> Signal | None:
        ...
