"""Download real historical OHLCV data via ccxt's public (no API key
required) endpoints and write it in the CSV format `tradingbot.main backtest`
expects: one file per symbol, columns `timestamp,open,high,low,close,volume`.

This is a standalone utility -- it does not import the rest of tradingbot,
so it has no dependency on exchange credentials or config, and can be run
before you've set anything else up. It only needs network access to the
exchange's public REST API, which this development sandbox does not have
(see docs/LIMITATIONS.md) -- run this on your own machine instead.

Usage:
    python scripts/fetch_historical_data.py --exchange binanceusdm \
        --symbols BTC/USDT:USDT ETH/USDT:USDT SOL/USDT:USDT \
        --timeframe 1m --days 30 --out-dir data/historical

Notes:
- Exchanges cap how many candles one request returns (commonly 1000-1500),
  so this paginates with `since` until it reaches the requested start time
  or the exchange returns no more data.
- Respects the exchange's rate limit via ccxt's built-in throttling
  (`enableRateLimit: True`) -- do not disable that to "go faster"; it
  exists to keep you from getting IP-banned.
- Output filenames are the symbol's base asset lowercased (e.g.
  `BTC/USDT:USDT` -> `btc.csv`), matching what
  `tradingbot.main._load_candles_csv` expects when it reconstructs the
  symbol from the filename.
"""
from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

import ccxt


def fetch_symbol_ohlcv(exchange: ccxt.Exchange, symbol: str, timeframe: str, since_ms: int, until_ms: int) -> list[list[float]]:
    all_candles: list[list[float]] = []
    cursor = since_ms
    timeframe_ms = exchange.parse_timeframe(timeframe) * 1000

    while cursor < until_ms:
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=cursor, limit=1000)
        if not batch:
            break
        all_candles.extend(batch)
        last_ts = batch[-1][0]
        if last_ts <= cursor:
            break  # exchange isn't advancing -- avoid an infinite loop
        cursor = last_ts + timeframe_ms
        if len(batch) < 2:
            break

    # De-duplicate and clip to the requested window (pagination can overlap by one candle).
    seen = set()
    deduped = []
    for row in all_candles:
        if row[0] in seen or row[0] > until_ms:
            continue
        seen.add(row[0])
        deduped.append(row)
    deduped.sort(key=lambda r: r[0])
    return deduped


def write_csv(path: Path, candles: list[list[float]]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for ts, o, h, l, c, v in candles:
            writer.writerow([int(ts), o, h, l, c, v])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--exchange", default="binanceusdm", help="ccxt exchange id (e.g. binanceusdm, bybit)")
    parser.add_argument("--symbols", nargs="+", required=True, help="Unified ccxt perpetual symbols, e.g. BTC/USDT:USDT")
    parser.add_argument("--timeframe", default="1m")
    parser.add_argument("--days", type=int, default=30, help="How many days of history to fetch, ending now")
    parser.add_argument("--out-dir", default="data/historical")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    exchange_cls = getattr(ccxt, args.exchange)
    exchange = exchange_cls({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    exchange.load_markets()

    until_ms = int(time.time() * 1000)
    since_ms = until_ms - args.days * 24 * 3600 * 1000

    for symbol in args.symbols:
        print(f"Fetching {symbol} {args.timeframe} for the last {args.days} day(s)...")
        candles = fetch_symbol_ohlcv(exchange, symbol, args.timeframe, since_ms, until_ms)
        if not candles:
            print(f"  WARNING: no candles returned for {symbol}, skipping")
            continue
        base = symbol.split("/")[0].lower()
        path = out_dir / f"{base}.csv"
        write_csv(path, candles)
        print(f"  wrote {len(candles)} candles -> {path}")

    if hasattr(exchange, "close"):
        exchange.close()
    print("\nDone. Run e.g.:")
    print(f"  python -m tradingbot.main backtest --data-dir {out_dir} --starting-equity 10000")


if __name__ == "__main__":
    main()
