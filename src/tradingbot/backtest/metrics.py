"""Performance metrics and breakdowns (spec section 36).

Every breakdown the spec asks for (by coin, by setup, by exit reason, ...)
is a groupby over the same `list[ClosedTrade]` -- implemented generically so
adding a new breakdown dimension doesn't require new code, just a new key
function.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

from tradingbot.backtest.engine import ClosedTrade


@dataclass(frozen=True, slots=True)
class PerformanceSummary:
    trade_count: int
    win_rate: float
    avg_win_bps: float
    avg_loss_bps: float
    profit_factor: float
    expectancy_bps: float
    sharpe_like: float          # mean/std of per-trade bps returns, NOT time-annualized
    max_drawdown_pct: float
    total_pnl_quote: float
    avg_holding_seconds: float
    median_holding_seconds: float


def summarize(trades: list[ClosedTrade], starting_equity: float) -> PerformanceSummary:
    if not trades:
        return PerformanceSummary(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    wins = [t for t in trades if t.pnl_quote > 0]
    losses = [t for t in trades if t.pnl_quote <= 0]
    win_rate = len(wins) / len(trades)
    avg_win = sum(t.pnl_bps_of_notional for t in wins) / len(wins) if wins else 0.0
    avg_loss = sum(t.pnl_bps_of_notional for t in losses) / len(losses) if losses else 0.0
    gross_win = sum(t.pnl_quote for t in wins)
    gross_loss = abs(sum(t.pnl_quote for t in losses))
    profit_factor = gross_win / gross_loss if gross_loss > 0 else float("inf") if gross_win > 0 else 0.0
    expectancy_bps = sum(t.pnl_bps_of_notional for t in trades) / len(trades)

    bps_returns = [t.pnl_bps_of_notional for t in trades]
    mean = sum(bps_returns) / len(bps_returns)
    var = sum((r - mean) ** 2 for r in bps_returns) / max(len(bps_returns) - 1, 1)
    std = math.sqrt(var)
    sharpe_like = mean / std if std > 0 else 0.0

    equity = starting_equity
    peak = equity
    max_dd = 0.0
    for t in sorted(trades, key=lambda t: t.exit_ts_ms):
        equity += t.pnl_quote
        peak = max(peak, equity)
        dd = (peak - equity) / peak * 100 if peak > 0 else 0.0
        max_dd = max(max_dd, dd)

    holding = [(t.exit_ts_ms - t.entry_ts_ms) / 1000 for t in trades]
    holding_sorted = sorted(holding)
    median_holding = holding_sorted[len(holding_sorted) // 2]

    return PerformanceSummary(
        trade_count=len(trades),
        win_rate=win_rate,
        avg_win_bps=avg_win,
        avg_loss_bps=avg_loss,
        profit_factor=profit_factor,
        expectancy_bps=expectancy_bps,
        sharpe_like=sharpe_like,
        max_drawdown_pct=max_dd,
        total_pnl_quote=sum(t.pnl_quote for t in trades),
        avg_holding_seconds=sum(holding) / len(holding),
        median_holding_seconds=median_holding,
    )


def breakdown_by(trades: list[ClosedTrade], key) -> dict[str, PerformanceSummary]:
    groups: dict[str, list[ClosedTrade]] = defaultdict(list)
    for t in trades:
        groups[str(key(t))].append(t)
    return {k: summarize(v, starting_equity=sum(x.notional for x in v) or 1.0) for k, v in groups.items()}


def breakdown_by_symbol(trades: list[ClosedTrade]) -> dict[str, PerformanceSummary]:
    return breakdown_by(trades, lambda t: t.symbol)


def breakdown_by_setup(trades: list[ClosedTrade]) -> dict[str, PerformanceSummary]:
    return breakdown_by(trades, lambda t: t.setup_name)


def breakdown_by_exit_reason(trades: list[ClosedTrade]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for t in trades:
        counts[t.exit_reason] += 1
    return dict(counts)


def breakdown_by_side(trades: list[ClosedTrade]) -> dict[str, PerformanceSummary]:
    return breakdown_by(trades, lambda t: t.side.value)
