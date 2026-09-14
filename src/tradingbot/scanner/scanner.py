"""Real-time scanner orchestrator (spec architecture: scanner through
position management). Ties together every module built so far into one
per-symbol evaluation cycle, run concurrently across the eligible universe.

This is where "scan every eligible perpetual and trade any qualifying
setup, regardless of coin" is actually implemented: `run_cycle` is generic
over `symbol` and is invoked identically for BTC and for the newest
small-cap listing that just cleared the universe filters.
"""
from __future__ import annotations

import asyncio
import logging
import time

from tradingbot.config import AppConfig
from tradingbot.data.exchange_client import ExchangeClient
from tradingbot.data.models import ContractSpec, Side
from tradingbot.data.validation import check_candles, check_orderbook, has_critical
from tradingbot.execution.broker_base import Broker
from tradingbot.execution.order_manager import OrderManager
from tradingbot.features.pump_dump import compute_abnormal_move_score
from tradingbot.regime.classifier import RegimeSnapshot, classify_regime
from tradingbot.risk.leverage import select_leverage
from tradingbot.risk.limits import KillSwitch, OpenPositionInfo, PortfolioState, RiskEngine
from tradingbot.risk.position_sizing import compute_position_size
from tradingbot.setups.base import MarketSnapshot, Setup
from tradingbot.signal_engine.explanation import Decision, render_explanation
from tradingbot.signal_engine.expectancy import compute_expectancy, estimate_costs, win_probability_from_confidence
from tradingbot.signal_engine.scorer import score_signal
from tradingbot.storage.db import Repository
from tradingbot.universe.discovery import UniverseDiscovery

logger = logging.getLogger("tradingbot.scanner")


