# Known Limitations

This build is a research and execution **framework**, not a finished,
validated trading strategy. Read this before trusting any number it
produces.

## Scope not implemented in this pass

The design brief (63 sections) describes a full institutional-scale system.
This build implements the core pipeline end-to-end with real, tested logic
for: universe discovery, data validation, feature engineering, regime
classification, 6 concrete scalping setups, multi-factor scoring,
expectancy/EV, leverage selection, position sizing, portfolio risk limits
and kill switch, correlation clustering, an event-driven no-lookahead
backtester with Monte Carlo, paper and live brokers with mandatory stop
protection, a database-backed audit trail, a monitoring dashboard, and a
test suite. The following are **not** implemented and are stub interfaces
or explicitly out of scope for this pass:

- **News/sentiment/on-chain/macro data providers.** `Secrets` has fields
  for these API keys and `signal_engine/scorer.py` has neutral (score=50)
  slots reserved for them, but no provider integration exists yet. These
  are paid data sources (see docs/RESEARCH.md) that need real credentials
  and an operator decision about which vendor to use.
- **Setups 8–20 from the spec's list of 20** (short/long squeeze
  continuation as distinct from liquidation-reversal, cross-exchange
  dislocation, CVD-price divergence as its own setup, news-driven momentum,
  etc.) are not separately implemented. Six setups are implemented with
  real entry/stop/target/invalidation logic; the `Setup` base class and
  `setups/registry.py` make adding more mechanical, not architectural.
- **Machine-learning probability models** (spec section 38) are not
  trained. `win_probability_from_confidence()` is an explicitly-labeled
  conservative heuristic, not a calibrated model — replacing it with a
  setup-specific, walk-forward-validated hit rate from real backtest
  results is the natural next step once historical data is available.
- **Walk-forward validation harness** (train/validate/test rolling windows)
  is described in RESEARCH.md as the intended methodology but no automated
  harness is implemented yet; `backtest/engine.py` runs a single pass over
  whatever data it's given, and the caller is responsible for splitting
  data chronologically.
- **Multi-exchange comparison** (spec section 32) is not implemented; the
  system operates against one configured exchange at a time.

## Backtester approximations (spec section 33 is explicit that these must be documented)

- **No real historical order-book or tick data is fetched.** Most public
  APIs don't offer historical L2/tick data at scale for free.
  `backtest/synthetic_microstructure.py` approximates an order book (fixed
  assumed spread/depth) and taker trades (split from each OHLCV bar,
  weighted by how much of the bar's range the candle body occupied) when
  real order-book/trade history isn't supplied. **This means backtest
  results for order-flow-heavy setups (momentum continuation, liquidation
  reversal) are indicative only** — pass real historical trade/L2 data into
  `BacktestEngine.run` instead when you have it; the setup code is
  identical either way.
- **Partial fills and queue position are not modeled** in the backtester
  (the paper broker does simulate partial fills and rejection
  probabilistically, but the backtester assumes full fills at the modeled
  price).
- **Intrabar sequencing is a conservative assumption**: if a bar's
  high/low would hit both the stop and a take-profit, the stop is checked
  first (worse outcome assumed). This is deliberately pessimistic, not
  necessarily what happened.
- **Take-profit levels close the full remaining position at the first
  level touched**, rather than true partial fills across multiple TP
  prices, because OHLCV alone cannot reconstruct intrabar fill order.
- **Funding is approximated** as `funding_bps_per_8h * (holding_hours / 8)`
  rather than applied at exact historical funding timestamps with the
  period's actual realized rate, since a constant assumed rate is what's
  configured absent real historical funding-rate history.
- **Confirmation/context timeframe candles** (`candles_confirm_tf` /
  `candles_context_tf` in `MarketSnapshot`) are populated with lightly
  down-sampled slices of the same base series in the backtester rather than
  true resampled multi-timeframe candles; none of the six implemented
  setups currently read them (they exist for future multi-timeframe
  confirmation logic), so this doesn't affect current results, but a new
  setup that reads them should use `backtest/synthetic_microstructure.resample_candles`
  instead.
- **Performance**: the backtester is O(n) per event with several feature
  recomputations per bar; it has not been profiled or optimized for
  very large multi-year, multi-symbol runs.

## Paper trading approximations

- The paper broker correctly simulates fees, slippage, latency, rejection,
  and partial fills for the entry leg, and holds stop/take-profit orders as
  genuine resting trigger orders that only fill once `check_pending_triggers`
  observes price crossing the trigger (via `Scanner.position_monitor_loop`).
  It does **not** simulate order-book-depth-dependent slippage (slippage is
  a fixed configured bps, not derived from walking the actual book), and it
  does not model exchange downtime/maintenance windows.

## Live trading gaps

- `LiveBroker` requires `confirm_live=True` and the CLI requires
  `--i-understand-live-risk` plus `mode: live` in config — but this build
  has **not been run against a real exchange** in this session (no network
  egress / API credentials available in this development environment).
  Treat `LiveBroker` as implemented-but-unverified-against-a-real-exchange
  until it has been tested on an exchange testnet first.
- **Position reconciliation after restart** (spec section 44) is partially
  covered — `LiveBroker.get_position` exists and the scanner can be
  extended to call it on startup — but an automated "refuse to trade until
  reconciled" startup routine is not wired into `main.py` yet.
- **Real exchange conditional (stop/TP) order behavior** varies by exchange
  (mark-price vs. last-price triggers, etc.); `order_manager.py` places
  `STOP_MARKET` / `TAKE_PROFIT_MARKET` reduce-only orders through the
  standard ccxt order interface, but exchange-specific trigger semantics
  have not been individually verified.

## Why Python, and where it stops being enough

Python (with ccxt, asyncio, numpy) is adequate for the horizons this system
targets — seconds to low minutes — because the bottleneck at that horizon
is decision quality and risk discipline, not microsecond execution. It is
**not** adequate for genuine sub-second/HFT-style execution: Python's GIL,
ccxt's REST-first design, and garbage-collection pauses introduce
tens-to-hundreds of milliseconds of jitter that would dominate any edge at
that horizon. If the strategy ever needs sub-second execution, the
data-ingestion and order-submission hot path (not the research/backtest
code) would need to move to a compiled language with a direct exchange
WebSocket/FIX connection.

## Honesty note on expectancy figures

Every "expected value" figure this system computes before a real
setup-specific calibration exists is bounded by a deliberately conservative
heuristic (`win_probability_from_confidence`), not a validated prediction.
Do not treat any backtest Sharpe ratio or win rate produced against
synthetic-microstructure data as a claim about real-market performance —
run the backtester against real historical data (and, before risking real
capital, a real exchange testnet in paper mode) first.
