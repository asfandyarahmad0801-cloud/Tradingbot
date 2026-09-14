from __future__ import annotations

from tradingbot.data.models import Side
from tradingbot.risk.leverage import estimate_liquidation_price, liquidation_distance_pct, select_leverage
from tests.conftest import make_spec


def test_liquidation_price_long_below_entry():
    entry = 100.0
    liq = estimate_liquidation_price(entry, Side.LONG, leverage=10.0, maintenance_margin_rate=0.005)
    assert liq < entry
    # 1/leverage - mmr = 0.1 - 0.005 = 0.095
    assert abs(liq - entry * (1 - 0.095)) < 1e-9


def test_liquidation_price_short_above_entry():
    entry = 100.0
    liq = estimate_liquidation_price(entry, Side.SHORT, leverage=10.0, maintenance_margin_rate=0.005)
    assert liq > entry
    assert abs(liq - entry * (1 + 0.095)) < 1e-9


def test_higher_leverage_moves_liquidation_closer():
    entry = 100.0
    liq_low = estimate_liquidation_price(entry, Side.LONG, leverage=2.0)
    liq_high = estimate_liquidation_price(entry, Side.LONG, leverage=20.0)
    assert liquidation_distance_pct(entry, liq_high) < liquidation_distance_pct(entry, liq_low)


def test_select_leverage_respects_liquidation_distance_multiple():
    spec = make_spec(max_leverage=50.0)
    entry, stop = 100.0, 99.0  # 1% stop distance
    decision = select_leverage(
        entry, stop, Side.LONG, spec,
        max_position_leverage_config=50.0,
        min_liquidation_distance_multiple_of_stop=3.0,
    )
    assert not decision.rejected
    assert decision.liquidation_distance_multiple_of_stop >= 3.0
    # Liquidation must sit below the stop for a long.
    assert decision.liquidation_price < stop


def test_select_leverage_rejects_when_stop_too_wide_for_any_leverage():
    # Counterintuitively, a WIDE stop is what makes the safety multiple hard
    # to satisfy: liquidation distance shrinks monotonically as leverage
    # decreases only down to 1/leverage ~ 2x at the leverage floor, so an
    # extremely wide stop (here 80% of price) can exceed even the safest
    # liquidation distance available at the leverage floor.
    spec = make_spec(max_leverage=125.0)
    entry, stop = 100.0, 20.0
    decision = select_leverage(
        entry, stop, Side.LONG, spec,
        max_position_leverage_config=125.0,
        min_liquidation_distance_multiple_of_stop=3.0,
        leverage_step=0.5,
    )
    assert decision.rejected


def test_select_leverage_never_exceeds_configured_or_exchange_cap():
    spec = make_spec(max_leverage=5.0)
    entry, stop = 100.0, 95.0  # wide stop, leverage should be capped by spec, not by stop distance
    decision = select_leverage(
        entry, stop, Side.LONG, spec,
        max_position_leverage_config=10.0,   # config allows more than exchange max
        min_liquidation_distance_multiple_of_stop=1.0,
    )
    assert decision.leverage <= 5.0


def test_select_leverage_scales_down_with_volatility_and_event_multipliers():
    spec = make_spec(max_leverage=20.0)
    entry, stop = 100.0, 98.0
    normal = select_leverage(entry, stop, Side.LONG, spec, 20.0, 1.0, volatility_multiplier=1.0, event_window_multiplier=1.0)
    reduced = select_leverage(entry, stop, Side.LONG, spec, 20.0, 1.0, volatility_multiplier=0.5, event_window_multiplier=0.5)
    assert reduced.leverage <= normal.leverage
