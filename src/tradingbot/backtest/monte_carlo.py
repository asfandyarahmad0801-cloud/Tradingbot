"""Monte Carlo resampling of historical trade outcomes (spec section 35).

Resamples (with replacement) the realized per-trade bps returns to estimate
a distribution of plausible equity paths, rather than judging the strategy
by the single realized backtest path. This assumes trade outcomes are
approximately IID, which is a simplification (real trades can cluster in
regime -- see docs/LIMITATIONS.md); it is still far more informative than
reporting only the point-estimate backtest curve.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class MonteCarloResult:
    n_simulations: int
    median_final_equity: float
    p5_final_equity: float
    p95_final_equity: float
    worst_case_drawdown_pct: float
    median_drawdown_pct: float
    probability_of_ruin: float   # fraction of paths hitting <= ruin_equity_fraction * starting_equity


def _max_drawdown_pct(equity_path: np.ndarray) -> float:
    peak = np.maximum.accumulate(equity_path)
    dd = (peak - equity_path) / np.where(peak == 0, 1, peak) * 100
    return float(dd.max())


def run_monte_carlo(
    trade_pnl_bps: list[float],
    starting_equity: float,
    n_simulations: int = 2000,
    trades_per_path: int | None = None,
    ruin_equity_fraction: float = 0.5,
    seed: int | None = 42,
) -> MonteCarloResult:
    if not trade_pnl_bps:
        return MonteCarloResult(0, starting_equity, starting_equity, starting_equity, 0.0, 0.0, 0.0)

    rng = np.random.default_rng(seed)
    n_trades = trades_per_path or len(trade_pnl_bps)
    pnl_arr = np.array(trade_pnl_bps) / 10_000.0  # fraction of notional risked-equivalent

    finals = np.empty(n_simulations)
    drawdowns = np.empty(n_simulations)
    ruin_count = 0

    for sim in range(n_simulations):
        sampled = rng.choice(pnl_arr, size=n_trades, replace=True)
        equity_path = starting_equity * np.cumprod(1 + sampled)
        equity_path = np.insert(equity_path, 0, starting_equity)
        finals[sim] = equity_path[-1]
        drawdowns[sim] = _max_drawdown_pct(equity_path)
        if equity_path.min() <= starting_equity * ruin_equity_fraction:
            ruin_count += 1

    return MonteCarloResult(
        n_simulations=n_simulations,
        median_final_equity=float(np.median(finals)),
        p5_final_equity=float(np.percentile(finals, 5)),
        p95_final_equity=float(np.percentile(finals, 95)),
        worst_case_drawdown_pct=float(drawdowns.max()),
        median_drawdown_pct=float(np.median(drawdowns)),
        probability_of_ruin=ruin_count / n_simulations,
    )
