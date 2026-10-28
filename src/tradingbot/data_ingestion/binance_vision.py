"""Downloader for Binance's public historical archive (https://data.binance.vision).

Why this source: it is the only free, bulk, checksummed historical source
reachable from the research environment that carries, for the same venue,
1m klines *with taker-buy volume*, the premium index (perp vs. spot index),
funding settlements, 5-minute open interest, and percentage-band book depth.

What it does NOT carry (do not pretend otherwise downstream):
- Historical liquidation events (the liquidationSnapshot dataset is no
  longer published).
- Full L2 order-book history. `bookDepth` is a coarse snapshot of cumulative
  depth within +/-1..5% of mid, roughly every 30s -- useless for queue
  modelling, only usable as a slow liquidity-regime proxy.
- Order-level or quote-level data (bookTicker is not published for UM futures
  any more).

Provenance: every file is verified against the archive's published SHA-256
checksum before parsing, and a manifest line (url, sha256, rows, retrieval
time) is appended to `<root>/manifest.jsonl` so any research dataset can be
traced back to the exact source bytes.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from threading import Lock

import pandas as pd
import requests

log = logging.getLogger(__name__)

BASE_URL = "https://data.binance.vision/data"

KLINE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore",
]

# Datasets whose files come without a header in some periods and with one in others.
_HEADERLESS_COLUMNS = {
    "klines": KLINE_COLUMNS,
    "premiumIndexKlines": KLINE_COLUMNS,
    "markPriceKlines": KLINE_COLUMNS,
    "indexPriceKlines": KLINE_COLUMNS,
    "fundingRate": ["calc_time", "funding_interval_hours", "last_funding_rate"],
}

# Kinds that only exist as daily files on the archive.
DAILY_ONLY_KINDS = {"metrics", "bookDepth"}


class ChecksumMismatch(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ArchiveFile:
    market: str        # "futures/um" or "spot"
    kind: str          # klines, premiumIndexKlines, fundingRate, metrics, bookDepth, aggTrades ...
    symbol: str        # exchange-native, e.g. BTCUSDT
    period: str        # "YYYY-MM" (monthly) or "YYYY-MM-DD" (daily)
    interval: str | None = None  # "1m" for kline-type kinds

    @property
    def freq(self) -> str:
        return "daily" if len(self.period) == 10 else "monthly"

    @property
    def filename(self) -> str:
        if self.interval:
            return f"{self.symbol}-{self.interval}-{self.period}.zip"
        return f"{self.symbol}-{self.kind}-{self.period}.zip"

    @property
    def url(self) -> str:
        parts = [BASE_URL, self.market, self.freq, self.kind, self.symbol]
        if self.interval:
            parts.append(self.interval)
        parts.append(self.filename)
        return "/".join(parts)

    def local_path(self, root: Path) -> Path:
        sub = Path(self.market.replace("/", "_")) / self.kind / self.symbol
        if self.interval:
            sub = sub / self.interval
        return root / sub / f"{self.period}.parquet"


def month_range(start: str, end: str) -> list[str]:
    """Inclusive list of YYYY-MM strings."""
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def day_range(start: date, end: date) -> list[str]:
    out = []
    d = start
    while d <= end:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _to_epoch_ms(series: pd.Series) -> pd.Series:
    """Archive timestamps are ms, except spot files from 2025 onward which are
    microseconds. Anything above 1e14 cannot be a ms epoch before year 5000."""
    s = pd.to_numeric(series, errors="raise").astype("int64")
    return s.where(s < 10**14, s // 1000)


def parse_archive_csv(kind: str, raw: bytes) -> pd.DataFrame:
    text = raw.decode("utf-8")
    first = text.lstrip()[:1]
    has_header = not (first.isdigit() or first == "-")
    if has_header:
        df = pd.read_csv(io.StringIO(text))
    else:
        cols = _HEADERLESS_COLUMNS.get(kind)
        if cols is None:
            raise ValueError(f"headerless file for kind={kind!r} with no known column layout")
        df = pd.read_csv(io.StringIO(text), header=None, names=cols)

    if kind in ("klines", "premiumIndexKlines", "markPriceKlines", "indexPriceKlines"):
        df = df.drop(columns=["ignore"], errors="ignore")
        df["open_time"] = _to_epoch_ms(df["open_time"])
        df["close_time"] = _to_epoch_ms(df["close_time"])
        for c in df.columns:
            if c not in ("open_time", "close_time", "count"):
                df[c] = df[c].astype("float64")
        df = df.rename(columns={"open_time": "ts"})
    elif kind == "fundingRate":
        df["calc_time"] = _to_epoch_ms(df["calc_time"])
        df = df.rename(columns={"calc_time": "ts", "last_funding_rate": "funding_rate"})
        df["funding_rate"] = df["funding_rate"].astype("float64")
    elif kind in ("metrics", "bookDepth"):
        tcol = "create_time" if kind == "metrics" else "timestamp"
        ts = pd.to_datetime(df[tcol], utc=True, format="mixed")
        df = df.drop(columns=[tcol])
        # pandas >= 3 may infer second resolution from strings; pin the unit.
        df.insert(0, "ts", ts.dt.as_unit("ms").astype("int64"))
        if "symbol" in df.columns:
            df = df.drop(columns=["symbol"])
        for c in df.columns:
            if c != "ts":
                df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    elif kind == "aggTrades":
        df = df.rename(columns={"transact_time": "ts"})
        df["ts"] = _to_epoch_ms(df["ts"])
    return df.sort_values("ts", kind="stable").reset_index(drop=True)


class BinanceVisionClient:
    def __init__(self, root: Path | str, session: requests.Session | None = None, max_retries: int = 4,
                 timeout_s: float = 60.0) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        if session is None:
            session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(pool_connections=32, pool_maxsize=32)
            session.mount("https://", adapter)
        self.session = session
        self.max_retries = max_retries
        self.timeout_s = timeout_s
        self._manifest_lock = Lock()

    def _get(self, url: str) -> requests.Response | None:
        delay = 2.0
        for attempt in range(self.max_retries + 1):
            try:
                r = self.session.get(url, timeout=self.timeout_s)
                if r.status_code == 404:
                    return None
                if r.status_code == 429 or r.status_code >= 500:
                    raise requests.HTTPError(f"HTTP {r.status_code}")
                r.raise_for_status()
                return r
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
                if attempt == self.max_retries:
                    raise
                log.warning("retrying %s after %s (attempt %d)", url, exc, attempt + 1)
                time.sleep(delay)
                delay *= 2
        return None

    def fetch(self, f: ArchiveFile, overwrite: bool = False) -> Path | None:
        """Downloads, checksum-verifies, parses and stores one archive file.
        Returns the parquet path, or None if the archive has no such file."""
        out = f.local_path(self.root)
        if out.exists() and not overwrite:
            return out
        resp = self._get(f.url)
        if resp is None:
            return None
        payload = resp.content
        digest = hashlib.sha256(payload).hexdigest()
        ck = self._get(f.url + ".CHECKSUM")
        expected = ck.text.split()[0] if ck is not None else None
        if expected is not None and expected != digest:
            raise ChecksumMismatch(f"{f.url}: expected {expected}, got {digest}")

        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = [n for n in zf.namelist() if n.endswith(".csv")]
            if len(names) != 1:
                raise ValueError(f"{f.url}: expected one csv, found {names}")
            df = parse_archive_csv(f.kind, zf.read(names[0]))

        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp")
        df.to_parquet(tmp, index=False)
        tmp.replace(out)  # atomic: a crash never leaves a half-written parquet
        self._append_manifest({
            "url": f.url,
            "sha256": digest,
            "checksum_verified": expected is not None,
            "rows": int(len(df)),
            "path": str(out.relative_to(self.root)),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        })
        return out

    def fetch_many(self, files: list[ArchiveFile], workers: int = 12) -> dict[ArchiveFile, Path | None]:
        results: dict[ArchiveFile, Path | None] = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(self.fetch, f): f for f in files}
            for fut in as_completed(futs):
                f = futs[fut]
                try:
                    results[f] = fut.result()
                except Exception as exc:  # recorded, not swallowed: caller sees None + log
                    log.error("failed %s: %s", f.url, exc)
                    results[f] = None
        return results

    def _append_manifest(self, rec: dict) -> None:
        with self._manifest_lock, open(self.root / "manifest.jsonl", "a") as fh:
            fh.write(json.dumps(rec) + "\n")


def load_series(root: Path | str, market: str, kind: str, symbol: str, interval: str | None = None) -> pd.DataFrame:
    """Concatenates every stored period of one series, de-duplicated on ts."""
    base = Path(root) / market.replace("/", "_") / kind / symbol
    if interval:
        base = base / interval
    parts = sorted(base.glob("*.parquet"))
    if not parts:
        raise FileNotFoundError(f"no stored data under {base}")
    df = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
    return df.sort_values("ts", kind="stable").drop_duplicates("ts", keep="last").reset_index(drop=True)
