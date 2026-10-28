"""Data-quality checks for research time series.

Each check returns a structured `QualityReport` instead of raising, so the
caller decides what is fatal. Research code must refuse to evaluate a
hypothesis on a window whose report has `ok == False` for a field the
hypothesis depends on.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd


@dataclass(slots=True)
class QualityReport:
    name: str
    rows: int
    start_ms: int | None
    end_ms: int | None
    expected_step_ms: int | None
    duplicates: int = 0
    non_monotonic: int = 0
    missing_steps: int = 0
    largest_gap_ms: int = 0
    gap_list: list[tuple[int, int]] = field(default_factory=list)  # (gap_start_ts, gap_ms), largest first
    ohlc_violations: int = 0
    non_positive_prices: int = 0
    negative_volume: int = 0
    taker_exceeds_volume: int = 0
    nan_values: int = 0
    return_outliers: int = 0
    max_missing_fraction: float = 0.001

    @property
    def coverage(self) -> float:
        if not self.expected_step_ms or self.rows == 0 or self.start_ms is None or self.end_ms is None:
            return 1.0
        expected = (self.end_ms - self.start_ms) // self.expected_step_ms + 1
        return min(1.0, self.rows / expected) if expected > 0 else 1.0

    @property
    def ok(self) -> bool:
        return (
            self.rows > 0
            and self.duplicates == 0
            and self.non_monotonic == 0
            and self.ohlc_violations == 0
            and self.non_positive_prices == 0
            and self.negative_volume == 0
            and self.taker_exceeds_volume == 0
            and (1.0 - self.coverage) <= self.max_missing_fraction
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["gap_list"] = d["gap_list"][:10]
        d["coverage"] = self.coverage
        d["ok"] = self.ok
        return d


def check_timeseries(df: pd.DataFrame, name: str, expected_step_ms: int | None, ts_col: str = "ts",
                     max_missing_fraction: float = 0.001) -> QualityReport:
    rep = QualityReport(
        name=name,
        rows=len(df),
        start_ms=int(df[ts_col].iloc[0]) if len(df) else None,
        end_ms=int(df[ts_col].iloc[-1]) if len(df) else None,
        expected_step_ms=expected_step_ms,
        max_missing_fraction=max_missing_fraction,
    )
    if len(df) == 0:
        return rep
    ts = df[ts_col].to_numpy(dtype="int64")
    rep.duplicates = int(pd.Series(ts).duplicated().sum())
    diffs = np.diff(ts)
    rep.non_monotonic = int((diffs < 0).sum())
    rep.nan_values = int(df.isna().sum().sum())
    if expected_step_ms:
        pos = diffs[diffs > 0]
        rep.missing_steps = int(((pos // expected_step_ms) - 1).clip(min=0).sum())
        big = np.where(diffs > expected_step_ms)[0]
        if len(big):
            rep.largest_gap_ms = int(diffs[big].max())
            order = big[np.argsort(-diffs[big])]
            rep.gap_list = [(int(ts[i]), int(diffs[i])) for i in order[:50]]
    return rep


def check_ohlcv(df: pd.DataFrame, name: str, expected_step_ms: int = 60_000,
                outlier_sigma: float = 25.0, prices_must_be_positive: bool = True) -> QualityReport:
    """`prices_must_be_positive=False` for premium-index klines, which are
    signed basis values, not prices."""
    rep = check_timeseries(df, name, expected_step_ms)
    if len(df) == 0:
        return rep
    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    tol = 1e-12 * np.maximum(np.abs(h), 1.0)
    rep.ohlc_violations = int(((h + tol < np.maximum(o, c)) | (l - tol > np.minimum(o, c)) | (h + tol < l)).sum())
    if prices_must_be_positive:
        rep.non_positive_prices = int(((o <= 0) | (h <= 0) | (l <= 0) | (c <= 0)).sum())
        r = np.diff(np.log(c))
        if len(r) > 10:
            mad = np.median(np.abs(r - np.median(r))) * 1.4826
            if mad > 0:
                rep.return_outliers = int((np.abs(r) > outlier_sigma * mad).sum())
    if "volume" in df.columns:
        rep.negative_volume = int((df["volume"] < 0).sum())
        if "taker_buy_volume" in df.columns:
            rep.taker_exceeds_volume = int((df["taker_buy_volume"] > df["volume"] * (1 + 1e-9) + 1e-12).sum())
    return rep


def check_funding(df: pd.DataFrame, name: str, abs_rate_limit: float = 0.03) -> QualityReport:
    """Funding settles on a schedule that can change (8h -> 4h for some
    contracts), so no fixed step is enforced; we flag absurd rates instead."""
    rep = check_timeseries(df, name, expected_step_ms=None)
    if len(df):
        rep.return_outliers = int((df["funding_rate"].abs() > abs_rate_limit).sum())
    return rep
