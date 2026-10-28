"""Point-in-time aligned research panel.

Every row is keyed by the time at which its information became *available*
(`avail_ts`, epoch ms), never by when the underlying interval started. This
is the single convention that prevents look-ahead across the whole research
layer:

- 1m kline opening at t is available at t + 60s (its close).
- Premium-index kline: same as klines.
- Open-interest metrics stamped `create_time` are treated as available one
  full 5m period later. Binance does not document whether the stamp is the
  start or end of the measurement window; assuming the later time can only
  cost a little signal freshness, assuming the earlier one could leak.
- Funding settled at `calc_time` is known from `calc_time`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from tradingbot.data_ingestion.binance_vision import load_series
from tradingbot.data_quality.checks import QualityReport, check_funding, check_ohlcv, check_timeseries

MIN_MS = 60_000
METRICS_AVAIL_LAG_MS = 5 * MIN_MS


@dataclass(slots=True)
class SymbolData:
    symbol: str
    m1: pd.DataFrame        # index avail_ts; open, high, low, close, volume, quote_volume, taker_buy_quote_volume, premium
    funding: pd.DataFrame   # ts, funding_rate (settlements)
    metrics: pd.DataFrame | None  # index avail_ts; oi, oi_value, taker_ls_ratio, ...
    quality: list[QualityReport]


def load_symbol(root: Path | str, symbol: str, with_metrics: bool = True) -> SymbolData:
    reports: list[QualityReport] = []
    k = load_series(root, "futures/um", "klines", symbol, "1m")
    reports.append(check_ohlcv(k, f"{symbol} perp 1m klines"))
    prem = load_series(root, "futures/um", "premiumIndexKlines", symbol, "1m")
    reports.append(check_ohlcv(prem, f"{symbol} premium 1m", prices_must_be_positive=False))
    fund = load_series(root, "futures/um", "fundingRate", symbol)[["ts", "funding_rate"]]
    reports.append(check_funding(fund, f"{symbol} funding"))

    m1 = k[["ts", "open", "high", "low", "close", "volume", "quote_volume", "taker_buy_quote_volume"]].copy()
    m1 = m1.merge(prem[["ts", "close"]].rename(columns={"close": "premium"}), on="ts", how="left")
    m1["avail_ts"] = m1["ts"] + MIN_MS
    m1 = m1.drop(columns="ts").set_index("avail_ts")

    metrics = None
    if with_metrics:
        try:
            mt = load_series(root, "futures/um", "metrics", symbol)
            reports.append(check_timeseries(mt, f"{symbol} metrics 5m", 5 * MIN_MS, max_missing_fraction=0.02))
            mt = mt.rename(columns={
                "sum_open_interest": "oi",
                "sum_open_interest_value": "oi_value",
                "sum_taker_long_short_vol_ratio": "taker_ls_ratio",
                "count_long_short_ratio": "ls_ratio",
            })
            mt["avail_ts"] = mt["ts"] + METRICS_AVAIL_LAG_MS
            metrics = mt.drop(columns="ts").set_index("avail_ts")
            metrics = metrics[~metrics.index.duplicated(keep="last")]
        except FileNotFoundError:
            metrics = None
    return SymbolData(symbol, m1, fund.reset_index(drop=True), metrics, reports)


def resample_bars(m1: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Aggregates 1m rows into `minutes` bars keyed by availability time.

    A bar is only emitted when *all* of its constituent minutes exist, so a
    gap never silently produces a short bar whose 'close' is from earlier
    than its key suggests. Output index = close time of the bar."""
    step = minutes * MIN_MS
    bucket = ((m1.index.to_numpy() - 1) // step + 1) * step  # avail_ts rounded up to bar end
    g = m1.groupby(bucket)
    out = pd.DataFrame({
        "open": g["open"].first(),
        "high": g["high"].max(),
        "low": g["low"].min(),
        "close": g["close"].last(),
        "volume": g["volume"].sum(),
        "quote_volume": g["quote_volume"].sum(),
        "taker_buy_quote_volume": g["taker_buy_quote_volume"].sum(),
        "premium": g["premium"].mean(),
        "n": g["close"].size(),
    })
    out = out[out["n"] == minutes].drop(columns="n")
    out.index.name = "avail_ts"
    return out


def asof_join(left_index: pd.Index, right: pd.DataFrame, cols: list[str], max_age_ms: int | None) -> pd.DataFrame:
    """For each time in `left_index`, the most recent right row with
    avail_ts <= time. Values older than `max_age_ms` become NaN (stale data
    must look missing, not current)."""
    r = right[cols].sort_index()
    left = pd.DataFrame({"t": np.asarray(left_index, dtype="int64")})
    rr = r.reset_index().rename(columns={r.index.name or "index": "rt"})
    rr["rt"] = rr["rt"].astype("int64")
    j = pd.merge_asof(left, rr, left_on="t", right_on="rt", direction="backward")
    if max_age_ms is not None:
        stale = (j["t"] - j["rt"]) > max_age_ms
        j.loc[stale, cols] = np.nan
    j.index = left_index
    return j[cols]
