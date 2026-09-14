"""Trade expectancy / expected-value calculation (spec section 25).

EV is computed in basis points of entry notional so it's directly comparable
across coins of wildly different price levels, and directly comparable to
cost components (fees, spread, slippage, funding) which are naturally
expressed the same way.

Honesty note: `win_probability` here is a HEURISTIC derived from the
setup's own historical calibration (backtest hit-rate by setup, see
`backtest/metrics.py`) or, absent that, the setup's self-reported
`confidence` as a rough prior. It is not a guarantee -- spec section 38
reserves genuine probability *estimation* for a calibrated model trained on
walk-forward validated outcomes. Until such a model exists and is validated,
treat `min_win_probability` in config as a conservative floor, not a
precise forecast.
"""
from __future__ import annotations

from dataclasses import dataclass

from tradingbot.data.models import ContractSpec, FundingRate
from tradingbot.features.derivatives_features import estimate_funding_cost_bps
from tradingbot.setups.base import Signal


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    entry_fee_bps: float
    exit_fee_bps: float
    entry_slippage_bps: float
    exit_slippage_bps: float
    funding_bps: float
    spread_cost_bps: float

    @property
    def total_bps(self) -> float:
        return (
            self.entry_fee_bps + self.exit_fee_bps + self.entry_slippage_bps
            + self.exit_slippage_bps + self.funding_bps + self.spread_cost_bps
        )


@dataclass(frozen=True, slots=True)
class ExpectancyResult:
    win_probability: float
    reward_bps: float
    risk_bps: float
    costs: CostBreakdown
    expected_value_bps: float
    reward_to_risk: float

    def passes(self, min_ev_bps: float, min_reward_to_risk: float, min_win_probability: float) -> bool:
        return (
            self.expected_value_bps >= min_ev_bps
            and self.reward_to_risk >= min_reward_to_risk
            and self.win_probability >= min_win_probability
        )


def estimate_costs(
    spec: ContractSpec,
    is_maker_entry: bool,
    is_maker_exit: bool,
    spread_bps: float,
    estimated_slippage_bps: float,
    funding: FundingRate | None,
    position_open_ts_ms: int,
    expected_close_ts_ms: int,
) -> CostBreakdown:
    entry_fee = spec.maker_fee_bps if is_maker_entry else spec.taker_fee_bps
    exit_fee = spec.maker_fee_bps if is_maker_exit else spec.taker_fee_bps
    funding_bps = 0.0
    if funding is not None:
        funding_bps = estimate_funding_cost_bps(funding, position_open_ts_ms, expected_close_ts_ms)

    # Spread cost is only counted once here (crossing the spread on entry);
    # if the exit is also a taker order its slippage estimate already
    # captures the effective spread paid on the way out.
    spread_cost = spread_bps / 2.0 if not is_maker_entry else 0.0

    return CostBreakdown(
        entry_fee_bps=entry_fee,
        exit_fee_bps=exit_fee,
        entry_slippage_bps=estimated_slippage_bps if not is_maker_entry else 0.0,
        exit_slippage_bps=estimated_slippage_bps if not is_maker_exit else 0.0,
        funding_bps=funding_bps,
        spread_cost_bps=spread_cost,
    )


def compute_expectancy(
    signal: Signal,
    win_probability: float,
    costs: CostBreakdown,
) -> ExpectancyResult:
    risk_bps = signal.risk_per_unit / signal.entry_price * 10_000
    weighted_r = sum(tp.r_multiple * tp.fraction for tp in signal.take_profit_levels)
    reward_bps = weighted_r * risk_bps

    ev_bps = (
        win_probability * reward_bps
        - (1 - win_probability) * risk_bps
        - costs.total_bps
    )
    reward_to_risk = reward_bps / risk_bps if risk_bps > 0 else 0.0

    return ExpectancyResult(
        win_probability=win_probability,
        reward_bps=reward_bps,
        risk_bps=risk_bps,
        costs=costs,
        expected_value_bps=ev_bps,
        reward_to_risk=reward_to_risk,
    )


def win_probability_from_confidence(confidence_0_100: float, floor: float = 0.30, ceiling: float = 0.65) -> float:
    """Conservative, monotonic mapping from a setup's self-reported
    confidence to a win-probability prior, clamped well below 'certain' --
    see module docstring. This should be REPLACED per-setup with a
    backtest-calibrated hit rate as soon as one is available
    (`backtest/metrics.py` computes exactly that breakdown)."""
    fraction = max(0.0, min(confidence_0_100, 100.0)) / 100.0
    return floor + fraction * (ceiling - floor)
