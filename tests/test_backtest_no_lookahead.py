from __future__ import annotations

from tradingbot.backtest.engine import BacktestConfig, BacktestEngine
from tradingbot.risk.limits import RiskEngine
from tradingbot.config import RiskConfig
from tradingbot.setups.registry import default_setups
from tests.conftest import make_spec, make_trending_candles


def _config() -> BacktestConfig:
    return BacktestConfig(starting_equity=10_000.0, min_win_probability=0.0, min_expected_value_bps=-1e9, min_reward_to_risk=0.0)


def test_truncating_future_data_does_not_change_earlier_trades():
    symbol = "TEST/USDT:USDT"
    candles = make_trending_candles(symbol=symbol, n=400, drift_per_bar=0.2, noise_amp=0.05, seed=3)
    truncate_at = 250

    # Full series vs. a series truncated partway through -- everything up to
    # `truncate_at` is byte-identical in both, so if the engine ever peeked
    # ahead, trades opened before that point would differ between the runs.
    full_series = candles
    truncated_series = candles[:truncate_at]

    spec = make_spec(symbol)
    setups = default_setups()

    engine_full = BacktestEngine(_config(), setups, RiskEngine(RiskConfig()))
    result_full = engine_full.run({symbol: full_series}, {symbol: spec})

    engine_trunc = BacktestEngine(_config(), setups, RiskEngine(RiskConfig()))
    result_trunc = engine_trunc.run({symbol: truncated_series}, {symbol: spec})

    cutoff_ts = candles[truncate_at - 1].exchange_ts_ms

    trades_full_before_cutoff = [t for t in result_full.trades if t.entry_ts_ms <= cutoff_ts]
    trades_trunc_before_cutoff = [t for t in result_trunc.trades if t.entry_ts_ms <= cutoff_ts]

    assert len(trades_full_before_cutoff) == len(trades_trunc_before_cutoff)
    for a, b in zip(trades_full_before_cutoff, trades_trunc_before_cutoff):
        assert a.entry_ts_ms == b.entry_ts_ms
        assert a.symbol == b.symbol
        assert a.setup_name == b.setup_name
        assert a.direction == b.direction
        assert abs(a.entry_price - b.entry_price) < 1e-9


def test_backtest_produces_no_trades_when_expectancy_threshold_is_impossible():
    symbol = "TEST/USDT:USDT"
    candles = make_trending_candles(symbol=symbol, n=200, drift_per_bar=0.2, noise_amp=0.05, seed=3)
    spec = make_spec(symbol)
    cfg = BacktestConfig(starting_equity=10_000.0, min_expected_value_bps=1e9)  # impossible threshold
    engine = BacktestEngine(cfg, default_setups(), RiskEngine(RiskConfig()))
    result = engine.run({symbol: candles}, {symbol: spec})
    assert result.trades == []
