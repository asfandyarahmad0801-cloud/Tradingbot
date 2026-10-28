"""Signal -> trades -> net P&L, with the costs and timing a real taker would face.

Execution assumptions (all explicit, all conservative-leaning):
- The decision is made at the close of the bar keyed by `decision_ts`.
- Entry fills at the close of the 1m bar `delay_min` minutes later (default
  1 minute: decision latency + order round-trip). No fill at the decision
  bar's own close -- that price is already history when the signal exists.
- Exit is purely time-based at entry + horizon. No stop/target in this layer,
  so results are not flattered by intrabar stop sequencing; MAE/MFE are
  reported so stop design can be studied separately.
- Funding is charged at every actual settlement in (entry, exit] using the
  realised historical rate, signed by side.
- Positions per symbol never overlap: while a trade is open, further signals
  on that symbol are ignored (not queued).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from tradingbot.research.costs import CostModel
from tradingbot.research.dataset import MIN_MS, SymbolData
from tradingbot.research.stats import block_bootstrap_mean_ci, newey_west_tstat, strategy_metrics

DAY_MS = 1440 * MIN_MS


@dataclass(slots=True)
class ForwardTable:
    symbol: str
    horizon_min: int
    delay_min: int
    decision_ts: np.ndarray
    entry_ts: np.ndarray
    exit_ts: np.ndarray
    gross_long: np.ndarray     # simple return of a long, NaN when either price is missing
    funding_long: np.ndarray   # sum of funding rates a long pays over the holding window


def forward_table(sd: SymbolData, decision_ts: np.ndarray, horizon_min: int, delay_min: int = 1) -> ForwardTable:
    close = sd.m1["close"]
    entry_ts = decision_ts + delay_min * MIN_MS
    exit_ts = entry_ts + horizon_min * MIN_MS
    pe = close.reindex(entry_ts).to_numpy()
    px = close.reindex(exit_ts).to_numpy()
    gross = px / pe - 1.0
    fts = sd.funding["ts"].to_numpy()
    cum = np.concatenate([[0.0], np.cumsum(sd.funding["funding_rate"].to_numpy())])
    f_entry = cum[np.searchsorted(fts, entry_ts, side="right")]
    f_exit = cum[np.searchsorted(fts, exit_ts, side="right")]
    return ForwardTable(sd.symbol, horizon_min, delay_min, decision_ts, entry_ts, exit_ts, gross, f_exit - f_entry)


def simulate_trades(signal: np.ndarray, ft: ForwardTable, cost: CostModel, start_ms: int, end_ms: int,
                    sd: SymbolData | None = None) -> pd.DataFrame:
    """`signal` is aligned with `ft.decision_ts` (values -1, 0, +1; NaN = 0).
    Trades must both open and close inside [start_ms, end_ms)."""
    sig = np.nan_to_num(np.asarray(signal, dtype=float))
    cand = np.where((sig != 0) & (ft.decision_ts >= start_ms) & (ft.exit_ts < end_ms) & np.isfinite(ft.gross_long))[0]
    rows = []
    next_free = -1
    rt = cost.round_trip_bps(ft.symbol)
    for i in cand:
        if ft.decision_ts[i] < next_free:
            continue
        side = float(np.sign(sig[i]))
        gross_bps = side * ft.gross_long[i] * 1e4
        fund_bps = side * ft.funding_long[i] * 1e4
        rows.append((ft.symbol, int(ft.decision_ts[i]), int(ft.entry_ts[i]), int(ft.exit_ts[i]), side,
                     gross_bps, rt, fund_bps, gross_bps - rt - fund_bps))
        next_free = ft.exit_ts[i]
    tr = pd.DataFrame(rows, columns=["symbol", "decision_ts", "entry_ts", "exit_ts", "side", "gross_bps",
                                     "cost_bps", "funding_bps", "net_bps"])
    if sd is not None and len(tr):
        tr = add_excursions(tr, sd)
    return tr


def add_excursions(tr: pd.DataFrame, sd: SymbolData) -> pd.DataFrame:
    """Max adverse / favourable excursion (bps, from entry, using 1m high/low
    of bars that close strictly after entry and no later than exit)."""
    idx = sd.m1.index.to_numpy()
    hi, lo, cl = sd.m1["high"].to_numpy(), sd.m1["low"].to_numpy(), sd.m1["close"].to_numpy()
    mae, mfe = [], []
    for e, x, s in zip(tr["entry_ts"].to_numpy(), tr["exit_ts"].to_numpy(), tr["side"].to_numpy()):
        a, b = np.searchsorted(idx, e, side="left"), np.searchsorted(idx, x, side="right")
        pe = cl[a]
        h, l = hi[a + 1:b].max() / pe - 1, lo[a + 1:b].min() / pe - 1
        if s > 0:
            mae.append(min(l, 0) * 1e4)
            mfe.append(max(h, 0) * 1e4)
        else:
            mae.append(min(-h, 0) * 1e4)
            mfe.append(max(-l, 0) * 1e4)
    tr = tr.copy()
    tr["mae_bps"], tr["mfe_bps"] = mae, mfe
    return tr


def random_timing_null(trades: pd.DataFrame, tables: dict[str, ForwardTable], cost: CostModel, start_ms: int,
                       end_ms: int, n_sims: int = 1000, seed: int = 0) -> np.ndarray:
    """Distribution of mean net bps when the *same number of longs and shorts
    per symbol* are placed at uniformly random valid times in the same period.

    This is the key control: a long-biased signal in a bull market looks
    'profitable' against zero, but not against random long entries."""
    rng = np.random.default_rng(seed)
    total = np.zeros(n_sims)
    n_total = 0
    for sym, g in trades.groupby("symbol"):
        ft = tables[sym]
        valid = np.where((ft.decision_ts >= start_ms) & (ft.exit_ts < end_ms) & np.isfinite(ft.gross_long))[0]
        rt = cost.round_trip_bps(sym)
        for side in (1.0, -1.0):
            k = int((g["side"] == side).sum())
            if k == 0 or len(valid) == 0:
                continue
            pick = valid[rng.integers(0, len(valid), size=(n_sims, k))]
            net = side * ft.gross_long[pick] * 1e4 - rt - side * ft.funding_long[pick] * 1e4
            total += net.sum(axis=1)
            n_total += k
    return total / max(n_total, 1)


def summarize(trades: pd.DataFrame, start_ms: int, end_ms: int, null_means: np.ndarray | None = None) -> dict:
    period_days = (end_ms - start_ms) / DAY_MS
    if len(trades) == 0:
        return {"n_trades": 0}
    t = trades.sort_values("exit_ts")
    net = t["net_bps"].to_numpy()
    out = strategy_metrics(
        net, t["gross_bps"].to_numpy(), t["cost_bps"].to_numpy() + t["funding_bps"].to_numpy(),
        ((t["exit_ts"].to_numpy() - start_ms) // DAY_MS).astype(int),
        ((t["exit_ts"] - t["entry_ts"]).to_numpy() / MIN_MS), period_days,
    )
    tstat, p = newey_west_tstat(net)
    lo, hi = block_bootstrap_mean_ci(net)
    out.update({"t_nw": tstat, "p_two_sided": p, "ci95_mean_net_bps": [lo, hi],
                "n_long": int((t["side"] > 0).sum()), "n_short": int((t["side"] < 0).sum())})
    if "mae_bps" in t:
        out["mean_mae_bps"] = float(t["mae_bps"].mean())
        out["mean_mfe_bps"] = float(t["mfe_bps"].mean())
    if null_means is not None:
        obs = net.mean()
        out["null_mean_bps"] = float(null_means.mean())
        out["p_vs_random_timing"] = float((1 + np.sum(null_means >= obs)) / (len(null_means) + 1))
        out["excess_vs_random_bps"] = float(obs - null_means.mean())
    out["by_symbol"] = {s: {"n": int(len(g)), "mean_net_bps": float(g["net_bps"].mean())}
                        for s, g in t.groupby("symbol")}
    years = pd.to_datetime(t["exit_ts"], unit="ms", utc=True).dt.year
    out["by_year"] = {int(y): {"n": int(len(g)), "mean_net_bps": float(g["net_bps"].mean())}
                      for y, g in t.groupby(years)}
    return out
