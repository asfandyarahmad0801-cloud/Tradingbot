"""Pre-registered three-stage evaluation protocol.

    discovery  -> every variant of every hypothesis is evaluated; BH-FDR
                  across the whole family; robustness filters.
    validation -> only discovery survivors, parameters frozen; Holm
                  correction across survivors.
    test       -> only validation survivors, evaluated once. The test window
                  is never used to choose anything.

The rules below are fixed in code so they cannot be bent after seeing
results. A hypothesis that reaches 'accepted_for_paper' has earned the right
to be paper-traded -- nothing more.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from tradingbot.research.costs import CostModel
from tradingbot.research.dataset import SymbolData
from tradingbot.research.evaluate import ForwardTable, forward_table, random_timing_null, simulate_trades, summarize
from tradingbot.research.hypotheses import Hypothesis
from tradingbot.research.stats import bh_fdr


def _ms(d: str) -> int:
    return int(datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp() * 1000)


@dataclass(frozen=True)
class Splits:
    discovery: tuple[str, str] = ("2023-01-01", "2025-01-01")
    validation: tuple[str, str] = ("2025-01-01", "2025-10-01")
    test: tuple[str, str] = ("2025-10-01", "2026-10-01")

    def ms(self, name: str) -> tuple[int, int]:
        a, b = getattr(self, name)
        return _ms(a), _ms(b)


@dataclass(frozen=True)
class Rules:
    fdr_q: float = 0.10
    min_trades_discovery: int = 40
    min_trades_validation: int = 20
    validation_alpha: float = 0.05
    test_alpha: float = 0.05
    stress_multiplier: float = 1.5
    min_positive_symbol_share: float = 0.5
    n_null_sims: int = 1000


@dataclass
class Context:
    data: dict[str, SymbolData]
    features: dict[str, pd.DataFrame]
    cost: CostModel = field(default_factory=CostModel)
    delay_min: int = 1
    _ft: dict[tuple[str, int], ForwardTable] = field(default_factory=dict)

    def table(self, symbol: str, horizon: int) -> ForwardTable:
        key = (symbol, horizon)
        if key not in self._ft:
            idx = self.features[symbol].index.to_numpy(dtype="int64")
            self._ft[key] = forward_table(self.data[symbol], idx, horizon, self.delay_min)
        return self._ft[key]


def eligible_symbols(h: Hypothesis, ctx: Context) -> list[str]:
    syms = list(ctx.features)
    if h.symbols == "alts":
        syms = [s for s in syms if s != "BTCUSDT"]
    return syms


def run_variant(h: Hypothesis, params: dict, ctx: Context, start: int, end: int, cost: CostModel,
                n_null: int, seed: int = 0) -> tuple[pd.DataFrame, dict]:
    horizon = int(params["horizon_min"])
    trades, tables = [], {}
    for s in eligible_symbols(h, ctx):
        f = ctx.features[s]
        sig = h.signal_fn(f, params).to_numpy(dtype=float)
        ft = ctx.table(s, horizon)
        tables[s] = ft
        trades.append(simulate_trades(sig, ft, cost, start, end, ctx.data[s]))
    tr = pd.concat([t for t in trades if len(t)], ignore_index=True) if any(len(t) for t in trades) \
        else pd.DataFrame(columns=["symbol", "side", "net_bps"])
    null = random_timing_null(tr, tables, cost, start, end, n_null, seed) if len(tr) and n_null > 0 else None
    return tr, summarize(tr, start, end, null)


def _robust(summary: dict, stressed: dict, rules: Rules) -> tuple[bool, list[str]]:
    reasons = []
    if stressed.get("mean_net_bps", -1) <= 0:
        reasons.append(f"not profitable at {rules.stress_multiplier}x costs")
    years = summary.get("by_year", {})
    neg_years = [y for y, v in years.items() if v["n"] >= 10 and v["mean_net_bps"] <= 0]
    if neg_years:
        reasons.append(f"non-positive in year(s) {neg_years}")
    syms = summary.get("by_symbol", {})
    if syms:
        share = np.mean([v["mean_net_bps"] > 0 for v in syms.values()])
        if share < rules.min_positive_symbol_share:
            reasons.append(f"positive on only {share:.0%} of symbols")
    return not reasons, reasons


def run_protocol(hyps: list[Hypothesis], ctx: Context, splits: Splits = Splits(), rules: Rules = Rules(),
                 log=print) -> list[dict]:
    """Returns one result record per (hypothesis, variant), with per-stage summaries and a verdict."""
    records: list[dict] = []
    d0, d1 = splits.ms("discovery")
    for h in hyps:
        for params in h.variants():
            tr, summ = run_variant(h, params, ctx, d0, d1, ctx.cost, rules.n_null_sims)
            _, maker = run_variant(h, params, ctx, d0, d1, ctx.cost.as_maker(), 0)
            records.append({
                "hypothesis": h.hid, "name": h.name, "params": params, "baseline": h.hid.startswith("B"),
                "discovery": summ, "discovery_maker_bound": {k: maker.get(k) for k in ("mean_net_bps", "n_trades")},
            })
            log(f"[discovery] {h.hid} {params}: n={summ.get('n_trades')} "
                f"gross={summ.get('mean_gross_bps', float('nan')):.2f} net={summ.get('mean_net_bps', float('nan')):.2f} "
                f"p_null={summ.get('p_vs_random_timing', float('nan')):.3f}")

    family = [r for r in records if not r["baseline"]]
    pvals = [r["discovery"].get("p_vs_random_timing", np.nan)
             if r["discovery"].get("n_trades", 0) >= rules.min_trades_discovery else np.nan for r in family]
    rej, adj = bh_fdr(pvals, rules.fdr_q)
    survivors = []
    for r, ok, padj in zip(family, rej, adj):
        r["discovery"]["p_bh_adj"] = None if np.isnan(padj) else float(padj)
        r["family_size"] = len(family)
        s = r["discovery"]
        if s.get("n_trades", 0) < rules.min_trades_discovery:
            r["verdict"], r["reasons"] = "inconclusive", [f"only {s.get('n_trades', 0)} discovery trades"]
            continue
        if s["mean_net_bps"] <= 0:
            r["verdict"], r["reasons"] = "rejected_discovery", ["non-positive mean net return after costs"]
            continue
        if not ok:
            r["verdict"], r["reasons"] = "rejected_discovery", [f"BH-adjusted p={padj:.3f} > q={rules.fdr_q}"]
            continue
        h = next(x for x in hyps if x.hid == r["hypothesis"])
        _, stressed = run_variant(h, r["params"], ctx, d0, d1, ctx.cost.stressed(rules.stress_multiplier), 0)
        good, why = _robust(s, stressed, rules)
        r["discovery_stressed_mean_net_bps"] = stressed.get("mean_net_bps")
        if not good:
            r["verdict"], r["reasons"] = "rejected_discovery", why
            continue
        survivors.append(r)

    v0, v1 = splits.ms("validation")
    passed_val = []
    m = max(1, len(survivors))
    ranked = []
    for r in survivors:
        h = next(x for x in hyps if x.hid == r["hypothesis"])
        _, vs = run_variant(h, r["params"], ctx, v0, v1, ctx.cost, rules.n_null_sims, seed=1)
        _, vstress = run_variant(h, r["params"], ctx, v0, v1, ctx.cost.stressed(rules.stress_multiplier), 0)
        r["validation"] = vs
        r["validation_stressed_mean_net_bps"] = vstress.get("mean_net_bps")
        ranked.append((vs.get("p_vs_random_timing", 1.0), r, vstress))
        log(f"[validation] {r['hypothesis']} {r['params']}: n={vs.get('n_trades')} net={vs.get('mean_net_bps')}")
    # Holm step-down across validation survivors
    ranked.sort(key=lambda x: x[0])
    holm_stop = False
    for i, (p, r, vstress) in enumerate(ranked):
        vs = r["validation"]
        thr = rules.validation_alpha / (m - i)
        reasons = []
        if vs.get("n_trades", 0) < rules.min_trades_validation:
            reasons.append(f"only {vs.get('n_trades', 0)} validation trades")
        if vs.get("mean_net_bps", -1) <= 0:
            reasons.append("non-positive validation net return")
        if holm_stop or p > thr:
            holm_stop = True
            reasons.append(f"p_vs_random={p:.3f} > Holm threshold {thr:.4f}")
        if (vstress.get("mean_net_bps") or -1) <= 0:
            reasons.append("not profitable at stressed costs in validation")
        if reasons:
            r["verdict"], r["reasons"] = "rejected_validation", reasons
        else:
            passed_val.append(r)

    t0, t1 = splits.ms("test")
    for r in passed_val:
        h = next(x for x in hyps if x.hid == r["hypothesis"])
        _, ts = run_variant(h, r["params"], ctx, t0, t1, ctx.cost, rules.n_null_sims, seed=2)
        r["test"] = ts
        ok = ts.get("mean_net_bps", -1) > 0 and ts.get("p_vs_random_timing", 1) <= rules.test_alpha
        r["verdict"] = "accepted_for_paper" if ok else "rejected_test"
        r["reasons"] = [] if ok else ["failed locked test window"]

    for r in records:
        if r["baseline"]:
            h = next(x for x in hyps if x.hid == r["hypothesis"])
            for name in ("validation", "test"):
                a, b = splits.ms(name)
                _, r[name] = run_variant(h, r["params"], ctx, a, b, ctx.cost, 0)
            r["verdict"], r["reasons"] = "baseline", []
    return records
