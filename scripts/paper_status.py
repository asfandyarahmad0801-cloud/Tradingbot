"""Print the live paper-trading status: trades, P&L, rejections, learned lessons.

    python scripts/paper_status.py --db state/scalp_paper.db --log state/paper_run.log
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def ts(ms: int | None) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%H:%M:%S") if ms else "-"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="state/scalp_paper.db")
    ap.add_argument("--log", default="state/paper_run.log")
    ap.add_argument("--memory", default="state/setup_memory.json")
    args = ap.parse_args()
    c = sqlite3.connect(args.db)
    cols = [r[1] for r in c.execute("pragma table_info(trades)")]
    rows = [dict(zip(cols, r)) for r in c.execute("select * from trades order by id")]
    print(f"== Trades opened: {len(rows)}")
    for t in rows:
        print(f"  {ts(t.get('opened_ts_ms') or t.get('entry_ts_ms'))} {t['symbol']:<16} {t['direction']:<5} "
              f"{t['setup_name']:<28} entry={t['entry_price']:.6g} stop={t['stop_price']:.6g} "
              f"notional=${t['notional']:.2f} lev={t['leverage']}x exit={t.get('exit_reason') or 'OPEN'}")

    log = Path(args.log).read_text() if Path(args.log).exists() else ""
    closed = re.findall(r"trade_closed (\S+) (\S+) (\S+) pnl=(-?[\d.]+) usd \((-?[\d.]+) bps\) equity=([\d.]+)", log)
    print(f"\n== Trades closed: {len(closed)}")
    for sym, setup, why, pnl, bps, eq in closed:
        print(f"  {sym:<16} {setup:<28} {why:<12} pnl=${float(pnl):+.3f} ({float(bps):+.1f} bps) equity=${eq}")
    if closed:
        pnls = [float(x[3]) for x in closed]
        print(f"  realized P&L ${sum(pnls):+.3f}  wins {sum(p > 0 for p in pnls)}/{len(pnls)}")

    cnt = collections.Counter()
    for d, r in c.execute("select decision, reasons_json from decisions"):
        for x in json.loads(r or "[]"):
            cnt[f"{d}: {x.split(':')[0]}"] += 1
    print("\n== Why setups were NOT traded (counts)")
    for k, v in cnt.most_common(10):
        print(f"  {v:>5}  {k}")

    scans = re.findall(r"universe_scan: (\d+)/(\d+)", log)
    if scans:
        print(f"\n== Scans: {len(scans)}, last: {scans[-1][0]}/{scans[-1][1]} contracts eligible")
    errs = len(re.findall(r"run_cycle_failed|Traceback", log))
    print(f"== Errors logged: {errs}")
    if Path(args.memory).exists():
        mem = json.loads(Path(args.memory).read_text())
        bad = {k: v for k, v in mem.items() if v.get("banned") or v.get("cooldown_until_ms")}
        print(f"\n== Learning memory: {len(mem)} contexts tracked, {len(bad)} blocked")
        for k, v in bad.items():
            print(f"  {k}: banned={v['banned']} {v['ban_reason']} cooldown_until={ts(v['cooldown_until_ms'])}")


if __name__ == "__main__":
    main()
