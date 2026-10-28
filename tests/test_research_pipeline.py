"""Tests for the research layer: provenance parsing, point-in-time alignment,
cost/funding accounting, statistics, and -- most importantly -- that the
protocol does not manufacture edges from noise but does detect a planted one."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradingbot.data_ingestion.binance_vision import ArchiveFile, parse_archive_csv
from tradingbot.data_quality.checks import check_ohlcv
from tradingbot.research.costs import CostModel
from tradingbot.research.dataset import MIN_MS, SymbolData, asof_join, resample_bars
from tradingbot.research.evaluate import forward_table, random_timing_null, simulate_trades, summarize
from tradingbot.research.features import build_features
from tradingbot.research.registry import Registry
from tradingbot.research.stats import bh_fdr, block_bootstrap_mean_ci, newey_west_tstat

T0 = 1_700_000_100_000  # a 5-minute boundary


def make_symbol(n_min: int, seed: int = 0, drift_fn=None, symbol: str = "TESTUSDT",
                funding_rate: float = 0.0) -> SymbolData:
    rng = np.random.default_rng(seed)
    r = rng.normal(0, 5e-4, n_min)
    if drift_fn is not None:
        r = r + drift_fn(r)
    close = 100 * np.exp(np.cumsum(r))
    open_ = np.concatenate([[100.0], close[:-1]])
    hi = np.maximum(open_, close) * (1 + 1e-4)
    lo = np.minimum(open_, close) * (1 - 1e-4)
    qv = np.full(n_min, 1e6)
    idx = pd.Index(T0 + MIN_MS * np.arange(1, n_min + 1), name="avail_ts")
    m1 = pd.DataFrame({"open": open_, "high": hi, "low": lo, "close": close, "volume": qv / close,
                       "quote_volume": qv, "taker_buy_quote_volume": qv * rng.uniform(0.3, 0.7, n_min),
                       "premium": rng.normal(0, 1e-4, n_min)}, index=idx)
    fts = np.arange(T0, T0 + n_min * MIN_MS, 480 * MIN_MS)
    funding = pd.DataFrame({"ts": fts, "funding_rate": np.full(len(fts), funding_rate)})
    return SymbolData(symbol, m1, funding, None, [])


# --- ingestion -------------------------------------------------------------

def test_archive_url_layout():
    f = ArchiveFile("futures/um", "klines", "BTCUSDT", "2024-01", "1m")
    assert f.url == "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01.zip"
    g = ArchiveFile("futures/um", "metrics", "BTCUSDT", "2024-01-02")
    assert g.url.endswith("/daily/metrics/BTCUSDT/BTCUSDT-metrics-2024-01-02.zip")


def test_parse_headerless_and_microsecond_klines():
    raw = (b"1735689600000000,1,2,0.5,1.5,10,1735689659999999,15,3,4,6,0\n"
           b"1735689660000000,1.5,2,1,1.8,10,1735689719999999,15,3,4,6,0\n")
    df = parse_archive_csv("klines", raw)
    assert df["ts"].tolist() == [1735689600000, 1735689660000]
    assert "ignore" not in df.columns


def test_parse_metrics_timestamps_are_ms():
    raw = (b"create_time,symbol,sum_open_interest,sum_open_interest_value\n"
           b"2026-10-20 00:05:00,BTCUSDT,1,2\n2026-10-20 00:00:00,BTCUSDT,1,2\n")
    df = parse_archive_csv("metrics", raw)
    assert df["ts"].tolist() == [1792454400000, 1792454700000]  # sorted, milliseconds


# --- data quality ------------------------------------------------------------

def test_quality_detects_gap_duplicate_and_bad_ohlc():
    df = pd.DataFrame({"ts": [0, 60_000, 60_000, 240_000], "open": [1, 1, 1, 1], "high": [1.1, 1.1, 1.1, 0.9],
                       "low": [0.9, 0.9, 0.9, 0.8], "close": [1, 1, 1, 0.85], "volume": [1, 1, 1, 1]})
    rep = check_ohlcv(df, "x")
    assert rep.duplicates == 1 and rep.missing_steps == 2 and rep.ohlc_violations == 1
    assert not rep.ok


# --- point-in-time alignment ------------------------------------------------

def test_resample_drops_incomplete_bars_and_keys_by_close_time():
    sd = make_symbol(20)
    m1 = sd.m1.drop(sd.m1.index[7])  # bar 2 (minutes 6-10) now incomplete
    bars = resample_bars(m1, 5)
    first_key = bars.index[0]
    assert first_key % (5 * MIN_MS) == 0 and first_key == T0 + 5 * MIN_MS
    assert bars.loc[first_key, "close"] == m1.loc[first_key, "close"]
    assert len(bars) == len(resample_bars(sd.m1, 5)) - 1


def test_asof_join_never_uses_future_and_marks_stale():
    right = pd.DataFrame({"v": [1.0, 2.0]}, index=pd.Index([100, 200], name="avail_ts"))
    out = asof_join(pd.Index([99, 100, 150, 200, 1000]), right, ["v"], max_age_ms=300)
    assert np.isnan(out["v"].iloc[0])
    assert out["v"].tolist()[1:4] == [1.0, 1.0, 2.0]
    assert np.isnan(out["v"].iloc[4])  # 800ms old > 300ms


def test_features_are_causal_under_truncation():
    sd = make_symbol(20_000, seed=3)
    full = build_features(sd, norm_days=3, min_norm_days=1)
    cut = 15_000
    sd_cut = SymbolData(sd.symbol, sd.m1.iloc[:cut], sd.funding, None, [])
    part = build_features(sd_cut, norm_days=3, min_norm_days=1)
    common = part.index[:-1]
    cols = [c for c in part.columns if c != "valid"]
    pd.testing.assert_frame_equal(full.loc[common, cols], part.loc[common, cols], check_exact=False, rtol=1e-9)


# --- execution / cost accounting --------------------------------------------

def test_trade_accounting_delay_costs_and_funding_sign():
    sd = make_symbol(3000, funding_rate=0.001)
    dec = np.array([T0 + 100 * MIN_MS])
    ft = forward_table(sd, dec, horizon_min=600, delay_min=1)
    entry = sd.m1["close"].loc[T0 + 101 * MIN_MS]
    exitp = sd.m1["close"].loc[T0 + 701 * MIN_MS]
    cost = CostModel()
    rt = cost.round_trip_bps("TESTUSDT")
    # settlement at T0+480min falls inside (entry, exit]
    for side in (1.0, -1.0):
        tr = simulate_trades(np.array([side]), ft, cost, 0, 2**62)
        gross = side * (exitp / entry - 1) * 1e4
        assert tr["gross_bps"].iloc[0] == pytest.approx(gross)
        assert tr["funding_bps"].iloc[0] == pytest.approx(side * 10.0)  # long pays positive funding
        assert tr["net_bps"].iloc[0] == pytest.approx(gross - rt - side * 10.0)


def test_positions_do_not_overlap():
    sd = make_symbol(3000)
    dec = sd.m1.index.to_numpy()[100:400:5]
    ft = forward_table(sd, dec, horizon_min=60)
    tr = simulate_trades(np.ones(len(dec)), ft, CostModel(), 0, 2**62)
    assert (tr["decision_ts"].to_numpy()[1:] >= tr["exit_ts"].to_numpy()[:-1]).all()


def test_maker_bound_is_cheaper_than_taker_and_stress_scales():
    c = CostModel()
    assert c.as_maker().round_trip_bps("BTCUSDT") < c.round_trip_bps("BTCUSDT")
    assert c.stressed(2.0).round_trip_bps("X") == pytest.approx(2 * c.round_trip_bps("X"))


# --- statistics ---------------------------------------------------------------

def test_bh_fdr_known_example():
    rej, adj = bh_fdr([0.01, 0.04, 0.03, 0.5], q=0.05)
    assert rej.tolist() == [True, False, False, False]
    assert adj[0] == pytest.approx(0.04)


def test_newey_west_and_bootstrap_on_iid():
    x = np.random.default_rng(0).normal(1.0, 1.0, 2000)
    t, p = newey_west_tstat(x)
    assert t > 30 and p < 1e-10
    lo, hi = block_bootstrap_mean_ci(x)
    assert lo < 1.0 < hi


def test_random_signals_on_noise_are_not_significant_at_nominal_rate():
    """False-positive control: random signals on random walks must reject the
    null at roughly the nominal rate, not more."""
    sd = make_symbol(60_000, seed=11)
    dec = sd.m1.index.to_numpy()[::5]
    ft = forward_table(sd, dec, horizon_min=60)
    cost = CostModel(taker_fee_bps=0, default_impact_bps=0)
    rejections = 0
    trials = 40
    for seed in range(trials):
        rng = np.random.default_rng(100 + seed)
        sig = rng.choice([-1.0, 0.0, 1.0], size=len(dec), p=[0.02, 0.96, 0.02])
        tr = simulate_trades(sig, ft, cost, 0, 2**62)
        null = random_timing_null(tr, {sd.symbol: ft}, cost, 0, 2**62, n_sims=300, seed=seed)
        s = summarize(tr, int(dec[0]), int(dec[-1]), null)
        rejections += s["p_vs_random_timing"] <= 0.05
    assert rejections <= 6  # nominal 2 of 40; generous bound for 40 Bernoulli draws


def test_planted_edge_is_detected():
    """A genuine (small) predictable component must be found: here returns
    after a large 30m drop partially revert."""
    rng = np.random.default_rng(5)
    n = 80_000
    r = rng.normal(0, 5e-4, n)
    # plant: every 997th minute a 1% shock that reverts by 0.5% over the following hour
    for i in range(500, n - 100, 997):
        r[i] -= 0.01
        r[i + 1:i + 61] += 0.005 / 60
    sd = make_symbol(n, seed=5, drift_fn=lambda base: r - base)
    dec = sd.m1.index.to_numpy()
    close = sd.m1["close"]
    ret30 = np.log(close).diff(30).to_numpy()
    sig = np.where(ret30 < -0.008, 1.0, 0.0)
    ft = forward_table(sd, dec, horizon_min=60)
    cost = CostModel()
    tr = simulate_trades(sig, ft, cost, 0, 2**62)
    null = random_timing_null(tr, {sd.symbol: ft}, cost, 0, 2**62, n_sims=500)
    s = summarize(tr, int(dec[0]), int(dec[-1]), null)
    assert s["n_trades"] >= 40
    assert s["p_vs_random_timing"] < 0.01 and s["mean_gross_bps"] > 15


def test_registry_is_append_only(tmp_path):
    reg = Registry(tmp_path / "r.jsonl")
    reg.append({"hypothesis": "H01", "verdict": "rejected_discovery", "x": np.float64(1.5)})
    reg.append({"hypothesis": "H02", "verdict": "inconclusive"})
    rows = reg.read()
    assert [r["hypothesis"] for r in rows] == ["H01", "H02"] and rows[0]["x"] == 1.5


# --- limit-order entry model ---------------------------------------------------

def _flat_symbol(n: int, lows: dict[int, float], highs: dict[int, float] | None = None) -> SymbolData:
    sd = make_symbol(n)
    m1 = sd.m1.copy()
    m1[["open", "high", "low", "close"]] = 100.0
    for i, v in lows.items():
        m1.iloc[i, m1.columns.get_loc("low")] = v
    for i, v in (highs or {}).items():
        m1.iloc[i, m1.columns.get_loc("high")] = v
    return SymbolData(sd.symbol, m1, sd.funding.assign(funding_rate=0.0), None, [])


def test_limit_touch_does_not_fill_but_trade_through_does():
    from tradingbot.research.evaluate import limit_forward_table
    dec_i = 100
    # decision at bar 100; order live from bar 101; limit = 100 * (1 - 10bps) = 99.9
    touch = _flat_symbol(500, {103: 99.9})
    through = _flat_symbol(500, {103: 99.89})
    dec = np.array([touch.m1.index[dec_i]])
    t1 = limit_forward_table(touch, dec, horizon_min=60, offset_bps=10, window_min=10)
    t2 = limit_forward_table(through, dec, horizon_min=60, offset_bps=10, window_min=10)
    assert np.isnan(t1.gross_long[0])
    assert t2.entry_ts[0] == through.m1.index[103]
    assert t2.gross_long[0] == pytest.approx(100.0 / 99.9 - 1)


def test_limit_fill_outside_window_is_ignored_and_short_side_uses_highs():
    from tradingbot.research.evaluate import limit_forward_table
    sd = _flat_symbol(500, {130: 99.0}, {104: 100.2})
    dec = np.array([sd.m1.index[100]])
    ft = limit_forward_table(sd, dec, horizon_min=60, offset_bps=10, window_min=10)
    assert np.isnan(ft.gross_long[0])                       # low at bar 130 is past the window
    assert ft.for_side(-1).entry_ts[0] == sd.m1.index[104]  # short limit at 100.1 filled by high 100.2


def test_limit_round_trip_cost_is_maker_in_taker_out():
    c = CostModel()
    assert c.round_trip_bps("BTCUSDT", "limit") == pytest.approx(2.0 + 5.0 + 1.0)
