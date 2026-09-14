"""Dynamic perpetual-contract discovery, filtering and ranking.

Design rationale (spec section 3): the bot must not be restricted to a fixed
symbol list. This module re-derives the tradeable universe on every refresh
cycle from live exchange metadata plus fresh liquidity/spread/volatility
measurements, so a newly-listed contract becomes eligible the moment it
satisfies the same objective bar every other coin must clear, and a coin
whose liquidity has degraded drops out automatically.

Filtering is a hard gate (a coin either passes or it doesn't, with a
recorded reason -- see spec section 45 on logging rejected setups/contracts).
Ranking is a soft score used only to prioritize scanning order when
`max_symbols_scanned_concurrently` is smaller than the eligible universe; it
never excludes an otherwise-eligible coin.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from tradingbot.config import UniverseConfig
from tradingbot.data.exchange_client import ExchangeClient
from tradingbot.data.models import Candle, ContractSpec, ContractStatus, OrderBookSnapshot


@dataclass(slots=True)
class ContractMetrics:
    quote_volume_24h_usd: float
    spread_bps: float | None
    depth_usd_bid_10bps: float
    depth_usd_ask_10bps: float
    last_price: float
    price_age_seconds: float
    realized_vol_1h_bps: float | None
    contract_age_days: float | None


@dataclass(slots=True)
class UniverseEntry:
    spec: ContractSpec
    metrics: ContractMetrics
    eligible: bool
    rejection_reasons: list[str] = field(default_factory=list)
    liquidity_score: float = 0.0

    @property
    def symbol(self) -> str:
        return self.spec.symbol


class UniverseDiscovery:
    """Scans the exchange's full perpetual universe and applies eligibility rules."""

    def __init__(self, client: ExchangeClient, config: UniverseConfig) -> None:
        self.client = client
        self.config = config

    async def scan(self) -> list[UniverseEntry]:
        specs = await self.client.fetch_contract_specs()
        semaphore = asyncio.Semaphore(self.config.max_symbols_scanned_concurrently)

        async def bound_eval(spec: ContractSpec) -> UniverseEntry | None:
            async with semaphore:
                try:
                    return await self._evaluate(spec)
                except Exception as exc:  # noqa: BLE001 - one bad symbol must not kill the scan
                    return UniverseEntry(
                        spec=spec,
                        metrics=ContractMetrics(0, None, 0, 0, 0, 1e9, None, None),
                        eligible=False,
                        rejection_reasons=[f"data_fetch_error: {exc!r}"],
                    )

        results = await asyncio.gather(*(bound_eval(s) for s in specs))
        entries = [r for r in results if r is not None]
        entries.sort(key=lambda e: e.liquidity_score, reverse=True)
        return entries

    async def _evaluate(self, spec: ContractSpec) -> UniverseEntry:
        reasons: list[str] = []

        if spec.quote not in self.config.quote_currencies:
            reasons.append(f"quote_currency_not_supported:{spec.quote}")
        if self.config.exclude_coin_margined and spec.is_coin_margined:
            reasons.append("coin_margined_excluded_by_config")
        if spec.status != ContractStatus.TRADING:
            reasons.append(f"contract_status:{spec.status.value}")

        # Fetch fresh order book + recent candles for liquidity/volatility/age.
        book: OrderBookSnapshot = await self.client.fetch_order_book(spec.symbol, depth=50)
        candles: list[Candle] = await self.client.fetch_ohlcv(spec.symbol, timeframe="1m", limit=120)

        now_ms = int(time.time() * 1000)
        price_age_seconds = max(0.0, (now_ms - book.local_ts_ms) / 1000.0)
        last_price = book.mid_price or (candles[-1].close if candles else 0.0)

        quote_volume_24h_usd = 0.0
        if candles:
            # 1m candles for the last 120 minutes as a liquidity proxy; a full
            # 24h figure would need a longer fetch, deliberately kept light
            # here since this runs on every refresh cycle for every symbol.
            recent_quote_vol = sum(c.quote_volume for c in candles)
            quote_volume_24h_usd = recent_quote_vol * (1440 / max(len(candles), 1))

        spread_bps = book.spread_bps
        depth_bid = book.depth_within_bps("bid", 10)
        depth_ask = book.depth_within_bps("ask", 10)

        realized_vol_1h_bps = None
        if len(candles) >= 2:
            returns = [
                (candles[i].close / candles[i - 1].close - 1.0)
                for i in range(1, len(candles))
                if candles[i - 1].close > 0
            ]
            if returns:
                mean = sum(returns) / len(returns)
                var = sum((r - mean) ** 2 for r in returns) / max(len(returns) - 1, 1)
                realized_vol_1h_bps = (var ** 0.5) * 10_000

        contract_age_days = None
        if spec.listed_at_ms:
            contract_age_days = (now_ms - spec.listed_at_ms) / (1000 * 3600 * 24)

        metrics = ContractMetrics(
            quote_volume_24h_usd=quote_volume_24h_usd,
            spread_bps=spread_bps,
            depth_usd_bid_10bps=depth_bid,
            depth_usd_ask_10bps=depth_ask,
            last_price=last_price,
            price_age_seconds=price_age_seconds,
            realized_vol_1h_bps=realized_vol_1h_bps,
            contract_age_days=contract_age_days,
        )

        if quote_volume_24h_usd < self.config.min_quote_volume_24h_usd:
            reasons.append(
                f"quote_volume_too_low:{quote_volume_24h_usd:.0f}<{self.config.min_quote_volume_24h_usd:.0f}"
            )
        if spread_bps is None:
            reasons.append("no_spread_data")
        elif spread_bps > self.config.max_spread_bps:
            reasons.append(f"spread_too_wide:{spread_bps:.2f}bps>{self.config.max_spread_bps}bps")
        if min(depth_bid, depth_ask) < self.config.min_orderbook_depth_usd_within_10bps:
            reasons.append(
                f"insufficient_depth:{min(depth_bid, depth_ask):.0f}<{self.config.min_orderbook_depth_usd_within_10bps:.0f}"
            )
        if price_age_seconds > self.config.max_price_staleness_seconds:
            reasons.append(f"stale_price:{price_age_seconds:.1f}s")
        if contract_age_days is not None and contract_age_days < self.config.min_contract_age_days:
            reasons.append(f"contract_too_new:{contract_age_days:.1f}d")

        liquidity_score = self._score(metrics)
        return UniverseEntry(spec=spec, metrics=metrics, eligible=not reasons, rejection_reasons=reasons, liquidity_score=liquidity_score)

    @staticmethod
    def _score(m: ContractMetrics) -> float:
        """Ranking-only composite score, log-scaled so mega-cap volume doesn't
        completely dominate ordering. Never used as an eligibility gate."""
        import math

        vol_component = math.log10(max(m.quote_volume_24h_usd, 1.0))
        depth_component = math.log10(max(min(m.depth_usd_bid_10bps, m.depth_usd_ask_10bps), 1.0))
        spread_penalty = (m.spread_bps or 50.0)
        return vol_component * 2.0 + depth_component * 1.5 - spread_penalty * 0.05
