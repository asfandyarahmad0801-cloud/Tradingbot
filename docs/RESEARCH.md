# Phase 1 — First-Principles Research

This document answers the research questions the design brief requires
before writing implementation code. It draws on well-established market
microstructure concepts (order-flow imbalance, VWAP, liquidation mechanics)
and general, publicly-documented characteristics of crypto perpetual
futures markets. Anything presented as a specific historical statistic
("this setup wins X% of the time") would be a fabrication unless it comes
from this project's own backtests — so this document deliberately stays at
the level of mechanism and reasoning, and defers exact hit-rates and
Sharpe ratios to `backtest/metrics.py` output on real data, which nobody
has run yet in this session (no exchange/network access here — see
LIMITATIONS.md).

## 1–9. What is knowable, and through what channel

| Category | Examples | Latency class | Access |
|---|---|---|---|
| **Observable, real-time, free** | Order book (L2), executed trades, OHLCV, funding rate, open interest, mark/index price | Seconds or better | Public exchange REST/WS APIs (ccxt) |
| **Observable, free, delayed** | Liquidation feed (exchange-dependent), long/short ratio | Seconds–minutes | Public exchange APIs, coverage varies |
| **Derived** | ATR, RSI, VWAP, CVD, order-book imbalance, realized volatility, regime classification | Computed from the above | Local computation |
| **Probabilistic inference** | "This liquidation cluster looks exhausted", "this pump looks manipulated" | N/A | Heuristic classification calibrated against historical outcomes (must be backtested, not assumed) |
| **Observable, paid** | Deep historical L2/tick data, institutional order-flow, some on-chain analytics platforms, premium news feeds, curated social-sentiment scores | Varies | Paid vendors (Kaiko, Coinalyze, Glassnode, LunarCrush, etc.) — **not connected in this build** |
| **Unavailable / speculative** | Any specific market participant's intent, non-public order flow, insider information, the outcome of a not-yet-released macro print, "true" fair value | N/A | Never claim this is knowable |

This project never claims access to non-public information. Every feature
in `features/` is computed from data an exchange actually serves publicly,
or (for macro/news/on-chain) is designed to plug into named optional
providers via `Secrets` — and every such provider is a stub interface
until a real key is supplied, not a fabricated data source.

### Leading vs. lagging, by horizon

- **Sub-minute – 1m**: order-book imbalance, aggressive taker flow (CVD over
  5–30s windows), and liquidation prints are the closest things to
  "leading" at this horizon, because they represent real capital
  committing right now. Classic candle-based indicators (RSI, MACD) are
  lagging by construction (computed on already-closed bars) and are weak
  here — used only as supporting/contextual features, never triggers, per
  the design brief.
- **1–5m**: order flow still matters but decays; VWAP position, short-term
  structure (breakouts, swept liquidity), and funding/OI dislocations start
  to add information. This is the primary band the setups in `setups/`
  target.
- **5–15m**: higher-timeframe structure (support/resistance, session
  highs/lows), volatility regime, and BTC/ETH regime become more relevant.
  Liquidation-cascade exhaustion setups often need this much time to
  confirm the cascade has actually stopped.
- **15m+**: macro/news, sentiment shifts, and stablecoin-flow narratives
  operate on this horizon or slower; they are treated as **context/filter**
  signals (blackout windows, leverage reduction) rather than entry
  triggers for a scalping system.

### Noisy and easily-manipulated signals

- **Noisy**: single-trade prints, one-bar volume spikes, raw sentiment
  scores, any single indicator value in isolation.
- **Manipulable, in rough order of ease**: displayed order-book size
  (can be spoofed/cancelled in milliseconds — this is why the setups treat
  order-book depth as a filter, and lean on **executed trades** and
  **liquidations**, which cost real money to fake), social-media mention
  volume (bots), thin-orderbook "pumps" on low-cap alts, and — to a lesser
  extent — open interest on illiquid contracts. Funding rate and realized
  liquidations are harder to fake because they require real capital at
  risk, which is why `pump_dump.py` weights spread-expansion + large-trade
  concentration + genuine OI/funding shifts over raw social/volume
  numbers.

### Correlated signals (don't double-count)

