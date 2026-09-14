"""CLI entrypoint (spec section 42-43: backtest / paper / live modes).

    python -m tradingbot.main backtest --data-dir ./data/historical
    python -m tradingbot.main paper
    python -m tradingbot.main live --i-understand-live-risk

`paper` is the default posture: it is the only mode that runs without any
extra confirmation flag. `live` refuses to start unless
`--i-understand-live-risk` is passed AND `config.mode == "live"` in the
loaded config file, so a stray CLI invocation can never accidentally place
real orders (spec section 43).
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import sys
from pathlib import Path

from tradingbot.config import load_config, load_secrets
from tradingbot.data.exchange_client import ExchangeClient
from tradingbot.data.models import Candle, ContractSpec, ContractStatus, MarginMode, PositionMode
from tradingbot.execution.live_broker import LiveBroker
from tradingbot.execution.paper_broker import PaperBroker
from tradingbot.risk.limits import RiskEngine
from tradingbot.scanner.scanner import Scanner
from tradingbot.setups.registry import default_setups
from tradingbot.storage.db import Repository


def _configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s %(message)s")


def _default_spec(symbol: str, exchange_id: str) -> ContractSpec:
    """Conservative fallback contract spec for historical backtests where a
    live exchange connection to fetch real specs isn't available. Real
    live/paper runs always use `ExchangeClient.fetch_contract_specs`
    instead -- this is a backtest-only convenience."""
    base = symbol.split("/")[0]
    return ContractSpec(
        symbol=symbol, base=base, quote="USDT", settle="USDT", exchange_id=exchange_id,
        status=ContractStatus.TRADING, tick_size=0.0001, lot_size=0.001, min_order_qty=0.001,
        max_order_qty=None, min_notional=5.0, price_precision=4, qty_precision=3, max_leverage=20.0,
        funding_interval_hours=8.0, margin_mode=MarginMode.ISOLATED, position_mode=PositionMode.ONE_WAY,
        is_coin_margined=False, maker_fee_bps=2.0, taker_fee_bps=5.0,
    )


def _load_candles_csv(path: Path, symbol: str) -> list[Candle]:
    candles = []
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            candles.append(
                Candle(
                    symbol=symbol, timeframe="1m", exchange_ts_ms=int(row["timestamp"]), local_ts_ms=int(row["timestamp"]),
                    open=float(row["open"]), high=float(row["high"]), low=float(row["low"]), close=float(row["close"]),
                    volume=float(row["volume"]), quote_volume=float(row["volume"]) * float(row["close"]),
                )
            )
    return sorted(candles, key=lambda c: c.exchange_ts_ms)


def cmd_backtest(args: argparse.Namespace) -> None:
    from tradingbot.backtest.engine import BacktestConfig, BacktestEngine
    from tradingbot.backtest.metrics import breakdown_by_exit_reason, breakdown_by_setup, breakdown_by_symbol, summarize
    from tradingbot.backtest.monte_carlo import run_monte_carlo

    config = load_config(args.config)
    _configure_logging(config.logging.level)

    data_dir = Path(args.data_dir)
    csv_files = sorted(data_dir.glob("*.csv"))
    if not csv_files:
        print(f"No CSV files found in {data_dir}", file=sys.stderr)
        sys.exit(1)

    candles_by_symbol: dict[str, list[Candle]] = {}
    specs_by_symbol: dict[str, ContractSpec] = {}
    for path in csv_files:
        symbol = f"{path.stem.upper()}/USDT:USDT"
        candles_by_symbol[symbol] = _load_candles_csv(path, symbol)
        specs_by_symbol[symbol] = _default_spec(symbol, config.exchange.id)

    bt_config = BacktestConfig(
        starting_equity=args.starting_equity,
        risk_per_trade_pct=config.risk.risk_per_trade_pct,
        max_position_leverage=config.risk.max_position_leverage,
        min_liquidation_distance_multiple_of_stop=config.risk.min_liquidation_distance_multiple_of_stop,
        min_expected_value_bps=config.expectancy.min_expected_value_bps,
        min_reward_to_risk=config.expectancy.min_reward_to_risk,
        min_win_probability=config.expectancy.min_win_probability,
    )
    engine = BacktestEngine(bt_config, default_setups(), RiskEngine(config.risk))
    result = engine.run(candles_by_symbol, specs_by_symbol)

    summary = summarize(result.trades, bt_config.starting_equity)
    print(f"\n=== Backtest summary ({len(result.trades)} trades, {len(result.rejected)} rejected) ===")
    print(f"Final equity: {result.final_equity:,.2f} (start {bt_config.starting_equity:,.2f})")
    print(f"Win rate: {summary.win_rate:.1%}  Profit factor: {summary.profit_factor:.2f}  Expectancy: {summary.expectancy_bps:+.1f}bps")
    print(f"Max drawdown: {summary.max_drawdown_pct:.2f}%  Avg holding: {summary.avg_holding_seconds:.0f}s")
    print("\nBy symbol:")
    for symbol, s in breakdown_by_symbol(result.trades).items():
        print(f"  {symbol}: n={s.trade_count} win_rate={s.win_rate:.1%} expectancy={s.expectancy_bps:+.1f}bps pnl={s.total_pnl_quote:+.2f}")
    print("\nBy setup:")
    for setup, s in breakdown_by_setup(result.trades).items():
        print(f"  {setup}: n={s.trade_count} win_rate={s.win_rate:.1%} expectancy={s.expectancy_bps:+.1f}bps pnl={s.total_pnl_quote:+.2f}")
    print("\nExit reasons:", breakdown_by_exit_reason(result.trades))

    if result.trades:
        mc = run_monte_carlo([t.pnl_bps_of_notional for t in result.trades], bt_config.starting_equity)
        print(f"\nMonte Carlo ({mc.n_simulations} sims): median_final={mc.median_final_equity:,.2f} "
              f"p5={mc.p5_final_equity:,.2f} p95={mc.p95_final_equity:,.2f} "
              f"worst_drawdown={mc.worst_case_drawdown_pct:.1f}% prob_ruin={mc.probability_of_ruin:.1%}")


async def _run_paper_or_live(config, mode: str, confirm_live: bool) -> None:
    secrets = load_secrets()
    client = ExchangeClient(
        config.exchange.id,
        api_key=secrets.exchange_api_key,
        api_secret=secrets.exchange_api_secret,
        sandbox=config.exchange.sandbox,
        rate_limit_ms=config.exchange.rate_limit_ms,
    )
    repository = Repository(config.database.url)
    try:
        specs = await client.fetch_contract_specs()
        specs_by_symbol = {s.symbol: s for s in specs}

        if mode == "live":
            broker = LiveBroker(client, confirm_live=confirm_live)
        else:
            broker = PaperBroker(client, specs_by_symbol)

        scanner = Scanner(config, client, default_setups(), RiskEngine(config.risk), broker, repository, mode)
        await scanner.run_forever()
    finally:
        await client.close()


def cmd_paper(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    _configure_logging(config.logging.level)
    asyncio.run(_run_paper_or_live(config, "paper", confirm_live=False))


def cmd_live(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    _configure_logging(config.logging.level)
    if config.mode != "live" or not args.i_understand_live_risk:
        print(
            "Refusing to start live trading: pass --i-understand-live-risk AND set mode: live "
            "in the config file. This is a deliberate double confirmation (spec section 43).",
            file=sys.stderr,
        )
        sys.exit(1)
    asyncio.run(_run_paper_or_live(config, "live", confirm_live=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tradingbot")
    parser.add_argument("--config", default="config/config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    p_backtest = sub.add_parser("backtest", help="Run the event-driven backtester over local CSV history")
    p_backtest.add_argument("--data-dir", required=True, help="Directory of <symbol>.csv files (timestamp,open,high,low,close,volume)")
    p_backtest.add_argument("--starting-equity", type=float, default=10_000.0)
    p_backtest.set_defaults(func=cmd_backtest)

    p_paper = sub.add_parser("paper", help="Run continuous paper trading against live market data")
    p_paper.set_defaults(func=cmd_paper)

    p_live = sub.add_parser("live", help="Run continuous LIVE trading with real orders")
    p_live.add_argument("--i-understand-live-risk", action="store_true")
    p_live.set_defaults(func=cmd_live)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
