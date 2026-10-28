"""Statistical tools for honest hypothesis evaluation."""
from __future__ import annotations

import math

import numpy as np
from scipy import stats as sps


def newey_west_tstat(x: np.ndarray, lags: int | None = None) -> tuple[float, float]:
    """t-statistic of the mean with Newey-West (Bartlett) HAC standard error.
    Returns (t, two-sided p). Trade P&L in crypto is serially dependent
    (volatility clustering, regime persistence) so i.i.d. errors overstate t."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 3:
        return float("nan"), float("nan")
    if lags is None:
        lags = int(math.floor(4 * (n / 100.0) ** (2.0 / 9.0)))
    e = x - x.mean()
    lrv = e @ e / n
    for k in range(1, min(lags, n - 1) + 1):
        w = 1.0 - k / (lags + 1.0)
        lrv += 2.0 * w * (e[k:] @ e[:-k]) / n
    if lrv <= 0:
        return float("nan"), float("nan")
    t = x.mean() / math.sqrt(lrv / n)
    p = 2.0 * sps.t.sf(abs(t), df=n - 1)
    return float(t), float(p)


def block_bootstrap_mean_ci(x: np.ndarray, alpha: float = 0.05, n_boot: int = 2000, block: int | None = None,
                            seed: int = 0) -> tuple[float, float]:
    """Moving-block bootstrap CI for the mean (preserves short-range dependence)."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 5:
        return float("nan"), float("nan")
    if block is None:
        block = max(1, int(round(n ** (1 / 3))))
    rng = np.random.default_rng(seed)
    n_blocks = int(math.ceil(n / block))
    starts = rng.integers(0, n - block + 1, size=(n_boot, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(n_boot, -1)[:, :n]
    means = x[idx].mean(axis=1)
    return float(np.quantile(means, alpha / 2)), float(np.quantile(means, 1 - alpha / 2))


def bh_fdr(pvals: list[float] | np.ndarray, q: float = 0.10) -> tuple[np.ndarray, np.ndarray]:
    """Benjamini-Hochberg. Returns (reject mask, adjusted p-values). NaN p-values never reject."""
    p = np.asarray(pvals, dtype=float)
    m_valid = np.isfinite(p)
    adj = np.full_like(p, np.nan)
    rej = np.zeros(len(p), dtype=bool)
    pv = p[m_valid]
    m = len(pv)
    if m == 0:
        return rej, adj
    order = np.argsort(pv)
    ranked = pv[order] * m / np.arange(1, m + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    a = np.empty(m)
    a[order] = np.minimum(ranked, 1.0)
    adj[m_valid] = a
    rej[m_valid] = a <= q
    return rej, adj


def strategy_metrics(net_bps: np.ndarray, gross_bps: np.ndarray, cost_bps: np.ndarray, exit_day: np.ndarray,
                     hold_minutes: np.ndarray, period_days: float) -> dict:
    """Metrics for an equal-notional, non-compounding sequence of trades.

    P&L is aggregated to calendar days (including days with no trade, as 0)
    before computing Sharpe/Sortino, so a sparse strategy is not flattered by
    measuring only on the days it happened to trade."""
    net = np.asarray(net_bps, dtype=float)
    n = len(net)
    out: dict = {"n_trades": n}
    if n == 0:
        return out
    wins, losses = net[net > 0], net[net <= 0]
    days = max(1, int(round(period_days)))
    daily = np.zeros(days)
    np.add.at(daily, np.clip(exit_day, 0, days - 1), net)
    eq = np.cumsum(daily)
    dd = eq - np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]
    sd = daily.std(ddof=1)
    downside = np.sqrt(np.mean(np.minimum(daily, 0) ** 2))
    gross_profit = float(np.sum(gross_bps[gross_bps > 0]))
    out.update({
        "mean_net_bps": float(net.mean()),
        "median_net_bps": float(np.median(net)),
        "total_net_bps": float(net.sum()),
        "mean_gross_bps": float(np.mean(gross_bps)),
        "mean_cost_bps": float(np.mean(cost_bps)),
        "win_rate": float(len(wins) / n),
        "avg_win_bps": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss_bps": float(losses.mean()) if len(losses) else 0.0,
        "profit_factor": float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf"),
        "sharpe_daily_ann": float(daily.mean() / sd * math.sqrt(365)) if sd > 0 else float("nan"),
        "sortino_daily_ann": float(daily.mean() / downside * math.sqrt(365)) if downside > 0 else float("nan"),
        "max_drawdown_bps": float(dd.min()),
        "trades_per_day": n / period_days,
        "exposure_frac": float(np.sum(hold_minutes) / (period_days * 1440)),
        "fees_over_gross_profit": float(np.sum(cost_bps) / gross_profit) if gross_profit > 0 else float("inf"),
    })
    return out
