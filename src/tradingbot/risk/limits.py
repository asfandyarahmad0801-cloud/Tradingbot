"""Portfolio-level hard risk limits and kill switch (spec section 28).

This is the last line of defense: even a perfectly-scored, positive-EV
signal must pass through here before an order is ever placed. Every
rejection reason is returned explicitly so it can be logged (spec section 45
-- rejected setups and risk-limit events must never be silently dropped).

Priority hierarchy (spec section 63): capital preservation first. This
module has veto power over everything upstream.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from tradingbot.config import RiskConfig
from tradingbot.data.models import Side


@dataclass(slots=True)
class OpenPositionInfo:
    symbol: str
    side: Side
    notional: float
    leverage: float
    setup_name: str
    correlation_cluster: str | None = None


@dataclass(slots=True)
class PortfolioState:
    equity: float
    open_positions: list[OpenPositionInfo] = field(default_factory=list)
    daily_pnl_pct: float = 0.0
    weekly_pnl_pct: float = 0.0
    consecutive_losses: int = 0
    trade_entry_timestamps_ms: list[int] = field(default_factory=list)
    trades_today_by_symbol: dict[str, int] = field(default_factory=dict)
    last_exit_ts_ms_by_symbol: dict[str, int] = field(default_factory=dict)
    last_loss_ts_ms_by_symbol: dict[str, int] = field(default_factory=dict)

    def gross_notional(self) -> float:
        return sum(p.notional for p in self.open_positions)

    def effective_account_leverage(self) -> float:
        if self.equity <= 0:
            return float("inf")
        return self.gross_notional() / self.equity

    def cluster_exposure(self, cluster: str) -> float:
        return sum(p.notional for p in self.open_positions if p.correlation_cluster == cluster)


@dataclass(slots=True)
class KillSwitch:
    """Operator- or system-triggered emergency controls (spec section 28)."""

    halt_new_positions: bool = False
    close_all_requested: bool = False
    cancel_all_requested: bool = False
    disable_longs: bool = False
    disable_shorts: bool = False
    disable_high_leverage: bool = False
    high_leverage_threshold: float = 3.0
    disabled_symbols: set[str] = field(default_factory=set)
    disabled_strategies: set[str] = field(default_factory=set)
    disabled_exchanges: set[str] = field(default_factory=set)


class RiskEngine:
    def __init__(self, config: RiskConfig) -> None:
        self.config = config

    def check_new_trade(
        self,
        portfolio: PortfolioState,
        kill_switch: KillSwitch,
        symbol: str,
        exchange_id: str,
        side: Side,
        setup_name: str,
        notional: float,
        leverage: float,
        now_ms: int,
        correlation_cluster: str | None = None,
    ) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        cfg = self.config

        if kill_switch.halt_new_positions:
            reasons.append("kill_switch:new_positions_halted")
        if kill_switch.close_all_requested:
            reasons.append("kill_switch:close_all_in_progress")
        if exchange_id in kill_switch.disabled_exchanges:
            reasons.append(f"kill_switch:exchange_disabled:{exchange_id}")
        if symbol in kill_switch.disabled_symbols:
            reasons.append(f"kill_switch:symbol_disabled:{symbol}")
        if setup_name in kill_switch.disabled_strategies:
            reasons.append(f"kill_switch:strategy_disabled:{setup_name}")
        if side == Side.LONG and kill_switch.disable_longs:
            reasons.append("kill_switch:longs_disabled")
        if side == Side.SHORT and kill_switch.disable_shorts:
            reasons.append("kill_switch:shorts_disabled")
        if kill_switch.disable_high_leverage and leverage > kill_switch.high_leverage_threshold:
            reasons.append(f"kill_switch:leverage_{leverage}x_exceeds_threshold_{kill_switch.high_leverage_threshold}x")

        if portfolio.daily_pnl_pct <= -cfg.max_daily_loss_pct:
            reasons.append(f"daily_loss_limit_breached:{portfolio.daily_pnl_pct:.2f}%<=-{cfg.max_daily_loss_pct}%")
        if portfolio.weekly_pnl_pct <= -cfg.max_weekly_loss_pct:
            reasons.append(f"weekly_loss_limit_breached:{portfolio.weekly_pnl_pct:.2f}%<=-{cfg.max_weekly_loss_pct}%")
        if portfolio.consecutive_losses >= cfg.max_consecutive_losses:
            reasons.append(f"max_consecutive_losses_reached:{portfolio.consecutive_losses}")

        if len(portfolio.open_positions) >= cfg.max_concurrent_positions:
            reasons.append(f"max_concurrent_positions_reached:{cfg.max_concurrent_positions}")
        positions_on_symbol = sum(1 for p in portfolio.open_positions if p.symbol == symbol)
        if positions_on_symbol >= cfg.max_positions_per_coin:
            reasons.append(f"max_positions_per_coin_reached:{symbol}")

        equity = max(portfolio.equity, 1e-9)
        projected_exposure_pct = (portfolio.gross_notional() + notional) / equity * 100
        if projected_exposure_pct > cfg.max_portfolio_exposure_pct:
            reasons.append(f"portfolio_exposure_would_exceed_limit:{projected_exposure_pct:.1f}%>{cfg.max_portfolio_exposure_pct}%")

        projected_leverage = (portfolio.gross_notional() + notional) / equity
        if projected_leverage > cfg.max_effective_account_leverage:
            reasons.append(f"effective_account_leverage_would_exceed_limit:{projected_leverage:.2f}x>{cfg.max_effective_account_leverage}x")

        if leverage > cfg.max_position_leverage:
            reasons.append(f"position_leverage_exceeds_limit:{leverage}x>{cfg.max_position_leverage}x")

        if correlation_cluster is not None:
            projected_cluster_pct = (portfolio.cluster_exposure(correlation_cluster) + notional) / equity * 100
            if projected_cluster_pct > cfg.max_correlated_cluster_exposure_pct:
                reasons.append(
                    f"correlated_cluster_exposure_would_exceed_limit:{correlation_cluster}:{projected_cluster_pct:.1f}%>{cfg.max_correlated_cluster_exposure_pct}%"
                )

        one_hour_ago = now_ms - 3600_000
        trades_last_hour = sum(1 for t in portfolio.trade_entry_timestamps_ms if t >= one_hour_ago)
        if trades_last_hour >= cfg.max_trades_per_hour:
            reasons.append(f"max_trades_per_hour_reached:{trades_last_hour}")

        trades_today_symbol = portfolio.trades_today_by_symbol.get(symbol, 0)
        if trades_today_symbol >= cfg.max_trades_per_coin_per_day:
            reasons.append(f"max_trades_per_coin_per_day_reached:{symbol}:{trades_today_symbol}")

        last_exit = portfolio.last_exit_ts_ms_by_symbol.get(symbol)
        if last_exit is not None and (now_ms - last_exit) < cfg.cooldown_seconds_after_exit * 1000:
            reasons.append(f"cooldown_after_exit_active:{symbol}")

        last_loss = portfolio.last_loss_ts_ms_by_symbol.get(symbol)
        if last_loss is not None and (now_ms - last_loss) < cfg.cooldown_seconds_after_loss * 1000:
            reasons.append(f"cooldown_after_loss_active:{symbol}")

        return (len(reasons) == 0, reasons)
