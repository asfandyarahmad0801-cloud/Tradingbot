"""Causal feature panel on a fixed bar grid.

Every feature at row T uses only rows with avail_ts <= T. Normalisation
(z-scores, percentiles) uses trailing windows only -- there is no
full-sample standardisation anywhere, because that alone leaks the future
distribution into every past signal.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from tradingbot.research.dataset import MIN_MS, SymbolData, asof_join, resample_bars

DAY_MS = 24 * 60 * MIN_MS


def _rolling_z(x: pd.Series, window: int, min_periods: int) -> pd.Series:
    m = x.rolling(window, min_periods=min_periods).mean()
    s = x.rolling(window, min_periods=min_periods).std()
    return (x - m) / s.replace(0.0, np.nan)


def _rolling_pct_rank(x: pd.Series, window: int, min_periods: int) -> pd.Series:
    """Fraction of the trailing window (incl. current) strictly below the current value."""
    return x.rolling(window, min_periods=min_periods).rank(pct=True)


def build_features(sd: SymbolData, bar_minutes: int = 5, norm_days: int = 30,
                   min_norm_days: int = 7) -> pd.DataFrame:
    bars = resample_bars(sd.m1, bar_minutes)
    # Reindex onto a regular grid so that row-count windows equal time windows.
    step = bar_minutes * MIN_MS
    grid = pd.RangeIndex(int(bars.index[0]), int(bars.index[-1]) + step, step, name="avail_ts")
    b = bars.reindex(grid)
    per_hour = 60 // bar_minutes
    W = norm_days * 24 * per_hour
    MP = min_norm_days * 24 * per_hour

    f = pd.DataFrame(index=grid)
    f["close"] = b["close"]
    f["valid"] = b["close"].notna()
    logc = np.log(b["close"])
    r1 = logc.diff()
    f["ret_bar"] = r1
    sigma_bar = r1.rolling(W, min_periods=MP).std()
    f["sigma_bar"] = sigma_bar
    for name, hours in (("30m", 0.5), ("1h", 1), ("4h", 4), ("24h", 24)):
        n = int(hours * per_hour)
        ret = logc - logc.shift(n)
        f[f"ret_{name}"] = ret
        f[f"ret_{name}_z"] = ret / (sigma_bar * np.sqrt(n))

    # Realised volatility and its trailing percentile (compression detector).
    rv4 = np.sqrt((r1 ** 2).rolling(4 * per_hour, min_periods=4 * per_hour).sum())
    f["rv_4h"] = rv4
    f["rv_4h_pct"] = _rolling_pct_rank(rv4, W, MP)
    hi = b["high"].rolling(4 * per_hour, min_periods=4 * per_hour).max().shift(1)
    lo = b["low"].rolling(4 * per_hour, min_periods=4 * per_hour).min().shift(1)
    f["break_up"] = (b["close"] > hi).astype(float).where(hi.notna())
    f["break_dn"] = (b["close"] < lo).astype(float).where(lo.notna())

    # Aggressor imbalance: share of quote volume from taker buys, centred at 0.
    for name, hours in (("30m", 0.5), ("1h", 1)):
        n = int(hours * per_hour)
        qv = b["quote_volume"].rolling(n, min_periods=n).sum()
        tb = b["taker_buy_quote_volume"].rolling(n, min_periods=n).sum()
        imb = (2 * tb - qv) / qv.replace(0.0, np.nan)
        f[f"imb_{name}"] = imb
        f[f"imb_{name}_z"] = _rolling_z(imb, W, MP)
    vol1h = b["quote_volume"].rolling(per_hour, min_periods=per_hour).sum()
    f["vol_1h_z"] = _rolling_z(np.log(vol1h.replace(0, np.nan)), W, MP)

    # Basis: premium index of perp over spot index (signed fraction).
    prem1h = b["premium"].rolling(per_hour, min_periods=per_hour // 2).mean()
    f["prem_1h"] = prem1h
    f["prem_1h_z"] = _rolling_z(prem1h, W, MP)

    # Last *settled* funding rate, stale after 9h (8h schedule + slack).
    fund = sd.funding.copy()
    fund["avail_ts"] = fund["ts"]
    fj = asof_join(grid, fund.set_index("avail_ts"), ["funding_rate"], max_age_ms=9 * 60 * MIN_MS)
    f["funding"] = fj["funding_rate"]
    f["funding_z"] = _rolling_z(f["funding"], W, MP)

    if sd.metrics is not None:
        mj = asof_join(grid, sd.metrics, ["oi_value", "oi", "taker_ls_ratio", "ls_ratio"], max_age_ms=15 * MIN_MS)
        oi = np.log(mj["oi"].replace(0, np.nan))
        for name, hours in (("15m", 0.25), ("1h", 1), ("4h", 4)):
            n = int(hours * per_hour)
            d = oi - oi.shift(n)
            f[f"doi_{name}"] = d
            f[f"doi_{name}_z"] = _rolling_z(d, W, MP)
        f["ls_ratio"] = mj["ls_ratio"]
        f["ls_ratio_z"] = _rolling_z(np.log(mj["ls_ratio"]), W, MP)

    hour = (grid.to_numpy() // (60 * MIN_MS)) % 24
    f["hour_utc"] = hour
    return f


def add_reference_features(f: pd.DataFrame, ref: pd.DataFrame, prefix: str = "btc_") -> pd.DataFrame:
    """Joins another symbol's (e.g. BTC) features on the identical grid.
    Both frames are keyed by availability time, so a plain index join is causal."""
    cols = ["ret_bar", "ret_30m_z", "ret_1h_z", "ret_4h_z", "sigma_bar"]
    return f.join(ref[cols].add_prefix(prefix), how="left")
