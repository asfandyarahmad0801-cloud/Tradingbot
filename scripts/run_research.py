"""Milestone-1 research run: data-quality audit -> causal features ->
pre-registered discovery/validation/test protocol -> registry + report.

    python scripts/run_research.py --data data/raw --out research
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

from tradingbot.research.costs import CostModel
from tradingbot.research.dataset import load_symbol
from tradingbot.research.features import add_reference_features, build_features
from tradingbot.research.hypotheses import HYPOTHESES, ROUND2
from tradingbot.research.protocol import Context, Rules, Splits, run_protocol
from tradingbot.research.registry import Registry, dataset_fingerprint, git_commit


def fmt(x, nd=2):
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "–"
    return f"{x:.{nd}f}" if isinstance(x, float) else str(x)


def stage_row(name: str, s: dict | None) -> str:
    if not s or not s.get("n_trades"):
        return f"| {name} | 0 | – | – | – | – | – | – | – | – |"
    return (f"| {name} | {s['n_trades']} | {fmt(s['mean_gross_bps'])} | {fmt(s['mean_net_bps'])} | "
            f"{fmt(s['win_rate'] * 100, 1)}% | {fmt(s['profit_factor'])} | {fmt(s['sharpe_daily_ann'])} | "
            f"{fmt(s['max_drawdown_bps'], 0)} | {fmt(s.get('p_two_sided'), 3)} | {fmt(s.get('p_vs_random_timing'), 3)} |")


def write_report(path: Path, records: list[dict], quality: list[dict], meta: dict) -> None:
    L = ["# Milestone 1 — Research Results (auto-generated)", "",
         f"Generated {meta['generated_at']} · commit `{meta['commit']}` · dataset `{meta['fingerprint']}`", "",
         "Costs (base): taker {taker_fee_bps} bps/side + half-spread/slippage per side "
         "(BTC/ETH 1.0, others {default_impact_bps}); stressed ×{stress}. Entry 1 min after decision; "
         "time-based exit; realised funding charged.".format(
             stress=meta["rules"]["stress_multiplier"], **meta["cost"]), "",
         f"Splits: {meta['splits']}. Multiple-testing family size (discovery): {meta['family_size']}.", "",
         "## Verdict summary", "",
         "| ID | Name | Params | Verdict | Disc. n | Disc. gross bps | Disc. net bps | Excess vs random bps | "
         "p(random) | BH adj | Maker-bound net | Reasons |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in records:
        d = r["discovery"]
        L.append(f"| {r['hypothesis']} | {r['name']} | `{json.dumps(r['params'])}` | **{r['verdict']}** | "
                 f"{d.get('n_trades', 0)} | {fmt(d.get('mean_gross_bps'))} | {fmt(d.get('mean_net_bps'))} | "
                 f"{fmt(d.get('excess_vs_random_bps'))} | {fmt(d.get('p_vs_random_timing'), 3)} | "
                 f"{fmt(d.get('p_bh_adj'), 3)} | {fmt(r['discovery_maker_bound'].get('mean_net_bps'))} | "
                 f"{'; '.join(r.get('reasons', []))} |")
    L += ["", "## Per-stage detail (only stages actually run are shown)", "",
          "| Variant | Stage | n | gross bps | net bps | win | PF | Sharpe(d) | MDD bps | p(NW) | p(random) |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in records:
        tag = f"{r['hypothesis']} {json.dumps(r['params'])}"
        for st in ("discovery", "validation", "test"):
            if st in r:
                L.append(stage_row(f"{tag} / {st}", r[st]).replace(f"| {tag} / {st} |", f"| {tag} | {st} |", 1))
    L += ["", "## Data quality", "", "| Series | rows | coverage | missing steps | dups | largest gap (min) | ok |",
          "|---|---|---|---|---|---|---|"]
    for q in quality:
        L.append(f"| {q['name']} | {q['rows']} | {q['coverage']:.5f} | {q['missing_steps']} | {q['duplicates']} | "
                 f"{q['largest_gap_ms'] / 60000:.0f} | {q['ok']} |")
    path.write_text("\n".join(L) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/raw")
    ap.add_argument("--out", default="research")
    ap.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"])
    ap.add_argument("--only", nargs="*", help="hypothesis ids to run (default all)")
    ap.add_argument("--round", type=int, default=1, help="1 = Milestone-1 family, 2 = round-2 family")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    t = time.time()
    data, feats, quality = {}, {}, []
    for s in args.symbols:
        sd = load_symbol(args.data, s)
        data[s] = sd
        quality += [q.to_dict() for q in sd.quality]
        feats[s] = build_features(sd)
        print(f"loaded {s}: {len(sd.m1)} 1m rows, {len(feats[s])} 5m rows ({time.time() - t:.0f}s)")
    if "BTCUSDT" in feats:
        for s in args.symbols:
            feats[s] = add_reference_features(feats[s], feats["BTCUSDT"])

    bad = [q for q in quality if not q["ok"]]
    for q in bad:
        print(f"DATA QUALITY WARNING: {q['name']} coverage={q['coverage']:.5f} gaps={q['gap_list'][:3]}")

    pool = HYPOTHESES if args.round == 1 else ROUND2
    hyps = [h for h in pool if not args.only or h.hid in args.only]
    cost, splits, rules = CostModel(), Splits(), Rules()
    ctx = Context(data, feats, cost)
    records = run_protocol(hyps, ctx, splits, rules)

    meta = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "commit": git_commit(),
        "fingerprint": dataset_fingerprint(Path(args.data) / "manifest.jsonl", args.symbols),
        "cost": cost.to_dict(), "rules": rules.__dict__, "splits": splits.__dict__,
        "family_size": records[0].get("family_size") if records else 0, "symbols": args.symbols,
    }
    reg = Registry(out / "registry.jsonl")
    run_id = f"r{args.round}-{meta['generated_at']}"
    for r in records:
        reg.append({"run_id": run_id, **meta, **r})
    (out / "data_quality.json").write_text(json.dumps(quality, indent=1, default=str))
    write_report(out / ("M1_RESULTS.md" if args.round == 1 else f"R{args.round}_RESULTS.md"), records, quality, meta)
    print(f"done in {time.time() - t:.0f}s; verdicts:")
    for r in records:
        print(f"  {r['hypothesis']} {r['params']} -> {r['verdict']} {r.get('reasons', '')}")


if __name__ == "__main__":
    main()
