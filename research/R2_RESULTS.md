# Milestone 1 — Research Results (auto-generated)

Generated 2026-10-28T19:48:40Z · commit `ff808ea7b61387ed7178a39bda8833149fd9933b` · dataset `185bfebae5e5e198`

Costs (base): taker 5.0 bps/side + half-spread/slippage per side (BTC/ETH 1.0, others 2.0); stressed ×1.5. Entry 1 min after decision; time-based exit; realised funding charged.

Splits: {'discovery': ('2023-01-01', '2025-01-01'), 'validation': ('2025-01-01', '2025-10-01'), 'test': ('2025-10-01', '2026-10-01')}. Multiple-testing family size (discovery): 6.

## Verdict summary

| ID | Name | Params | Verdict | Disc. n | Disc. gross bps | Disc. net bps | Excess vs random bps | p(random) | BH adj | Maker-bound net | Reasons |
|---|---|---|---|---|---|---|---|---|---|---|---|
| H09 | mean_reversion_composite | `{"k": 1.5, "horizon_min": 240, "entry": "taker", "offset_bps": 5.0, "window_min": 15}` | **rejected_discovery** | 2152 | 9.20 | -3.64 | 9.23 | 0.009 | 0.054 | 5.43 | non-positive mean net return after costs |
| H09 | mean_reversion_composite | `{"k": 1.5, "horizon_min": 240, "entry": "limit", "offset_bps": 5.0, "window_min": 15}` | **rejected_discovery** | 1929 | -1.05 | -9.32 | 1.88 | 0.298 | 0.420 | -4.79 | non-positive mean net return after costs |
| H09 | mean_reversion_composite | `{"k": 2.0, "horizon_min": 240, "entry": "taker", "offset_bps": 5.0, "window_min": 15}` | **rejected_discovery** | 1006 | 2.18 | -10.57 | 2.15 | 0.350 | 0.420 | -1.52 | non-positive mean net return after costs |
| H09 | mean_reversion_composite | `{"k": 2.0, "horizon_min": 240, "entry": "limit", "offset_bps": 5.0, "window_min": 15}` | **rejected_discovery** | 900 | -9.20 | -17.43 | -6.38 | 0.888 | 0.888 | -12.90 | non-positive mean net return after costs |
| H10 | passive_entry_reversal | `{"base": "H07", "horizon_min": 240, "entry": "limit", "offset_bps": 5.0, "window_min": 15}` | **rejected_discovery** | 942 | -0.70 | -9.02 | 3.09 | 0.280 | 0.420 | -4.45 | non-positive mean net return after costs |
| H10 | passive_entry_reversal | `{"base": "H02", "horizon_min": 240, "entry": "limit", "offset_bps": 5.0, "window_min": 15}` | **rejected_discovery** | 592 | -0.56 | -8.47 | 5.43 | 0.204 | 0.420 | -3.93 | non-positive mean net return after costs |

## Per-stage detail (only stages actually run are shown)

| Variant | Stage | n | gross bps | net bps | win | PF | Sharpe(d) | MDD bps | p(NW) | p(random) |
|---|---|---|---|---|---|---|---|---|---|---|
| H09 {"k": 1.5, "horizon_min": 240, "entry": "taker", "offset_bps": 5.0, "window_min": 15} | discovery | 2152 | 9.20 | -3.64 | 53.8% | 0.96 | -0.33 | -17059 | 0.628 | 0.009 |
| H09 {"k": 1.5, "horizon_min": 240, "entry": "limit", "offset_bps": 5.0, "window_min": 15} | discovery | 1929 | -1.05 | -9.32 | 52.8% | 0.89 | -0.79 | -22119 | 0.273 | 0.298 |
| H09 {"k": 2.0, "horizon_min": 240, "entry": "taker", "offset_bps": 5.0, "window_min": 15} | discovery | 1006 | 2.18 | -10.57 | 52.8% | 0.89 | -0.64 | -16267 | 0.363 | 0.350 |
| H09 {"k": 2.0, "horizon_min": 240, "entry": "limit", "offset_bps": 5.0, "window_min": 15} | discovery | 900 | -9.20 | -17.43 | 52.0% | 0.82 | -1.04 | -16094 | 0.164 | 0.888 |
| H10 {"base": "H07", "horizon_min": 240, "entry": "limit", "offset_bps": 5.0, "window_min": 15} | discovery | 942 | -0.70 | -9.02 | 52.9% | 0.91 | -0.48 | -14900 | 0.496 | 0.280 |
| H10 {"base": "H02", "horizon_min": 240, "entry": "limit", "offset_bps": 5.0, "window_min": 15} | discovery | 592 | -0.56 | -8.47 | 47.6% | 0.90 | -0.36 | -10152 | 0.616 | 0.204 |

## Data quality

| Series | rows | coverage | missing steps | dups | largest gap (min) | ok |
|---|---|---|---|---|---|---|
| BTCUSDT perp 1m klines | 1971360 | 1.00000 | 0 | 0 | 0 | True |
| BTCUSDT premium 1m | 1968464 | 0.99853 | 2896 | 0 | 1441 | False |
| BTCUSDT funding | 4107 | 1.00000 | 0 | 0 | 0 | True |
| BTCUSDT metrics 5m | 394139 | 0.99966 | 133 | 0 | 630 | True |
| ETHUSDT perp 1m klines | 1971360 | 1.00000 | 0 | 0 | 0 | True |
| ETHUSDT premium 1m | 1968464 | 0.99853 | 2896 | 0 | 1441 | False |
| ETHUSDT funding | 4107 | 1.00000 | 0 | 0 | 0 | True |
| ETHUSDT metrics 5m | 394139 | 0.99966 | 133 | 0 | 630 | True |
| SOLUSDT perp 1m klines | 1971360 | 1.00000 | 0 | 0 | 0 | True |
| SOLUSDT premium 1m | 1968464 | 0.99853 | 2896 | 0 | 1441 | False |
| SOLUSDT funding | 4107 | 1.00000 | 0 | 0 | 0 | True |
| SOLUSDT metrics 5m | 394122 | 0.99962 | 150 | 0 | 630 | True |
| XRPUSDT perp 1m klines | 1971360 | 1.00000 | 0 | 0 | 0 | False |
| XRPUSDT premium 1m | 1968464 | 0.99853 | 2896 | 0 | 1441 | False |
| XRPUSDT funding | 4107 | 1.00000 | 0 | 0 | 0 | True |
| XRPUSDT metrics 5m | 394139 | 0.99966 | 133 | 0 | 630 | True |
| DOGEUSDT perp 1m klines | 1971360 | 1.00000 | 0 | 0 | 0 | True |
| DOGEUSDT premium 1m | 1968464 | 0.99853 | 2896 | 0 | 1441 | False |
| DOGEUSDT funding | 4107 | 1.00000 | 0 | 0 | 0 | True |
| DOGEUSDT metrics 5m | 394139 | 0.99966 | 133 | 0 | 630 | True |