RSI, Stochastic, and MACD are all derived from the same close-price series
and are highly correlated with each other and with simple momentum (ROC).
Several "different" order-flow metrics (CVD, taker imbalance, buy/sell
ratio) are also mathematically related transforms of the same buy/sell
volume split. The signal engine (`signal_engine/scorer.py`) explicitly
groups scoring by *independent information sources* (setup confidence,
liquidity/execution quality, volatility regime, BTC-regime alignment,
abnormal-move risk, macro/sentiment/on-chain) rather than summing every
individual indicator, precisely to avoid manufacturing false confidence out
of five correlated views of the same price series.

## 10. Distinguishing genuine demand from manipulation

No single signal does this reliably. The approach here (`pump_dump.py`,
`derivatives_features.classify_liquidation_event`) is to require
**multiple, cheaper-to-fake-independently** signals to agree: real trade
notional (not just displayed book size), spread behavior (manipulated books
often show abnormal spread widening as displayed liquidity is pulled),
open interest / funding response (fresh leveraged interest costs money to
put on), and liquidation flow (forced, not discretionary). None of this is
certain — it produces a risk *score*, not a verdict, and setups that trade
through elevated abnormal-move scores (breakout, liquidity-sweep,
liquidation-reversal) do so with tighter liquidity/spread gates, not by
ignoring the risk.

## 11. Avoiding overfitting to one coin/exchange/timeframe/regime

Structural choices made specifically for this: (a) setups are defined by
regime + structural conditions computed the same way for every symbol, not
per-symbol calibrated constants; (b) the backtester runs across whatever
symbol set is handed to it and reports **per-symbol** breakdowns
(`backtest/metrics.breakdown_by_symbol`) specifically so "it only works on
one coin" is visible rather than hidden in an aggregate number; (c) walk-
forward validation (train/validate/test, chronological, never shuffled) is
the intended validation methodology — see LIMITATIONS.md for what is and
isn't implemented yet; (d) Monte Carlo resampling
(`backtest/monte_carlo.py`) stress-tests whether a strategy's result could
plausibly be noise from a small trade sample.

## 12–13. Which scalping setups suit perpetuals, and which don't survive costs

Suitable: setups whose expected move is a multiple of the realistic
round-trip cost (spread + fees + slippage + prorated funding) —
implemented setups (`setups/`) target 1.3–1.5x realized cost as a *minimum*
gate (`min_reward_to_risk`), enforced by `signal_engine/expectancy.py`
before any order is placed. Unsuitable: any setup whose theoretical edge is
smaller than 2 x taker fee + typical spread + expected slippage — this is
mechanically rejected by `ExpectancyResult.passes()`, not left to
discretion. Very short/ultra-high-frequency setups (sub-second) are
explicitly **not** attempted here, since this stack's realistic tick-to-
trade latency (Python + REST/WS via ccxt) cannot compete at that horizon —
see the Python/latency discussion in LIMITATIONS.md.

## 14. Leverage's effect on stop distance / liquidation / sizing / EV

Leverage does not change the *notional* risk of a trade (sizing is
risk-based, off the stop distance, not off leverage — `risk/position_sizing.py`).
What leverage changes is **margin efficiency** and **liquidation
proximity**: higher leverage brings the liquidation price closer to entry
for the same margin, which is why leverage here is *selected*
(`risk/leverage.py`) to keep liquidation at least `N` stop-distances away —
never maximized. Leverage does not add expected value; it only changes how
much margin is consumed per unit of the (unchanged) directional bet, and
increases the consequence of being wrong about the stop's reliability
(gaps, slippage on the stop fill).

## 15. Scanning many coins without concentrated correlated exposure

BTC-beta dominates most altcoin short-term moves. `risk/correlation.py`
computes rolling pairwise correlations, clusters symbols via connected
components on the correlation graph, and the risk engine
(`risk/limits.py`) caps exposure *per cluster*, not just per symbol — five
correlated small-caps are risk-limited as (approximately) one position, not
five independent ones.

## What this build does NOT claim

- No claim of predicting the direction of any specific future price move
  with high confidence.
- No claim of access to non-public order flow, exchange internals, or
  regulator/Fed decisions before release.
- Every win-probability figure used before a real calibration exists
  (`signal_engine/expectancy.win_probability_from_confidence`) is an
  explicitly-labeled, conservative heuristic — not a validated forecast.
  Replacing it with a backtest-calibrated, setup-specific hit rate is the
  natural next step once historical data is connected (see LIMITATIONS.md).
