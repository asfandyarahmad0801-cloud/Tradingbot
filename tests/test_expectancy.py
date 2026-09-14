from __future__ import annotations

from tradingbot.data.models import FundingRate, Side
from tradingbot.features.derivatives_features import estimate_funding_cost_bps
from tradingbot.setups.base import Signal, TakeProfitLevel
from tradingbot.signal_engine.expectancy import CostBreakdown, compute_expectancy, win_probability_from_confidence


def _signal(entry=100.0, stop=99.0, r_multiples=((1.0, 0.5), (2.0, 0.5))) -> Signal:
    return Signal(
        symbol="TEST/USDT:USDT", setup_name="unit_test", direction=Side.LONG, entry_price=entry, stop_price=stop,
        take_profit_levels=tuple(TakeProfitLevel(r, f) for r, f in r_multiples), max_holding_seconds=300, confidence=70.0,
    )


def test_expected_value_positive_case():
    signal = _signal()
    costs = CostBreakdown(5.0, 5.0, 3.0, 3.0, 0.0, 2.0)
    result = compute_expectancy(signal, win_probability=0.5, costs=costs)
    # risk_bps = 100bps (1/100), reward_bps = 1.5 * 100 = 150bps
    assert abs(result.risk_bps - 100.0) < 1e-6
    assert abs(result.reward_bps - 150.0) < 1e-6
    expected_ev = 0.5 * 150 - 0.5 * 100 - costs.total_bps
    assert abs(result.expected_value_bps - expected_ev) < 1e-6


def test_expectancy_fails_when_costs_dominate_small_move():
    signal = _signal(entry=100.0, stop=99.9, r_multiples=((1.0, 1.0),))  # tiny 10bps risk
    costs = CostBreakdown(5.0, 5.0, 3.0, 3.0, 0.0, 2.0)  # 18bps of costs, larger than the whole move
    result = compute_expectancy(signal, win_probability=0.6, costs=costs)
    assert not result.passes(min_ev_bps=5.0, min_reward_to_risk=1.0, min_win_probability=0.3)


def test_win_probability_from_confidence_is_bounded_and_monotonic():
    low = win_probability_from_confidence(0)
    mid = win_probability_from_confidence(50)
    high = win_probability_from_confidence(100)
    assert low < mid < high
    assert 0.0 < low
    assert high < 1.0


def test_funding_cost_not_charged_if_position_closes_before_next_funding():
    funding = FundingRate(symbol="X", exchange_ts_ms=0, local_ts_ms=0, rate=0.001, next_funding_ts_ms=1_000_000, interval_hours=8.0)
    cost = estimate_funding_cost_bps(funding, position_open_ts_ms=0, expected_close_ts_ms=999_999)
    assert cost == 0.0


def test_funding_cost_charged_once_if_position_spans_one_funding_timestamp():
    funding = FundingRate(symbol="X", exchange_ts_ms=0, local_ts_ms=0, rate=0.001, next_funding_ts_ms=1_000_000, interval_hours=8.0)
    cost = estimate_funding_cost_bps(funding, position_open_ts_ms=0, expected_close_ts_ms=1_000_001)
    assert abs(cost - 0.001 * 10_000) < 1e-9


def test_funding_cost_charged_multiple_times_for_long_holding_span():
    interval_ms = 8 * 3600 * 1000
    funding = FundingRate(symbol="X", exchange_ts_ms=0, local_ts_ms=0, rate=0.001, next_funding_ts_ms=interval_ms, interval_hours=8.0)
    # closes 2.5 intervals past the first funding timestamp -> 3 payments total
    cost = estimate_funding_cost_bps(funding, position_open_ts_ms=0, expected_close_ts_ms=interval_ms + int(2.5 * interval_ms))
    assert abs(cost - 0.001 * 10_000 * 3) < 1e-6
