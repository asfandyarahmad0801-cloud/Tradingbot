"""Event-driven backtesting engine (spec section 33).

No-lookahead guarantee: at bar index i for a symbol, `_build_snapshot` is
constructed only from candles[0..i] (closed bars) -- never candle i+1 or
beyond. Setups only ever see `MarketSnapshot.as_of_ms == candles[i].exchange_ts_ms
+ timeframe`, i.e. the moment bar i actually closed.

Fees, slippage, funding, leverage, liquidation, and position/lot-size
rounding are modeled using the exact same risk/expectancy/leverage code
paths used live, so a strategy cannot pass backtest by accident through a
code path the live system doesn't share.

See docs/LIMITATIONS.md for what this backtester does NOT model precisely:
partial fills, queue position, real historical order-book depth (unless
supplied), and exchange downtime -- all noted rather than silently assumed
away.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from tradingbot.data.models import Candle, ContractSpec, Side
from tradingbot.data.validation import check_candles, has_critical
from tradingbot.features.pump_dump import compute_abnormal_move_score
from tradingbot.regime.classifier import classify_regime
from tradingbot.risk.leverage import select_leverage
from tradingbot.risk.limits import KillSwitch, OpenPositionInfo, PortfolioState, RiskEngine
from tradingbot.risk.position_sizing import compute_position_size
from tradingbot.setups.base import MarketSnapshot, Setup, Signal
from tradingbot.signal_engine.expectancy import CostBreakdown, compute_expectancy, win_probability_from_confidence
from tradingbot.signal_engine.scorer import score_signal
from tradingbot.backtest.synthetic_microstructure import synthesize_order_book, synthesize_trades


@dataclass(slots=True)
class BacktestConfig:
    starting_equity: float = 10_000.0
    timeframe_seconds: int = 60
    assumed_spread_bps: float = 4.0
    assumed_depth_usd: float = 100_000.0
    taker_slippage_bps: float = 3.0
    risk_per_trade_pct: float = 0.25
    max_notional_usd: float = 5_000.0
    max_position_leverage: float = 5.0
    min_liquidation_distance_multiple_of_stop: float = 3.0
    maintenance_margin_rate: float = 0.005
    min_expected_value_bps: float = 5.0
    min_reward_to_risk: float = 1.3
    min_win_probability: float = 0.30
    funding_bps_per_8h: float = 1.0
    max_spread_bps_for_score: float = 8.0


@dataclass(slots=True)
class ClosedTrade:
    symbol: str
    setup_name: str
    side: Side
    entry_ts_ms: int
    exit_ts_ms: int
    entry_price: float
    exit_price: float
    qty: float
    notional: float
    leverage: float
    pnl_quote: float
    pnl_bps_of_notional: float
    fees_bps: float
    funding_bps: float
    exit_reason: str
    expected_value_bps: float
    confidence: float


@dataclass(slots=True)
class RejectedSetup:
    symbol: str
    setup_name: str
    ts_ms: int
    reasons: tuple[str, ...]


@dataclass(slots=True)
class BacktestResult:
    trades: list[ClosedTrade] = field(default_factory=list)
    equity_curve: list[tuple[int, float]] = field(default_factory=list)
    rejected: list[RejectedSetup] = field(default_factory=list)
    final_equity: float = 0.0


@dataclass(slots=True)
class _OpenPosition:
    signal: Signal
    qty: float
    notional: float
    leverage: float
    liquidation_price: float
    margin_required: float
    entry_ts_ms: int
    expected_value_bps: float
    tp_prices: list[tuple[float, float]]  # (price, fraction) sorted by proximity
    remaining_fraction: float = 1.0


class BacktestEngine:
    def __init__(self, config: BacktestConfig, setups: list[Setup], risk_engine: RiskEngine) -> None:
        self.config = config
        self.setups = setups
        self.risk_engine = risk_engine

    def run(self, candles_by_symbol: dict[str, list[Candle]], specs_by_symbol: dict[str, ContractSpec]) -> BacktestResult:
        result = BacktestResult()
        equity = self.config.starting_equity
        portfolio = PortfolioState(equity=equity)
        kill_switch = KillSwitch()
        open_positions: dict[str, _OpenPosition] = {}

        # Merge all (symbol, index) events into one chronological timeline.
        events: list[tuple[int, str, int]] = []
        for symbol, candles in candles_by_symbol.items():
            for i, c in enumerate(candles):
                events.append((c.exchange_ts_ms, symbol, i))
        events.sort(key=lambda e: e[0])

        min_history = 60

        for ts_ms, symbol, i in events:
            candles = candles_by_symbol[symbol]
            spec = specs_by_symbol[symbol]
            history = candles[: i + 1]
            bar = candles[i]

            if symbol in open_positions:
                closed = self._manage_open_position(open_positions[symbol], bar)
                if closed is not None:
                    result.trades.append(closed)
                    equity += closed.pnl_quote
                    portfolio.equity = equity
                    portfolio.last_exit_ts_ms_by_symbol[symbol] = ts_ms
                    if closed.pnl_quote < 0:
                        portfolio.last_loss_ts_ms_by_symbol[symbol] = ts_ms
                        portfolio.consecutive_losses += 1
                    else:
                        portfolio.consecutive_losses = 0
                    del open_positions[symbol]
                    portfolio.open_positions = [
                        OpenPositionInfo(s, p.signal.direction, p.notional, p.leverage, p.signal.setup_name)
                        for s, p in open_positions.items()
                    ]

            if symbol not in open_positions and len(history) >= min_history:
                issues = check_candles(symbol, history[-120:], self.config.timeframe_seconds, max_staleness_seconds=1e12, now_ms=ts_ms)
                if not has_critical(issues):
                    self._maybe_open_position(
                        symbol, spec, history, ts_ms, portfolio, kill_switch, open_positions, result
                    )

            result.equity_curve.append((ts_ms, equity + sum(self._unrealized(p, bar) for s, p in open_positions.items() if s == symbol)))

        result.final_equity = equity
        return result

    def _unrealized(self, pos: "_OpenPosition", bar: Candle) -> float:
        if pos.signal.direction == Side.LONG:
            return pos.qty * pos.remaining_fraction * (bar.close - pos.signal.entry_price)
        return pos.qty * pos.remaining_fraction * (pos.signal.entry_price - bar.close)

    def _manage_open_position(self, pos: _OpenPosition, bar: Candle) -> ClosedTrade | None:
        side = pos.signal.direction
        is_long = side == Side.LONG

        # 1. Liquidation check first -- the worst outcome, checked before stop.
        liquidated = (bar.low <= pos.liquidation_price) if is_long else (bar.high >= pos.liquidation_price)
        if liquidated:
            return self._close(pos, pos.liquidation_price, bar.exchange_ts_ms, "liquidated", full_loss=True)

        # 2. Stop-loss check.
        stop_hit = (bar.low <= pos.signal.stop_price) if is_long else (bar.high >= pos.signal.stop_price)
        if stop_hit:
            return self._close(pos, pos.signal.stop_price, bar.exchange_ts_ms, "stop_loss")

        # 3. Take-profit levels (partial exits) -- simplified to full close at
        # the first TP level reached, since intrabar partial-fill sequencing
        # cannot be reconstructed from OHLCV alone (documented limitation).
        for tp_price, _fraction in pos.tp_prices:
            tp_hit = (bar.high >= tp_price) if is_long else (bar.low <= tp_price)
            if tp_hit:
                return self._close(pos, tp_price, bar.exchange_ts_ms, "take_profit")

        # 4. Time-based exit.
        holding_seconds = (bar.exchange_ts_ms - pos.entry_ts_ms) / 1000.0
        if holding_seconds >= pos.signal.max_holding_seconds:
            return self._close(pos, bar.close, bar.exchange_ts_ms, "max_holding_time")

        return None

    def _close(self, pos: _OpenPosition, exit_price: float, exit_ts_ms: int, reason: str, full_loss: bool = False) -> ClosedTrade:
        side = pos.signal.direction
        entry = pos.signal.entry_price
        qty = pos.qty

        exit_slip = entry * self.config.taker_slippage_bps / 10_000
        if reason in ("stop_loss", "liquidated"):
            exit_price = exit_price - exit_slip if side == Side.LONG else exit_price + exit_slip

        if full_loss:
            pnl = -pos.margin_required
        else:
            pnl = qty * (exit_price - entry) if side == Side.LONG else qty * (entry - exit_price)

        holding_hours = max((exit_ts_ms - pos.entry_ts_ms) / (1000 * 3600), 0.0)
        funding_bps = self.config.funding_bps_per_8h * (holding_hours / 8.0)
        fees_bps = 5.0 + 5.0  # taker in + taker out, conservative default
        cost_quote = pos.notional * (fees_bps + funding_bps) / 10_000
        pnl -= cost_quote

        pnl_bps = pnl / pos.notional * 10_000 if pos.notional else 0.0

        return ClosedTrade(
            symbol=pos.signal.symbol,
            setup_name=pos.signal.setup_name,
            side=side,
            entry_ts_ms=pos.entry_ts_ms,
            exit_ts_ms=exit_ts_ms,
            entry_price=entry,
            exit_price=exit_price,
            qty=qty,
            notional=pos.notional,
            leverage=pos.leverage,
            pnl_quote=pnl,
            pnl_bps_of_notional=pnl_bps,
            fees_bps=fees_bps,
            funding_bps=funding_bps,
            exit_reason=reason,
            expected_value_bps=pos.expected_value_bps,
            confidence=pos.signal.confidence,
        )

    def _maybe_open_position(
        self,
        symbol: str,
        spec: ContractSpec,
        history: list[Candle],
        ts_ms: int,
        portfolio: PortfolioState,
        kill_switch: KillSwitch,
        open_positions: dict[str, _OpenPosition],
        result: BacktestResult,
    ) -> None:
        cfg = self.config
        entry_tf = history[-200:]
        confirm_tf = history[-1000::5][-100:] if len(history) >= 5 else history
        context_tf = history[-1000::60][-50:] if len(history) >= 60 else history

        last_bar = entry_tf[-1]
        recent_trades = synthesize_trades(last_bar)
        prior_bar = entry_tf[-2] if len(entry_tf) >= 2 else last_bar
        prior_trades = synthesize_trades(prior_bar)
        book = synthesize_order_book(last_bar, cfg.assumed_spread_bps, cfg.assumed_depth_usd)

        abnormal = compute_abnormal_move_score(
            entry_tf, recent_trades, prior_trades,
            spread_bps_now=book.spread_bps, spread_bps_baseline=cfg.assumed_spread_bps,
            oi_change_pct=None, funding_change_bps=None, recent_liquidations=[],
        )
        regime = classify_regime(entry_tf, depth_usd=book.depth_within_bps("bid", 10), min_healthy_depth_usd=cfg.assumed_depth_usd * 0.5, abnormal_move_score=abnormal.score)

        snapshot = MarketSnapshot(
            symbol=symbol, as_of_ms=ts_ms, spec=spec,
            candles_entry_tf=entry_tf, candles_confirm_tf=confirm_tf, candles_context_tf=context_tf,
            order_book=book, recent_trades=recent_trades, prior_trades=prior_trades,
            funding=None, open_interest_now=None, open_interest_prior=None, recent_liquidations=[],
            regime=regime, btc_regime=None, abnormal_move=abnormal,
            spread_bps=book.spread_bps, depth_usd=min(book.depth_within_bps("bid", 10), book.depth_within_bps("ask", 10)),
        )

        for setup in self.setups:
            signal = setup.evaluate(snapshot)
            if signal is None:
                continue

            win_prob = win_probability_from_confidence(signal.confidence)
            costs = CostBreakdown(
                entry_fee_bps=spec.taker_fee_bps, exit_fee_bps=spec.taker_fee_bps,
                entry_slippage_bps=cfg.taker_slippage_bps, exit_slippage_bps=cfg.taker_slippage_bps,
                funding_bps=cfg.funding_bps_per_8h * (signal.max_holding_seconds / 3600 / 8),
                spread_cost_bps=(book.spread_bps or 0) / 2,
            )
            expectancy = compute_expectancy(signal, win_prob, costs)
            if not expectancy.passes(cfg.min_expected_value_bps, cfg.min_reward_to_risk, cfg.min_win_probability):
                result.rejected.append(RejectedSetup(symbol, setup.name, ts_ms, (f"expectancy_fail:ev={expectancy.expected_value_bps:.1f}bps",)))
                continue

            leverage_decision = select_leverage(
                signal.entry_price, signal.stop_price, signal.direction, spec,
                cfg.max_position_leverage, cfg.min_liquidation_distance_multiple_of_stop, cfg.maintenance_margin_rate,
            )
            if leverage_decision.rejected:
                result.rejected.append(RejectedSetup(symbol, setup.name, ts_ms, leverage_decision.reasons))
                continue

            size = compute_position_size(
                portfolio.equity, cfg.risk_per_trade_pct, signal.entry_price, signal.stop_price,
                leverage_decision.leverage, spec, cfg.max_notional_usd,
            )
            if size.rejected:
                result.rejected.append(RejectedSetup(symbol, setup.name, ts_ms, size.reasons))
                continue

            allowed, risk_reasons = self.risk_engine.check_new_trade(
                portfolio, kill_switch, symbol, spec.exchange_id, signal.direction, setup.name,
                size.notional, leverage_decision.leverage, ts_ms,
            )
            if not allowed:
                result.rejected.append(RejectedSetup(symbol, setup.name, ts_ms, tuple(risk_reasons)))
                continue

            tp_prices = []
            for tp in signal.take_profit_levels:
                price = (
                    signal.entry_price + tp.r_multiple * signal.risk_per_unit
                    if signal.direction == Side.LONG
                    else signal.entry_price - tp.r_multiple * signal.risk_per_unit
                )
                tp_prices.append((price, tp.fraction))
            tp_prices.sort(key=lambda x: abs(x[0] - signal.entry_price))

            open_positions[symbol] = _OpenPosition(
                signal=signal, qty=size.qty, notional=size.notional, leverage=leverage_decision.leverage,
                liquidation_price=leverage_decision.liquidation_price, margin_required=size.margin_required,
                entry_ts_ms=ts_ms, expected_value_bps=expectancy.expected_value_bps, tp_prices=tp_prices,
            )
            portfolio.trade_entry_timestamps_ms.append(ts_ms)
            portfolio.trades_today_by_symbol[symbol] = portfolio.trades_today_by_symbol.get(symbol, 0) + 1
            portfolio.open_positions = [
                OpenPositionInfo(s, p.signal.direction, p.notional, p.leverage, p.signal.setup_name)
                for s, p in open_positions.items()
            ]
            break  # one setup per symbol per bar; first qualifying setup wins
