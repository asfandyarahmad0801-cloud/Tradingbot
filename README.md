# Leveraged Crypto Perpetual-Futures Scalping — Research & Execution Framework

A modular framework for scanning the full eligible perpetual-futures
universe on an exchange, detecting risk-controlled short-horizon scalping
setups, sizing and leveraging them safely, and executing them in backtest,
paper, or live mode through the same code path.

**This is a research and execution framework, not a profit guarantee.**
See `docs/LIMITATIONS.md` for what is and isn't implemented/validated, and
read `docs/RESEARCH.md` for the reasoning behind each signal and setup
before trusting any of it with real capital.

## Why this design

- **Trade every qualifying setup, on any coin** — the universe is
  discovered and filtered dynamically (`universe/discovery.py`) against
  objective liquidity/spread/depth/age criteria, never a fixed symbol list.
  A setup is not skipped just because the coin is small-cap; it's skipped
  only when it fails an explicit, logged check.
- **No-trade is the default.** A signal only becomes an order after passing
  setup-specific confirmation, a positive-expected-value check net of fees/
  slippage/funding, a safe leverage/liquidation-distance check, and every
  portfolio-level risk limit. Every rejection is logged with its reason.
- **Leverage is a risk amplifier, never an edge generator** — it's selected
  to keep the liquidation price a configurable multiple of the stop
  distance away, not maximized for a given setup.
- **Backtest, paper, and live share the same setup/risk/expectancy code.**
  Only the data source and the broker differ, so a strategy can't "pass"
  backtest through a code path live trading doesn't share.

See `docs/ARCHITECTURE.md` for the full pipeline diagram and rationale.

## Folder structure

```
config/config.yaml          Non-secret operating parameters (conservative defaults)
.env.example                 Secret/credential template (copy to .env)
src/tradingbot/
  config.py                  Config + secrets loading
  data/                       Data models, ccxt exchange client, data-quality validation
  universe/                   Dynamic perpetual-contract discovery, filtering, ranking
  features/                   Volatility, order-flow, market-structure, derivatives,
                               indicators, pump/dump detection
  regime/                     Market-wide & per-coin regime classification
  setups/                     Setup base class + 6 concrete scalping setups + registry
  signal_engine/               Multi-factor scoring, expectancy/EV, human-readable explanations
  risk/                        Leverage selection, position sizing, portfolio limits/kill switch,
                               correlation clustering
  backtest/                    Event-driven no-lookahead backtester, metrics, Monte Carlo
  execution/                   Broker interface, paper broker, live broker, order manager
  scanner/                     Orchestrates universe -> data -> features -> setups -> risk -> execution
  storage/                     SQLAlchemy models + repository (trades, decisions, risk/data-quality events)
  monitoring/                  Alerting (Telegram/Discord)
  dashboard/                   Streamlit monitoring dashboard
  main.py                      CLI entrypoint (backtest / paper / live)
tests/                         pytest suite
docs/                          ARCHITECTURE.md, RESEARCH.md, LIMITATIONS.md, SECURITY.md
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill in exchange API keys (read+trade only, NEVER withdrawal)
```

Edit `config/config.yaml` for exchange selection, universe filters, risk
limits, and expectancy thresholds. Defaults are intentionally conservative
(paper mode, low leverage caps, small risk-per-trade, tight portfolio
exposure limits) — see `docs/SECURITY.md` before ever widening them.

## Running the test suite

```bash
python -m pytest -q
```

62 tests cover leverage/liquidation math, position sizing, expectancy
(including funding proration), risk-limit enforcement, data-quality
validation, feature calculations, individual setup detection logic,
universe filtering, correlation clustering, and a no-lookahead guarantee
test for the backtester (verifies that truncating future data never changes
trades opened before the truncation point).

## Backtesting

The backtester reads local CSV history (one file per symbol:
`timestamp,open,high,low,close,volume`, one row per 1-minute bar):

```bash
python -m tradingbot.main backtest --data-dir ./data/historical --starting-equity 10000
```

This prints a performance summary, breakdowns by symbol/setup/exit-reason,
and a Monte Carlo resample of the realized trade outcomes. **Read
`docs/LIMITATIONS.md` first** — without real historical order-book/trade
data supplied, the backtester approximates microstructure from OHLCV,
which is indicative only for order-flow-heavy setups.

## Paper trading

```bash
python -m tradingbot.main paper
```

Runs continuously against live market data with simulated fills (fees,
slippage, latency, partial fills, rejection probability, and genuine
resting stop/take-profit trigger orders). This is the default, safe mode —
no real orders are ever placed. Requires network access to the configured
exchange's public market-data endpoints.

## Live trading

```bash
python -m tradingbot.main live --i-understand-live-risk
```

Refuses to start unless `mode: live` is also set in `config/config.yaml` —
a deliberate double confirmation. **Before running this against real
capital:** run the full test suite, run a backtest, run paper trading for a
meaningful period and review its trade log, and read `docs/SECURITY.md` and
`docs/LIMITATIONS.md` in full. Start with the smallest possible risk-per-
trade and leverage caps in `config.yaml`, and monitor actively — this
system has not been run against a live exchange in its development to
date (see LIMITATIONS.md).

## Monitoring dashboard

```bash
streamlit run src/tradingbot/dashboard/app.py -- --database-url sqlite:///./tradingbot.db
```

Shows equity curve, open positions, PnL by setup/symbol, recent no-trade/
rejected decisions, risk events, data-quality events, and the latest
universe scan — all read from the same database the scanner writes to.

## Realistic expectations

This system does not predict the market with certainty, does not
guarantee profitability, does not guarantee avoidance of liquidation, and
does not have access to any non-public information. It is built around
probability, expectancy, risk control, and execution quality — see
`docs/RESEARCH.md` for what each signal can and cannot tell you, and
`docs/LIMITATIONS.md` for what remains unvalidated. Leverage amplifies
losses exactly as much as gains; treat every default risk limit in
`config/config.yaml` as a ceiling to loosen deliberately and gradually,
never a starting point to maximize.