class Scanner:
    def __init__(
        self,
        config: AppConfig,
        client: ExchangeClient,
        setups: list[Setup],
        risk_engine: RiskEngine,
        broker: Broker,
        repository: Repository,
        mode: str,
    ) -> None:
        self.config = config
        self.client = client
        self.setups = setups
        self.risk_engine = risk_engine
        self.order_manager = OrderManager(broker)
        self.broker = broker
        self.repository = repository
        self.mode = mode
        self.portfolio = PortfolioState(equity=config.risk.risk_per_trade_pct)  # replaced on first cycle
        self.kill_switch = KillSwitch()
        self.discovery = UniverseDiscovery(client, config.universe)
        self._btc_regime: RegimeSnapshot | None = None
        self._open_trade_ids: dict[str, int] = {}
        self._open_entry_ts: dict[str, int] = {}

    async def refresh_portfolio_equity(self) -> None:
        self.portfolio.equity = await self.broker.get_balance()

    async def refresh_btc_regime(self) -> None:
        try:
            btc_candles = await self.client.fetch_ohlcv("BTC/USDT:USDT", "1m", limit=200)
            self._btc_regime = classify_regime(btc_candles, depth_usd=1e9, min_healthy_depth_usd=1.0)
        except Exception as exc:  # noqa: BLE001
            logger.warning("btc_regime_refresh_failed: %r", exc)

    async def build_snapshot(self, symbol: str, spec: ContractSpec) -> MarketSnapshot | None:
        try:
            entry_tf = await self.client.fetch_ohlcv(symbol, self.config.timeframes.entry[0], limit=200)
            confirm_tf = await self.client.fetch_ohlcv(symbol, self.config.timeframes.confirmation[0], limit=100)
            context_tf = await self.client.fetch_ohlcv(symbol, self.config.timeframes.higher_context[0], limit=50)
            book = await self.client.fetch_order_book(symbol, depth=20)
            recent_trades = await self.client.fetch_trades(symbol, limit=200)
            funding = await self.client.fetch_funding_rate(symbol)
            oi_now = await self.client.fetch_open_interest(symbol)
        except Exception as exc:  # noqa: BLE001 - one symbol's API failure must not kill the scan
            self.repository.log_risk_event("api_failure", f"{symbol}: {exc!r}")
            return None

        now_ms = int(time.time() * 1000)
        candle_issues = check_candles(symbol, entry_tf, timeframe_seconds=60, now_ms=now_ms)
        book_issues = check_orderbook(symbol, book, now_ms=now_ms)
        self.repository.log_data_quality_events(candle_issues + book_issues)
        if has_critical(candle_issues) or has_critical(book_issues):
            return None

        half = len(recent_trades) // 2
        prior_trades, recent_window = recent_trades[:half], recent_trades[half:]

        depth_usd = min(book.depth_within_bps("bid", 10), book.depth_within_bps("ask", 10))
        abnormal = compute_abnormal_move_score(
            entry_tf, recent_window, prior_trades,
            spread_bps_now=book.spread_bps, spread_bps_baseline=self.config.risk.max_spread_bps,
            oi_change_pct=None, funding_change_bps=None, recent_liquidations=[],
        )
        regime = classify_regime(
            entry_tf, depth_usd=depth_usd,
            min_healthy_depth_usd=self.config.universe.min_orderbook_depth_usd_within_10bps,
            abnormal_move_score=abnormal.score,
        )

        return MarketSnapshot(
            symbol=symbol, as_of_ms=now_ms, spec=spec,
            candles_entry_tf=entry_tf, candles_confirm_tf=confirm_tf, candles_context_tf=context_tf,
            order_book=book, recent_trades=recent_window, prior_trades=prior_trades,
            funding=funding, open_interest_now=oi_now, open_interest_prior=None, recent_liquidations=[],
            regime=regime, btc_regime=self._btc_regime, abnormal_move=abnormal,
            spread_bps=book.spread_bps, depth_usd=depth_usd,
        )

    async def run_cycle(self, symbol: str, spec: ContractSpec) -> None:
        if symbol in {p.symbol for p in self.portfolio.open_positions}:
            return  # position management for open trades happens elsewhere (position_management loop)

        snapshot = await self.build_snapshot(symbol, spec)
        if snapshot is None:
            return

        cfg = self.config
        for setup in self.setups:
            signal = setup.evaluate(snapshot)
            if signal is None:
                continue

            score = score_signal(snapshot, signal, cfg.risk.max_spread_bps, cfg.universe.min_orderbook_depth_usd_within_10bps)
            win_prob = win_probability_from_confidence(signal.confidence)
            now_ms = snapshot.as_of_ms
            costs = estimate_costs(
                spec, is_maker_entry=(cfg.execution.default_order_type != "market"), is_maker_exit=False,
                spread_bps=snapshot.spread_bps or 0.0, estimated_slippage_bps=cfg.execution.max_market_order_slippage_bps,
                funding=snapshot.funding, position_open_ts_ms=now_ms, expected_close_ts_ms=now_ms + signal.max_holding_seconds * 1000,
            )
            expectancy = compute_expectancy(signal, win_prob, costs)

            if not expectancy.passes(cfg.expectancy.min_expected_value_bps, cfg.expectancy.min_reward_to_risk, cfg.expectancy.min_win_probability):
                self.repository.log_decision(symbol, "no_trade", [f"expectancy_fail:ev={expectancy.expected_value_bps:.1f}bps"], setup.name)
                continue

            leverage_decision = select_leverage(
                signal.entry_price, signal.stop_price, signal.direction, spec,
                cfg.risk.max_position_leverage, cfg.risk.min_liquidation_distance_multiple_of_stop,
            )
            if leverage_decision.rejected:
                self.repository.log_decision(symbol, "rejected", list(leverage_decision.reasons), setup.name)
                continue

            size = compute_position_size(
                self.portfolio.equity, cfg.risk.risk_per_trade_pct, signal.entry_price, signal.stop_price,
                leverage_decision.leverage, spec, max_notional_usd=self.portfolio.equity * cfg.risk.max_effective_account_leverage,
            )
            if size.rejected:
                self.repository.log_decision(symbol, "rejected", list(size.reasons), setup.name)
                continue

            allowed, reasons = self.risk_engine.check_new_trade(
                self.portfolio, self.kill_switch, symbol, spec.exchange_id, signal.direction, setup.name,
                size.notional, leverage_decision.leverage, now_ms,
            )
            explanation = render_explanation(signal, score, expectancy, Decision(allowed, tuple(reasons)), leverage_decision.leverage, size.notional)
            logger.info("\n%s", explanation)

            if not allowed:
                self.repository.log_decision(symbol, "rejected", reasons, setup.name, explanation)
                continue

            await self.order_manager.broker.set_leverage(symbol, leverage_decision.leverage)
            managed = await self.order_manager.enter_with_protection(signal, size.qty)
            trade_id = self.repository.log_trade_opened(
                symbol=symbol, exchange=spec.exchange_id, direction=signal.direction.value, setup_name=setup.name,
                entry_price=signal.entry_price, stop_price=signal.stop_price,
                take_profit_json=[{"r": tp.r_multiple, "f": tp.fraction} for tp in signal.take_profit_levels],
                qty=size.qty, notional=size.notional, leverage=leverage_decision.leverage, margin_used=size.margin_required,
                estimated_liquidation_price=leverage_decision.liquidation_price, market_regime=snapshot.regime.trend.value,
                signal_score=score.composite_score, factor_scores_json=score.components.__dict__,
                confidence=signal.confidence, expected_value_bps=expectancy.expected_value_bps,
                expected_holding_seconds=signal.max_holding_seconds, mode=self.mode,
            )
            if managed.protected:
                self.portfolio.open_positions.append(
                    OpenPositionInfo(symbol, signal.direction, size.notional, leverage_decision.leverage, setup.name)
                )
                self.portfolio.trade_entry_timestamps_ms.append(now_ms)
                self.portfolio.trades_today_by_symbol[symbol] = self.portfolio.trades_today_by_symbol.get(symbol, 0) + 1
                self._open_trade_ids[symbol] = trade_id
                self._open_entry_ts[symbol] = now_ms
            else:
                self.repository.log_risk_event("unprotected_position_emergency_exit", symbol)
            break  # one signal per symbol per cycle

    async def monitor_paper_positions_once(self) -> None:
        """Polls resting stop/take-profit trigger orders on the paper
        broker and reconciles closed positions into the portfolio state and
        trade log. No-op for the live broker, where the exchange itself
        executes resting conditional orders and reconciliation instead
        happens via `get_position` (see docs/LIMITATIONS.md for the live
        reconciliation gap this leaves)."""
        from tradingbot.execution.paper_broker import PaperBroker

        if not isinstance(self.broker, PaperBroker):
            return

        fills = await self.broker.check_pending_triggers()
        for symbol, order_type_value, order_result in fills:
            self.portfolio.open_positions = [p for p in self.portfolio.open_positions if p.symbol != symbol]
            now_ms = order_result.fill_ts_ms or int(time.time() * 1000)
            exit_reason = "stop_loss" if order_type_value == "stop_market" else "take_profit"

            trade_id = self._open_trade_ids.pop(symbol, None)
            entry_ts = self._open_entry_ts.pop(symbol, now_ms)
            if trade_id is not None:
                self.repository.log_trade_closed(
                    trade_id, exit_reason=exit_reason, actual_holding_seconds=(now_ms - entry_ts) / 1000.0,
                )
            self.portfolio.last_exit_ts_ms_by_symbol[symbol] = now_ms
            if exit_reason == "stop_loss":
                self.portfolio.last_loss_ts_ms_by_symbol[symbol] = now_ms
                self.portfolio.consecutive_losses += 1
            else:
                self.portfolio.consecutive_losses = 0

    async def position_monitor_loop(self, interval_seconds: float = 5.0) -> None:
        while True:
            try:
                await self.monitor_paper_positions_once()
            except Exception as exc:  # noqa: BLE001 - the monitor loop must never die silently
                logger.error("position_monitor_error: %r", exc)
            await asyncio.sleep(interval_seconds)

    async def scan_universe_once(self) -> None:
        await self.refresh_portfolio_equity()
        await self.refresh_btc_regime()
        entries = await self.discovery.scan()
        self.repository.log_universe_snapshot(entries)
        eligible = [e for e in entries if e.eligible]
        logger.info("universe_scan: %d/%d symbols eligible", len(eligible), len(entries))

        semaphore = asyncio.Semaphore(self.config.universe.max_symbols_scanned_concurrently)

        async def bound_run(entry) -> None:
            async with semaphore:
                await self.run_cycle(entry.symbol, entry.spec)

        await asyncio.gather(*(bound_run(e) for e in eligible))

    async def _scan_loop(self) -> None:
        while True:
            if not self.kill_switch.halt_new_positions:
                await self.scan_universe_once()
            await asyncio.sleep(self.config.universe.refresh_interval_seconds)

    async def run_forever(self) -> None:
        await asyncio.gather(self._scan_loop(), self.position_monitor_loop())
