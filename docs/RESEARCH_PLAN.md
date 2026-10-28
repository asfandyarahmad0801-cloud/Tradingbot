# Market Inefficiency Discovery Engine — Research Plan & Architecture

Status: **Stage 1–5 (partial).** This document covers the architecture, what data
actually exists, the validation methodology, the main failure modes, and the
first milestone. Results live in `research/M1_RESULTS.md` (generated) and
`research/registry.jsonl` (append-only).

## 0. Starting point and what changed

The repository already contained a scalping framework (`setups/`, `signal_engine/`,
`risk/`, `backtest/`, `execution/`). An audit of it against this brief found
three problems that make it unsuitable as the *decision* layer as-is:

1. **Win probabilities are not estimated** — `win_probability_from_confidence`
   maps a self-reported 0–100 confidence to 30–65%. Every EV figure built on
   it is a heuristic, not evidence.
2. **Its backtests run on synthetic microstructure** (`synthetic_microstructure.py`
   fabricates order books and splits candles into fake taker trades). Order-flow
   setups evaluated that way say nothing about real markets.
3. **No walk-forward harness, no multiple-testing control, no random-timing
   null** — so a profitable backtest cannot be told apart from luck or market drift.

Its risk, leverage, sizing and broker code is reasonable and is kept for later
stages. The new research layer sits beside it and must *earn* each strategy a
place in it: nothing reaches the decision engine without passing the protocol below.

## 1. Architecture

```
                         ┌──────────────── RESEARCH (offline) ────────────────┐
data_ingestion/          │ research/dataset.py   point-in-time panel (avail_ts)│
  binance_vision.py ───► │ research/features.py  causal, trailing-normalised   │
  (sha256-verified,      │ research/hypotheses.py pre-registered specs + grids │
   manifest.jsonl)       │ research/evaluate.py  taker fills, delay, funding,  │
data_quality/checks.py ─►│                       random-timing null            │
                         │ research/stats.py     NW-HAC t, block bootstrap, BH │
                         │ research/protocol.py  discovery → validation → test │
                         │ research/registry.py  append-only experiment log    │
                         └───────────────┬────────────────────────────────────┘
                                         │ only 'accepted_for_paper' specs
                                         ▼
     (Stage 6+)  meta-controller ─► agents (regime, liquidity, derivatives,
                 price-response, cross-market, macro, auditor) ─► decision
                 record ─► RISK CONTROLLER (veto, deterministic) ─► execution
                 optimiser ─► paper broker │ live broker (disabled, gated)
```

Design rules:

* **One time convention:** every row is keyed by when it became *available*
  (`avail_ts`). Features at T use rows ≤ T only; trades enter at T + delay.
* **No full-sample statistics anywhere** — z-scores and percentiles are trailing.
* **Research and live share feature code**, so a signal can't pass research via
  a code path production won't run.
* **The risk controller is deterministic and independent.** ML/meta layers may
  propose; they can never resize past or override risk limits.

## 2. Data: what actually exists (verified from this environment, 2026-10-28)

| Source | Reachable | What we use | Gaps / limits |
|---|---|---|---|
| data.binance.vision (public archive) | ✅ | USDT-M perp 1m klines **incl. taker-buy volume**, premium-index 1m klines, funding settlements, 5m open interest + long/short ratios, spot 1m klines | No liquidation history (dataset withdrawn). No L2 / quote history (bookTicker gone; `bookDepth` = ±1–5% cumulative depth every ~30s only). Premium index has two missing whole days. |
| Binance REST/WS (api/fapi.binance.com) | ❌ HTTP 451 (geo-block) | — | Live paper trading must use another venue or run from another region. |
| OKX public REST | ✅ | candidate venue for live funding/OI/book data & cross-exchange checks | History depth limited. |
| Bybit | ❌ 403 | — | |
| Hyperliquid info API | ✅ (POST) | candidate cross-venue funding/L2 | |
| Coinbase, Kraken, Deribit | ✅ | spot reference, options vol (Deribit) | |
| Macro calendar (CPI/FOMC) | ❌ no feed configured | — | **Marked unavailable.** No macro data is fabricated. |

Milestone-1 dataset: BTC, ETH, SOL, XRP, DOGE perps, 2023-01 → 2026-09, 7,610 files, every
file SHA-256 checked against Binance's published checksum, recorded in `data/raw/manifest.jsonl`.
Reproduce with `scripts/fetch_research_data.py`.

Survivorship note: the five symbols were chosen as the most liquid perps that existed
for the whole window. That is a selection made with hindsight; results on them are
not evidence about the alt universe at large.

