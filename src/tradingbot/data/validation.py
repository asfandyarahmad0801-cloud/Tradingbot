"""Data-quality gates (spec section 40).

Every feed that reaches the setup-detection engine passes through here
first. A symbol with a data-quality failure is excluded from new entries for
that cycle -- existing positions are still managed (see
`risk.limits.KillSwitch` / execution layer), but no new trade is opened on
data we cannot trust. Every failure is returned as a structured
`DataQualityIssue` so it can be logged (never silently dropped).
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from tradingbot.data.models import Candle, OrderBookSnapshot


@dataclass(frozen=True, slots=True)
class DataQualityIssue:
    symbol: str
    check: str
    detail: str
    severity: str  # "warning" | "critical" -- critical blocks new entries


def check_candles(
    symbol: str,
    candles: list[Candle],
    timeframe_seconds: int,
    max_staleness_seconds: float = 30.0,
    outlier_zscore: float = 8.0,
    now_ms: int | None = None,
) -> list[DataQualityIssue]:
    issues: list[DataQualityIssue] = []
    if not candles:
        return [DataQualityIssue(symbol, "missing_data", "no candles returned", "critical")]

    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)

    # Duplicate / out-of-order timestamps.
    seen: set[int] = set()
    prev_ts = None
    for c in candles:
        if c.exchange_ts_ms in seen:
            issues.append(DataQualityIssue(symbol, "duplicate_candle", f"ts={c.exchange_ts_ms}", "critical"))
        seen.add(c.exchange_ts_ms)
        if prev_ts is not None and c.exchange_ts_ms < prev_ts:
            issues.append(DataQualityIssue(symbol, "out_of_order", f"ts={c.exchange_ts_ms} after {prev_ts}", "critical"))
        prev_ts = c.exchange_ts_ms

    # Gaps: consecutive candles should be exactly one timeframe apart.
    step_ms = timeframe_seconds * 1000
    ordered = sorted(candles, key=lambda c: c.exchange_ts_ms)
    for a, b in zip(ordered, ordered[1:]):
        gap = b.exchange_ts_ms - a.exchange_ts_ms
        if gap > step_ms * 1.5:
            missing = round(gap / step_ms) - 1
            issues.append(DataQualityIssue(symbol, "gap", f"{missing} missing candle(s) around ts={a.exchange_ts_ms}", "warning"))

    # Staleness of the most recent candle.
    latest = ordered[-1]
    staleness = (now_ms - latest.exchange_ts_ms) / 1000.0
    if staleness > max_staleness_seconds:
        issues.append(DataQualityIssue(symbol, "stale_data", f"latest candle is {staleness:.1f}s old", "critical"))

    # Sanity: OHLC ordering and non-negative volume.
    for c in ordered:
        if not (c.low <= c.open <= c.high and c.low <= c.close <= c.high and c.low <= c.high):
            issues.append(DataQualityIssue(symbol, "invalid_ohlc", f"ts={c.exchange_ts_ms} o={c.open} h={c.high} l={c.low} c={c.close}", "critical"))
        if c.volume < 0 or c.quote_volume < 0:
            issues.append(DataQualityIssue(symbol, "negative_volume", f"ts={c.exchange_ts_ms}", "critical"))

    # Outlier return detection (simple robust z-score on log returns).
    closes = [c.close for c in ordered if c.close > 0]
    if len(closes) >= 10:
        rets = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / max(len(rets) - 1, 1)
        std = var ** 0.5
        if std > 0:
            for i, r in enumerate(rets):
                z = (r - mean) / std
                if abs(z) > outlier_zscore:
                    issues.append(
                        DataQualityIssue(
                            symbol, "return_outlier", f"z={z:.1f} at ts={ordered[i + 1].exchange_ts_ms}", "warning"
                        )
                    )
    return issues


def check_orderbook(
    symbol: str,
    book: OrderBookSnapshot,
    max_staleness_seconds: float = 5.0,
    now_ms: int | None = None,
) -> list[DataQualityIssue]:
    issues: list[DataQualityIssue] = []
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)

    if not book.bids or not book.asks:
        issues.append(DataQualityIssue(symbol, "empty_book", "no bids or asks", "critical"))
        return issues

    if book.best_bid is not None and book.best_ask is not None and book.best_bid >= book.best_ask:
        issues.append(DataQualityIssue(symbol, "crossed_book", f"bid={book.best_bid} ask={book.best_ask}", "critical"))

    staleness = (now_ms - book.local_ts_ms) / 1000.0
    if staleness > max_staleness_seconds:
        issues.append(DataQualityIssue(symbol, "stale_orderbook", f"{staleness:.2f}s old", "critical"))

    return issues


def has_critical(issues: list[DataQualityIssue]) -> bool:
    return any(i.severity == "critical" for i in issues)
