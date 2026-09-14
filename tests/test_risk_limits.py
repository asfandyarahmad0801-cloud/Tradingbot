from __future__ import annotations

from tradingbot.config import RiskConfig
from tradingbot.data.models import Side
from tradingbot.risk.limits import KillSwitch, OpenPositionInfo, PortfolioState, RiskEngine


def _engine(**overrides) -> RiskEngine:
    return RiskEngine(RiskConfig(**overrides))


def test_trade_allowed_when_within_all_limits():
    engine = _engine()
    portfolio = PortfolioState(equity=10_000.0)
    allowed, reasons = engine.check_new_trade(
        portfolio, KillSwitch(), "BTC/USDT:USDT", "binanceusdm", Side.LONG, "momentum", notional=500.0, leverage=2.0, now_ms=0,
    )
    assert allowed
    assert reasons == []


def test_kill_switch_halts_new_positions():
    engine = _engine()
    portfolio = PortfolioState(equity=10_000.0)
    ks = KillSwitch(halt_new_positions=True)
    allowed, reasons = engine.check_new_trade(portfolio, ks, "BTC/USDT:USDT", "binanceusdm", Side.LONG, "momentum", 500.0, 2.0, 0)
    assert not allowed
    assert any("halt" in r for r in reasons)


def test_daily_loss_limit_blocks_new_trades():
    engine = _engine(max_daily_loss_pct=2.0)
    portfolio = PortfolioState(equity=10_000.0, daily_pnl_pct=-2.5)
    allowed, reasons = engine.check_new_trade(portfolio, KillSwitch(), "X", "binanceusdm", Side.LONG, "s", 500.0, 2.0, 0)
    assert not allowed
    assert any("daily_loss_limit" in r for r in reasons)


def test_max_concurrent_positions_enforced():
    engine = _engine(max_concurrent_positions=1)
    portfolio = PortfolioState(equity=10_000.0, open_positions=[OpenPositionInfo("ETH/USDT:USDT", Side.LONG, 1000, 2.0, "s")])
    allowed, reasons = engine.check_new_trade(portfolio, KillSwitch(), "BTC/USDT:USDT", "binanceusdm", Side.SHORT, "s", 500.0, 2.0, 0)
    assert not allowed
    assert any("max_concurrent_positions" in r for r in reasons)


def test_max_positions_per_coin_enforced():
    engine = _engine(max_positions_per_coin=1, max_concurrent_positions=10)
    portfolio = PortfolioState(equity=10_000.0, open_positions=[OpenPositionInfo("BTC/USDT:USDT", Side.LONG, 1000, 2.0, "s")])
    allowed, reasons = engine.check_new_trade(portfolio, KillSwitch(), "BTC/USDT:USDT", "binanceusdm", Side.LONG, "s", 500.0, 2.0, 0)
    assert not allowed


def test_portfolio_exposure_limit_enforced():
    engine = _engine(max_portfolio_exposure_pct=10.0, max_concurrent_positions=99)
    portfolio = PortfolioState(equity=10_000.0)  # 10% cap == $1000 notional
    allowed, reasons = engine.check_new_trade(portfolio, KillSwitch(), "X", "binanceusdm", Side.LONG, "s", notional=2000.0, leverage=1.0, now_ms=0)
    assert not allowed
    assert any("portfolio_exposure" in r for r in reasons)


def test_position_leverage_limit_enforced():
    engine = _engine(max_position_leverage=3.0)
    portfolio = PortfolioState(equity=10_000.0)
    allowed, reasons = engine.check_new_trade(portfolio, KillSwitch(), "X", "binanceusdm", Side.LONG, "s", 500.0, leverage=10.0, now_ms=0)
    assert not allowed
    assert any("position_leverage_exceeds_limit" in r for r in reasons)


def test_cooldown_after_loss_blocks_symbol():
    engine = _engine(cooldown_seconds_after_loss=300)
    portfolio = PortfolioState(equity=10_000.0)
    portfolio.last_loss_ts_ms_by_symbol["X"] = 1_000_000
    allowed, reasons = engine.check_new_trade(portfolio, KillSwitch(), "X", "binanceusdm", Side.LONG, "s", 500.0, 2.0, now_ms=1_000_000 + 60_000)
    assert not allowed
    assert any("cooldown_after_loss" in r for r in reasons)


def test_symbol_specific_kill_switch():
    engine = _engine()
    portfolio = PortfolioState(equity=10_000.0)
    ks = KillSwitch(disabled_symbols={"X"})
    allowed, reasons = engine.check_new_trade(portfolio, ks, "X", "binanceusdm", Side.LONG, "s", 500.0, 2.0, 0)
    assert not allowed


def test_max_trades_per_hour_enforced():
    engine = _engine(max_trades_per_hour=2)
    portfolio = PortfolioState(equity=10_000.0, trade_entry_timestamps_ms=[0, 100, 200])
    allowed, reasons = engine.check_new_trade(portfolio, KillSwitch(), "X", "binanceusdm", Side.LONG, "s", 500.0, 2.0, now_ms=500)
    assert not allowed
    assert any("max_trades_per_hour" in r for r in reasons)