## 3. Hypotheses (pre-registered in `research/hypotheses.py`)

Ranked by prior plausibility of surviving *after costs*, given the available data:

| ID | Hypothesis | Competing explanation (registered as opposite variant) | Holding |
|---|---|---|---|
| H01 | Extreme funding → returns against the crowd | Funding is momentum | 8–24h |
| H03 | Price move on falling OI fades; on rising OI continues | OI is hedging noise | 1–4h |
| H07 | Large 1h/4h moves overshoot and revert | Moves are information → momentum | 1–4h |
| H08 | OI flush + big move (liquidation proxy) reverts | Regime break continues | 1–4h |
| H04 | Aggressive flow that fails to move price is absorbed → fade | Accumulation → break in flow direction | 30m–2h |
| H05 | Volatility compression → breakout follows | Breakouts from quiet ranges are sweeps → fade | 4–12h |
| H02 | Perp premium dislocation mean-reverts via perp | Premium leads spot | 1–4h |
| H06 | Alts lag BTC at 30m | Lag is seconds-scale, gone at 5m+ (cost-realism check) | 15m–1h |
| B01/B02 | Baselines: daily TS-momentum, always-long | — | 24h |

Every spec documents mechanism, data, exact signal, when it should work/fail, why it
might not be arbitraged, and what refutes it.

Deferred (data not available for honest testing yet): order-book imbalance/resiliency,
spread widening, real liquidation clusters, cross-exchange dislocations, macro event
reactions. These need forward-collected data (Stage 3b recorder) — they will not be
"tested" on synthetic proxies.

## 4. Validation methodology

1. **Chronological splits:** discovery 2023-01→2024-12, validation 2025-01→2025-09,
   locked test 2025-10→2026-09. Features are causal so the windows need no refitting.
2. **Execution realism:** decision at bar close; fill at the 1m close one minute later;
   taker fees (5 bps/side, VIP0) + assumed half-spread/slippage (1 bp BTC/ETH, 2 bps
   others); realised funding at each settlement; non-overlapping positions per symbol;
   time-based exits only (no intrabar stop-sequencing flattery); MAE/MFE recorded.
3. **Null = random timing,** not zero: same number of longs/shorts per symbol placed at
   random valid times in the same window. Controls for market drift and for side bias.
4. **Inference:** Newey–West HAC t, moving-block bootstrap CI, BH-FDR (q = 0.10) across
   *every* variant in discovery (baselines excluded), Holm at validation.
5. **Robustness gates:** positive net at 1.5× costs; positive in every discovery year
   with ≥10 trades; positive on ≥50% of symbols.
6. **Maker-fee bound** reported for information only — never used to accept anything,
   because non-fills and adverse selection are not modelled.
7. **Registry:** every variant at every stage appended to `research/registry.jsonl`
   with commit, dataset fingerprint, cost model, and rules.

Tests (`tests/test_research_pipeline.py`) verify: causal features under truncation,
as-of joins never see the future, exact trade/fee/funding accounting, no position
overlap, random signals on random walks reject at ~nominal rate, and a planted
edge is detected.

## 5. Principal risks and failure modes

* **Costs dominate.** A round trip is ~12–14 bps at taker rates. Most short-horizon
  predictability in liquid crypto is smaller than that. Expect most hypotheses to die here.
* **Regime dependence.** 2023–2026 contains a bull cycle; long-biased signals look good
  against zero. The random-timing null exists for exactly this.
* **Data limitations.** No L2/liquidations: order-book hypotheses are untestable until we
  record our own data; OI is 5-minute, and its stamp convention is undocumented (we lag it
  a full period to be safe).
* **Selection bias:** five liquid survivors; small hypothesis grid still means ~60 tests.
* **Geo-blocking:** Binance live endpoints are blocked from this environment, so paper
  trading must use a different venue (OKX/Hyperliquid) — whose costs and microstructure
  differ from the research venue. Any strategy must be re-validated on the venue it trades.
* **Model risk later:** meta-controllers and ML can overfit far more easily than the
  rule specs here. They will be held to the same protocol and must beat the simple
  version out-of-sample to be used.

## 6. Milestone 1 (this change)

Deliverable: a reproducible, tested pipeline that can say **no** credibly, run on real
data over all pre-registered hypotheses. Done when: data is checksum-verified and
quality-audited; tests pass (including the noise/planted-edge calibration tests); the
protocol has produced a verdict for every variant; results and failures are registered.
See `research/M1_RESULTS.md` and the findings summary in `docs/M1_FINDINGS.md`.
