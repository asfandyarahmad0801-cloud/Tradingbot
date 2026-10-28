# Milestone 1 — Findings

Run: `research/registry.jsonl` (run id `m1-…`, 59 records), full tables in
`research/M1_RESULTS.md`. Data: Binance USDT-M BTC/ETH/SOL/XRP/DOGE, 1m klines,
premium index, funding, 5m OI, 2023-01 → 2026-09, all files checksum-verified.

## Bottom line

**No hypothesis survived discovery. Nothing is approved for paper trading.**
56 variants tested (+3 baselines); 0 passed the pre-registered gates. The
validation (2025-01→09) and test (2025-10→2026-09) windows were **never
evaluated** for any hypothesis, so they are still clean for future,
pre-registered work.

## What the data does say

1. **Real but small predictive information exists.** Several signals beat
   random timing at BH-adjusted p < 0.05 in discovery, and in every such case
   the registered *opposite* variant lost (p ≈ 0.98–1.0), i.e. the direction is
   consistent, not noise:

   | Signal | Gross bps/trade | Excess vs random | Net (taker) | Net (maker bound) |
   |---|---|---|---|---|
   | H07 fade 4h move >3σ, hold 4h | 13.7 | 14.7 | +0.8 | +9.9 |
   | H02 fade premium z>3.5, hold 4h | 10.6 | 14.0 | −1.9 | +7.2 |
   | H06 alt catches up to BTC, 1h | 6.4 | 6.3 | −7.4 | +2.4 |
   | H03 fade price-up-on-falling-OI, 1h | 6.1 | 5.6 | −7.1 | +2.0 |
   | H07 fade 4h move, hold 1h | 5.9 | 6.2 | −7.2 | +1.9 |

   The directional evidence favours **mean reversion after liquidity-driven
   moves** (H02, H03 short-covering, H07, H08) over continuation, and a real
   BTC→alt lag at 30–60 min (H06).

2. **Costs eat all of it.** A taker round trip is 12–14 bps; the edges are
   3–14 bps. This is the central finding: the problem is not detecting signal,
   it is *harvesting* it.

3. **Even the best taker-net candidate fails robustness.** H07 (4h/240m) nets
   +0.8 bps but is −14.8 bps in 2023 and negative at 1.5× costs. Its average
   adverse excursion is −261 bps per trade — a fragile, knife-catching profile.

4. **Funding contrarian (H01 k=3, 24h)** made +30 bps net on 242 trades, but
   +102 in 2023 and −30 in 2024, BH p = 0.14. Rejected; regime-dependent and
   too few independent events.

5. **Order-flow absorption (H04, the brief's example) shows nothing**: gross
   ≈ 0 in both directions at both thresholds. Taker share from 1m klines may
   simply be too coarse; this is not evidence against the idea with true
   tick/L2 data.

6. **Volatility compression breakouts (H05)**: weakly positive gross for
   *following* the break, never significant, never net positive.

7. **Baselines:** always-long earned +11 bps/day net (a bull-market artefact,
   not skill); daily long/short TS-momentum earned −13. Every rule tested lost
   to simply holding — which itself carries ~−285 bps average adverse excursion.

## Interpretation and what is *not* allowed next

It would be easy to now tweak thresholds until something passes. That would
be data snooping on the discovery window and is not permitted by the protocol:
any follow-up is a **new pre-registered hypothesis**, counted in a new family.

Credible next directions, ranked:

1. **Cost reduction, not more signals.** The mean-reversion signals are of the
   kind a *passive* liquidity provider is paid for. Test the same signals
   executed with resting limit orders — but only with a fill model that charges
   for adverse selection (fills conditional on price trading *through* the
   level, using 1m data, and later tick data). The maker-bound column above is
   the ceiling, not the expectation.
2. **Combine the independent weak signals** (H02, H03, H07, H06) into one
   score and test whether the *combination* clears costs out-of-sample
   (Agent 7). Registered as one hypothesis with a fixed combination rule
   (e.g. equal-weighted z), not a fitted model, at first.
3. **Longer horizons / lower turnover** for the funding signal, with more
   symbols to increase independent events.
4. **Forward-collect data we lack** (L2 snapshots, trades, liquidations,
   cross-venue funding) from venues reachable here (OKX, Hyperliquid) so the
   order-book hypotheses can be tested honestly.

## Known limitations of this milestone

- Time-exit only; no stop-loss logic yet (MAE shows it would matter).
- Costs are assumed, not measured from quotes; impact independent of size.
- Five liquid survivor symbols; no delisted coins.
- OI availability lagged a full 5 min by assumption; premium index missing 2 days.
- Registry rows record a `-dirty` commit (run before this commit was made);
  re-running `scripts/run_research.py` on this commit reproduces them exactly.
- Binance live endpoints are geo-blocked (HTTP 451) from this environment;
  paper trading (Stage 8) will need OKX or Hyperliquid and re-validation there.
