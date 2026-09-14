"""Human-readable signal explanation generator (spec section 50).

Every trade/no-trade decision must be explainable without reading code.
This module renders the structured decision inputs (signal, score,
expectancy, risk decision) into the plain-text report format the spec
requests, and this exact string is what gets logged for every decision.
"""
from __future__ import annotations

from dataclasses import dataclass

from tradingbot.setups.base import Signal
from tradingbot.signal_engine.expectancy import ExpectancyResult
from tradingbot.signal_engine.scorer import SignalScore


@dataclass(frozen=True, slots=True)
class Decision:
    trade: bool
    risk_reasons: tuple[str, ...] = ()


def render_explanation(
    signal: Signal,
    score: SignalScore,
    expectancy: ExpectancyResult,
    decision: Decision,
    leverage: float | None = None,
    position_size_notional: float | None = None,
) -> str:
    lines = []
    lines.append(f"SIGNAL: {signal.direction.value.upper()}")
    lines.append("")
    lines.append(f"Symbol: {signal.symbol}")
    lines.append(f"Setup: {signal.setup_name}")
    lines.append(f"Score: {score.composite_score:.0f}/100")
    lines.append("")
    lines.append("Reasons:")
    for r in signal.reasons:
        lines.append(f"* {r}")
    for r in score.reasons:
        lines.append(f"* {r}")
    lines.append("")
    lines.append("Expectancy:")
    lines.append(f"* win_probability={expectancy.win_probability:.0%}")
    lines.append(f"* reward_to_risk={expectancy.reward_to_risk:.2f}")
    lines.append(f"* expected_value={expectancy.expected_value_bps:+.1f}bps")
    lines.append(f"* total_costs={expectancy.costs.total_bps:.1f}bps")
    lines.append("")
    if decision.risk_reasons:
        lines.append("Risks:")
        for r in decision.risk_reasons:
            lines.append(f"* {r}")
        lines.append("")
    lines.append(f"Decision: {'TRADE' if decision.trade else 'NO TRADE'}")
    if decision.trade:
        lines.append("")
        lines.append("Execution plan:")
        lines.append(f"* direction={signal.direction.value}")
        lines.append(f"* entry_price={signal.entry_price:.6g}")
        lines.append(f"* stop_price={signal.stop_price:.6g}")
        for tp in signal.take_profit_levels:
            lines.append(f"* take_profit={tp.r_multiple:.2f}R fraction={tp.fraction:.0%}")
        if leverage is not None:
            lines.append(f"* leverage={leverage:.2f}x")
        if position_size_notional is not None:
            lines.append(f"* position_notional={position_size_notional:,.2f}")
        lines.append(f"* max_holding_seconds={signal.max_holding_seconds}")
    return "\n".join(lines)
