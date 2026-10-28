"""Transaction-cost model for research evaluation.

Fee figures are Binance USDT-M VIP0 schedule values (taker 0.05%, maker
0.02%) -- the tier a new account actually gets. Half-spread + slippage per
side are *assumptions*, not measurements: we have no historical quote data
(see data_ingestion/binance_vision.py). They are deliberately on the
conservative side for small (<$50k) orders on these contracts and every
result is re-reported under a stressed multiple.

The 'maker' scenario is reported only as an optimistic bound. It ignores
non-fills and adverse selection (a resting limit order tends to fill
precisely when price is moving through it), so it must never be the basis
for accepting a hypothesis.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


DEFAULT_IMPACT_BPS = {"BTCUSDT": 1.0, "ETHUSDT": 1.0}


@dataclass(frozen=True, slots=True)
class CostModel:
    taker_fee_bps: float = 5.0
    maker_fee_bps: float = 2.0
    default_impact_bps: float = 2.0                 # half-spread + slippage per side, alts
    impact_bps: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_IMPACT_BPS))
    stress_multiplier: float = 1.0
    scenario: str = "taker"                          # "taker" (base) or "maker" (optimistic bound)

    def per_side_bps(self, symbol: str) -> float:
        if self.scenario == "maker":
            return self.maker_fee_bps * self.stress_multiplier
        impact = self.impact_bps.get(symbol, self.default_impact_bps)
        return (self.taker_fee_bps + impact) * self.stress_multiplier

    def round_trip_bps(self, symbol: str) -> float:
        return 2.0 * self.per_side_bps(symbol)

    def stressed(self, mult: float) -> "CostModel":
        return CostModel(self.taker_fee_bps, self.maker_fee_bps, self.default_impact_bps,
                         dict(self.impact_bps), mult, self.scenario)

    def as_maker(self) -> "CostModel":
        return CostModel(self.taker_fee_bps, self.maker_fee_bps, self.default_impact_bps,
                         dict(self.impact_bps), self.stress_multiplier, "maker")

    def to_dict(self) -> dict:
        return asdict(self)
