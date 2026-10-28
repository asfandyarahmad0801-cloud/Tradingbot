"""Fetch the Milestone-1 research dataset from data.binance.vision.

Public archive, no API key. Every file is SHA-256 verified and recorded in
<out>/manifest.jsonl.

    python scripts/fetch_research_data.py --out data/raw \
        --symbols BTCUSDT ETHUSDT SOLUSDT XRPUSDT DOGEUSDT \
        --start 2023-01 --end 2026-09
"""
from __future__ import annotations

import argparse
import logging
from datetime import date

from tradingbot.data_ingestion.binance_vision import ArchiveFile, BinanceVisionClient, day_range, month_range

MONTHLY_FUTURES = [("klines", "1m"), ("premiumIndexKlines", "1m"), ("fundingRate", None)]
DAILY_FUTURES = ["metrics"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/raw")
    ap.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"])
    ap.add_argument("--spot-symbols", nargs="*", default=["BTCUSDT", "ETHUSDT"])
    ap.add_argument("--start", default="2023-01")
    ap.add_argument("--end", default="2026-09")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--skip-metrics", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    months = month_range(args.start, args.end)
    ey, em = map(int, args.end.split("-"))
    last_day = date(ey + (em == 12), em % 12 + 1, 1).toordinal() - 1
    days = day_range(date(*map(int, args.start.split("-")), 1), date.fromordinal(last_day))

    files: list[ArchiveFile] = []
    for s in args.symbols:
        for kind, interval in MONTHLY_FUTURES:
            files += [ArchiveFile("futures/um", kind, s, m, interval) for m in months]
        if not args.skip_metrics:
            files += [ArchiveFile("futures/um", k, s, d) for k in DAILY_FUTURES for d in days]
    for s in args.spot_symbols:
        files += [ArchiveFile("spot", "klines", s, m, "1m") for m in months]

    client = BinanceVisionClient(args.out)
    res = client.fetch_many(files, workers=args.workers)
    missing = [f.url for f, p in res.items() if p is None]
    logging.info("fetched %d/%d files; %d missing", len(res) - len(missing), len(res), len(missing))
    for u in sorted(missing)[:50]:
        logging.info("missing: %s", u)


if __name__ == "__main__":
    main()
