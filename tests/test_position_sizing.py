from __future__ import annotations

from tradingbot.data.models import Side
from tradingbot.risk.position_sizing import compute_position_size, worst_case_loss_with_slippage
from tests.conftest import make_spec


def test_position_size_matches_risk_budget():
    spec = make_spec()
    equity = 10_000.0
    risk_pct = 1.0  # risk $100
    entry, stop = 100.0, 99.0  # $1 stop distance
    result = compute_position_size(equity, risk_pct, entry, stop, leverage=5.0, spec=spec, max_notional_usd=1_000_000)
    assert not result.rejected
    # qty * stop_distance should approximate the risk budget (within lot-size rounding)
    implied_risk = result.qty * abs(entry - stop)
    assert abs(implied_risk - 100.0) < 100.0 * 0.05  # within 5% due to lot rounding


def test_position_size_rejected_below_min_order_qty():
    spec = make_spec()
    # risk_amount = 10 * 0.001 / 100 = 0.0001; stop_distance = 1.0 -> qty_raw
    # = 0.0001, which rounds down to 0 at lot_size=0.001 -> below min_order_qty.
    result = compute_position_size(
        equity=10.0, risk_pct=0.001, entry_price=100.0, stop_price=99.0, leverage=5.0,
        spec=spec, max_notional_usd=1_000_000,
    )
    assert result.rejected


def test_position_size_capped_by_max_notional():
    spec = make_spec()
    result = compute_position_size(
        equity=1_000_000.0, risk_pct=5.0, entry_price=100.0, stop_price=99.0, leverage=10.0,
        spec=spec, max_notional_usd=5_000.0,
    )
    assert not result.rejected
    assert result.notional <= 5_000.0 * 1.01


def test_position_size_rejects_invalid_stop():
    spec = make_spec()
    result = compute_position_size(10_000, 1.0, 100.0, 100.0, 5.0, spec, 1_000_000)
    assert result.rejected


def test_worst_case_loss_with_slippage_exceeds_naive_risk():
    qty = 10.0
    entry, stop = 100.0, 99.0
    naive_risk = qty * (entry - stop)
    worst = worst_case_loss_with_slippage(qty, entry, stop, Side.LONG, extra_slippage_bps=20.0)
    assert worst > naive_risk
