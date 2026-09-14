# Architecture

## Pipeline

```
universe/discovery.py          (dynamic perp contract discovery + filtering + ranking)
        |
data/exchange_client.py        (ccxt-based market data + orders)
data/validation.py             (data-quality gate: gaps, staleness, crossed books, outliers)
        |
features/*.py                  (volatility, orderflow, market structure, derivatives, indicators, pump/dump)
        |
regime/classifier.py           (trend x volatility x risk-flag classification, market-wide and per-coin)
        |
setups/*.py                    (per-setup entry/stop/target/invalidation logic; setups/base.py wraps
                                 regime/spread/liquidity/manipulation gating around every setup)
        |
signal_engine/scorer.py        (multi-factor confirmation score; NOT a re-decision of the setup)
signal_engine/expectancy.py    (fees + slippage + funding -> expected value in bps; hard gate)
        |
risk/leverage.py               (liquidation-distance-driven leverage selection)
risk/position_sizing.py        (risk-budget-based sizing, exchange lot/min-notional rounding)
risk/limits.py                 (portfolio hard limits + kill switch; final veto)
risk/correlation.py            (cluster exposure aggregation)
        |
execution/order_manager.py     (entry + MANDATORY protective stop/TP; emergency exit if stop fails)
execution/paper_broker.py      execution/live_broker.py    (same Broker interface)
        |
storage/db.py                  (every trade, decision, rejection, risk/data-quality event logged)
        |
scanner/scanner.py             (orchestrates all of the above per symbol, concurrently, on a cycle)
        |
dashboard/app.py               (reads the same database; no separate metrics pipeline)
```

`backtest/engine.py` re-uses the exact same setups, risk engine, leverage
selection, position sizing, and expectancy code as the live scanner — the
only things it swaps out are the broker (simulated fills against historical
bars) and, when real historical order-book/trade data isn't supplied, the
order-book/trade *inputs* (via `backtest/synthetic_microstructure.py`).

## Why this decomposition

- **One direction of data flow, no circular deps.** Each stage only depends
  on stages above it. `setups/` never imports `risk/`; `risk/` never
  imports `execution/`. This is what let the backtester reuse everything
  above `execution/` unmodified.
- **The setup decides IF to trade; the risk engine decides IF ALLOWED to
  trade.** These are separate concerns on purpose (spec priority hierarchy:
  capital preservation before opportunity capture) — a setup can never
  approve its own risk exception.
- **A signal is data, not an order.** `Signal` (setups/base.py) carries
  price levels and reasons; nothing about it causes an order until it has
  passed expectancy AND risk-limit checks. This is what makes "no-trade"
  the default and "trade" the exception that has to earn its way through
  several independent gates.
- **Same Broker interface for paper and live** (`execution/broker_base.py`)
  so the scanner code path is identical in both modes — the only thing
  that changes is which concrete broker `main.py` constructs, and live
  additionally requires an explicit `confirm_live=True` plus a CLI flag.

## Concurrency model

The scanner evaluates the eligible universe concurrently
(`asyncio.gather`, bounded by `universe.max_symbols_scanned_concurrently`)
so a slow/unhealthy symbol's API calls don't stall the rest of the scan.
Position *management* (paper trigger-order fills) runs as a second,
faster-interval loop (`Scanner.position_monitor_loop`) concurrently with
the scan loop, since protective orders need to be checked far more often
than a full universe re-scan.

## Data model boundary

`data/models.py` defines every cross-module data shape (`Candle`,
`OrderBookSnapshot`, `Trade`, `FundingRate`, `OpenInterest`, `Liquidation`,
`ContractSpec`). These are frozen dataclasses, not exchange-specific dicts
— `data/exchange_client.py` is the only module that translates raw ccxt
payloads into them, so every other module (features, setups, risk,
backtest) is exchange-agnostic by construction.
