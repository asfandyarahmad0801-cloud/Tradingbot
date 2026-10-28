# Milestone 1 — Research Results (auto-generated)

Generated 2026-10-28T19:43:52Z · commit `b16cf8bceb6b7123d768d359cdb13a9715fbe445-dirty` · dataset `185bfebae5e5e198`

Costs (base): taker 5.0 bps/side + half-spread/slippage per side (BTC/ETH 1.0, others 2.0); stressed ×1.5. Entry 1 min after decision; time-based exit; realised funding charged.

Splits: {'discovery': ('2023-01-01', '2025-01-01'), 'validation': ('2025-01-01', '2025-10-01'), 'test': ('2025-10-01', '2026-10-01')}. Multiple-testing family size (discovery): 56.

## Verdict summary

| ID | Name | Params | Verdict | Disc. n | Disc. gross bps | Disc. net bps | Excess vs random bps | p(random) | BH adj | Maker-bound net | Reasons |
|---|---|---|---|---|---|---|---|---|---|---|---|
| H01 | funding_crowding | `{"k": 2.0, "direction": 1, "horizon_min": 480}` | **rejected_discovery** | 815 | 6.77 | -4.70 | 9.21 | 0.135 | 0.397 | 4.51 | non-positive mean net return after costs |
| H01 | funding_crowding | `{"k": 2.0, "direction": 1, "horizon_min": 1440}` | **rejected_discovery** | 516 | 1.56 | -7.76 | 4.37 | 0.395 | 0.843 | 1.50 | non-positive mean net return after costs |
| H01 | funding_crowding | `{"k": 2.0, "direction": -1, "horizon_min": 480}` | **rejected_discovery** | 815 | -6.77 | -21.73 | -9.27 | 0.883 | 1.000 | -12.51 | non-positive mean net return after costs |
| H01 | funding_crowding | `{"k": 2.0, "direction": -1, "horizon_min": 1440}` | **rejected_discovery** | 516 | -1.56 | -18.76 | -4.84 | 0.607 | 0.895 | -9.50 | non-positive mean net return after costs |
| H01 | funding_crowding | `{"k": 3.0, "direction": 1, "horizon_min": 480}` | **rejected_discovery** | 358 | -2.25 | -13.30 | 2.35 | 0.422 | 0.843 | -4.09 | non-positive mean net return after costs |
| H01 | funding_crowding | `{"k": 3.0, "direction": 1, "horizon_min": 1440}` | **rejected_discovery** | 242 | 38.51 | 30.33 | 47.23 | 0.033 | 0.142 | 39.62 | BH-adjusted p=0.142 > q=0.1 |
| H01 | funding_crowding | `{"k": 3.0, "direction": -1, "horizon_min": 480}` | **rejected_discovery** | 358 | 2.25 | -13.13 | -2.80 | 0.589 | 0.895 | -3.91 | non-positive mean net return after costs |
| H01 | funding_crowding | `{"k": 3.0, "direction": -1, "horizon_min": 1440}` | **rejected_discovery** | 242 | -38.51 | -56.91 | -47.98 | 0.972 | 1.000 | -47.62 | non-positive mean net return after costs |
| H02 | premium_dislocation | `{"k": 2.5, "direction": 1, "horizon_min": 60}` | **rejected_discovery** | 4862 | 2.19 | -10.85 | 2.81 | 0.007 | 0.044 | -1.70 | non-positive mean net return after costs |
| H02 | premium_dislocation | `{"k": 2.5, "direction": 1, "horizon_min": 240}` | **rejected_discovery** | 1929 | 6.57 | -6.14 | 9.04 | 0.007 | 0.044 | 3.07 | non-positive mean net return after costs |
| H02 | premium_dislocation | `{"k": 2.5, "direction": -1, "horizon_min": 60}` | **rejected_discovery** | 4862 | -2.19 | -15.45 | -2.79 | 0.989 | 1.000 | -6.30 | non-positive mean net return after costs |
| H02 | premium_dislocation | `{"k": 2.5, "direction": -1, "horizon_min": 240}` | **rejected_discovery** | 1929 | -6.57 | -20.27 | -9.24 | 0.994 | 1.000 | -11.07 | non-positive mean net return after costs |
| H02 | premium_dislocation | `{"k": 3.5, "direction": 1, "horizon_min": 60}` | **rejected_discovery** | 1488 | 4.85 | -8.08 | 5.58 | 0.004 | 0.040 | 0.97 | non-positive mean net return after costs |
| H02 | premium_dislocation | `{"k": 3.5, "direction": 1, "horizon_min": 240}` | **rejected_discovery** | 625 | 10.58 | -1.86 | 14.02 | 0.014 | 0.071 | 7.20 | non-positive mean net return after costs |
| H02 | premium_dislocation | `{"k": 3.5, "direction": -1, "horizon_min": 60}` | **rejected_discovery** | 1488 | -4.85 | -18.02 | -5.50 | 0.995 | 1.000 | -8.97 | non-positive mean net return after costs |
| H02 | premium_dislocation | `{"k": 3.5, "direction": -1, "horizon_min": 240}` | **rejected_discovery** | 625 | -10.58 | -24.27 | -13.81 | 0.983 | 1.000 | -15.20 | non-positive mean net return after costs |
| H03 | oi_price_divergence | `{"k": 2.0, "case": "short_covering", "horizon_min": 60}` | **rejected_discovery** | 3603 | 4.09 | -9.08 | 3.66 | 0.005 | 0.040 | 0.02 | non-positive mean net return after costs |
| H03 | oi_price_divergence | `{"k": 2.0, "case": "short_covering", "horizon_min": 240}` | **rejected_discovery** | 2760 | 3.17 | -10.15 | 1.25 | 0.344 | 0.837 | -1.05 | non-positive mean net return after costs |
| H03 | oi_price_divergence | `{"k": 2.0, "case": "new_positions", "horizon_min": 60}` | **rejected_discovery** | 2688 | -3.67 | -17.01 | -4.27 | 0.996 | 1.000 | -7.76 | non-positive mean net return after costs |
| H03 | oi_price_divergence | `{"k": 2.0, "case": "new_positions", "horizon_min": 240}` | **rejected_discovery** | 2045 | -4.15 | -17.69 | -6.41 | 0.962 | 1.000 | -8.48 | non-positive mean net return after costs |
| H03 | oi_price_divergence | `{"k": 3.0, "case": "short_covering", "horizon_min": 60}` | **rejected_discovery** | 1627 | 6.06 | -7.07 | 5.63 | 0.002 | 0.037 | 1.97 | non-positive mean net return after costs |
| H03 | oi_price_divergence | `{"k": 3.0, "case": "short_covering", "horizon_min": 240}` | **rejected_discovery** | 1312 | 0.43 | -12.87 | -1.72 | 0.648 | 0.931 | -3.82 | non-positive mean net return after costs |
| H03 | oi_price_divergence | `{"k": 3.0, "case": "new_positions", "horizon_min": 60}` | **rejected_discovery** | 1167 | 2.41 | -11.03 | 1.67 | 0.261 | 0.671 | -1.76 | non-positive mean net return after costs |
| H03 | oi_price_divergence | `{"k": 3.0, "case": "new_positions", "horizon_min": 240}` | **rejected_discovery** | 960 | 9.83 | -3.81 | 7.11 | 0.090 | 0.336 | 5.40 | non-positive mean net return after costs |
| H04 | flow_absorption | `{"k": 2.0, "direction": 1, "horizon_min": 30}` | **rejected_discovery** | 5634 | -0.03 | -13.39 | -0.03 | 0.526 | 0.893 | -4.04 | non-positive mean net return after costs |
| H04 | flow_absorption | `{"k": 2.0, "direction": 1, "horizon_min": 120}` | **rejected_discovery** | 4450 | 0.09 | -13.25 | 0.17 | 0.465 | 0.863 | -3.91 | non-positive mean net return after costs |
| H04 | flow_absorption | `{"k": 2.0, "direction": -1, "horizon_min": 30}` | **rejected_discovery** | 5634 | 0.03 | -13.31 | 0.04 | 0.472 | 0.863 | -3.96 | non-positive mean net return after costs |
| H04 | flow_absorption | `{"k": 2.0, "direction": -1, "horizon_min": 120}` | **rejected_discovery** | 4450 | -0.09 | -13.44 | -0.00 | 0.503 | 0.881 | -4.09 | non-positive mean net return after costs |
| H04 | flow_absorption | `{"k": 3.0, "direction": 1, "horizon_min": 30}` | **rejected_discovery** | 553 | 0.38 | -13.06 | 0.47 | 0.420 | 0.843 | -3.61 | non-positive mean net return after costs |
| H04 | flow_absorption | `{"k": 3.0, "direction": 1, "horizon_min": 120}` | **rejected_discovery** | 521 | 0.64 | -12.78 | 1.19 | 0.420 | 0.843 | -3.33 | non-positive mean net return after costs |
| H04 | flow_absorption | `{"k": 3.0, "direction": -1, "horizon_min": 30}` | **rejected_discovery** | 553 | -0.38 | -13.83 | -0.35 | 0.577 | 0.895 | -4.39 | non-positive mean net return after costs |
| H04 | flow_absorption | `{"k": 3.0, "direction": -1, "horizon_min": 120}` | **rejected_discovery** | 521 | -0.64 | -14.11 | -0.71 | 0.550 | 0.895 | -4.67 | non-positive mean net return after costs |
| H05 | compression_breakout | `{"pct": 0.1, "direction": 1, "horizon_min": 240}` | **rejected_discovery** | 2699 | 3.62 | -9.72 | 3.18 | 0.173 | 0.484 | -0.46 | non-positive mean net return after costs |
| H05 | compression_breakout | `{"pct": 0.1, "direction": 1, "horizon_min": 720}` | **rejected_discovery** | 1714 | 9.82 | -3.66 | 9.16 | 0.088 | 0.336 | 5.58 | non-positive mean net return after costs |
| H05 | compression_breakout | `{"pct": 0.1, "direction": -1, "horizon_min": 240}` | **rejected_discovery** | 2699 | -3.62 | -16.80 | -3.17 | 0.846 | 1.000 | -7.54 | non-positive mean net return after costs |
| H05 | compression_breakout | `{"pct": 0.1, "direction": -1, "horizon_min": 720}` | **rejected_discovery** | 1714 | -9.82 | -22.83 | -8.68 | 0.891 | 1.000 | -13.58 | non-positive mean net return after costs |
| H05 | compression_breakout | `{"pct": 0.2, "direction": 1, "horizon_min": 240}` | **rejected_discovery** | 4573 | 3.17 | -10.14 | 2.82 | 0.133 | 0.397 | -0.89 | non-positive mean net return after costs |
| H05 | compression_breakout | `{"pct": 0.2, "direction": 1, "horizon_min": 720}` | **rejected_discovery** | 2666 | 4.58 | -8.77 | 3.47 | 0.264 | 0.671 | 0.45 | non-positive mean net return after costs |
| H05 | compression_breakout | `{"pct": 0.2, "direction": -1, "horizon_min": 240}` | **rejected_discovery** | 4573 | -3.17 | -16.35 | -2.55 | 0.847 | 1.000 | -7.11 | non-positive mean net return after costs |
| H05 | compression_breakout | `{"pct": 0.2, "direction": -1, "horizon_min": 720}` | **rejected_discovery** | 2666 | -4.58 | -17.67 | -3.46 | 0.734 | 0.979 | -8.45 | non-positive mean net return after costs |
| H06 | btc_lead_lag | `{"k": 2.0, "horizon_min": 15}` | **rejected_discovery** | 2186 | 2.79 | -11.01 | 2.76 | 0.005 | 0.040 | -1.20 | non-positive mean net return after costs |
| H06 | btc_lead_lag | `{"k": 2.0, "horizon_min": 60}` | **rejected_discovery** | 1781 | 6.43 | -7.38 | 6.33 | 0.002 | 0.037 | 2.42 | non-positive mean net return after costs |
| H06 | btc_lead_lag | `{"k": 3.0, "horizon_min": 15}` | **rejected_discovery** | 468 | -1.11 | -14.89 | -1.08 | 0.703 | 0.973 | -5.03 | non-positive mean net return after costs |
| H06 | btc_lead_lag | `{"k": 3.0, "horizon_min": 60}` | **rejected_discovery** | 409 | 5.65 | -8.21 | 5.44 | 0.099 | 0.346 | 1.64 | non-positive mean net return after costs |
| H07 | short_term_reversal | `{"window": "1h", "k": 3.0, "direction": 1, "horizon_min": 60}` | **rejected_discovery** | 3408 | 2.92 | -10.22 | 2.98 | 0.016 | 0.075 | -1.06 | non-positive mean net return after costs |
| H07 | short_term_reversal | `{"window": "1h", "k": 3.0, "direction": 1, "horizon_min": 240}` | **rejected_discovery** | 2399 | -1.06 | -14.09 | -0.83 | 0.604 | 0.895 | -4.96 | non-positive mean net return after costs |
| H07 | short_term_reversal | `{"window": "1h", "k": 3.0, "direction": -1, "horizon_min": 60}` | **rejected_discovery** | 3408 | -2.92 | -16.09 | -3.01 | 0.980 | 1.000 | -6.94 | non-positive mean net return after costs |
| H07 | short_term_reversal | `{"window": "1h", "k": 3.0, "direction": -1, "horizon_min": 240}` | **rejected_discovery** | 2399 | 1.06 | -12.17 | 0.79 | 0.416 | 0.843 | -3.04 | non-positive mean net return after costs |
| H07 | short_term_reversal | `{"window": "4h", "k": 3.0, "direction": 1, "horizon_min": 60}` | **rejected_discovery** | 2200 | 5.89 | -7.18 | 6.18 | 0.001 | 0.037 | 1.95 | non-positive mean net return after costs |
| H07 | short_term_reversal | `{"window": "4h", "k": 3.0, "direction": 1, "horizon_min": 240}` | **rejected_discovery** | 1040 | 13.69 | 0.77 | 14.70 | 0.004 | 0.040 | 9.92 | not profitable at 1.5x costs; non-positive in year(s) [2023] |
| H07 | short_term_reversal | `{"window": "4h", "k": 3.0, "direction": -1, "horizon_min": 60}` | **rejected_discovery** | 2200 | -5.89 | -19.08 | -6.05 | 1.000 | 1.000 | -9.95 | non-positive mean net return after costs |
| H07 | short_term_reversal | `{"window": "4h", "k": 3.0, "direction": -1, "horizon_min": 240}` | **rejected_discovery** | 1040 | -13.69 | -27.07 | -14.56 | 0.999 | 1.000 | -17.92 | non-positive mean net return after costs |
| H08 | forced_flow_reversal | `{"k": 2.0, "horizon_min": 60}` | **rejected_discovery** | 3635 | 3.50 | -9.66 | 3.02 | 0.010 | 0.056 | -0.58 | non-positive mean net return after costs |
| H08 | forced_flow_reversal | `{"k": 2.0, "horizon_min": 240}` | **rejected_discovery** | 2860 | 5.23 | -8.10 | 3.42 | 0.120 | 0.395 | 0.98 | non-positive mean net return after costs |
| H08 | forced_flow_reversal | `{"k": 3.0, "horizon_min": 60}` | **rejected_discovery** | 2345 | 0.67 | -12.46 | 0.16 | 0.478 | 0.863 | -3.42 | non-positive mean net return after costs |
| H08 | forced_flow_reversal | `{"k": 3.0, "horizon_min": 240}` | **rejected_discovery** | 1962 | 0.20 | -13.13 | -1.98 | 0.712 | 0.973 | -4.08 | non-positive mean net return after costs |
| B01 | baseline_tsmom | `{"long_only": false, "horizon_min": 1440}` | **baseline** | 3365 | 0.22 | -13.22 | 0.35 | 0.471 | – | -4.02 |  |
| B01 | baseline_tsmom | `{"long_only": true, "horizon_min": 1440}` | **baseline** | 2098 | 28.85 | 12.66 | -4.25 | 0.678 | – | 21.85 |  |
| B02 | baseline_always_long | `{"horizon_min": 1440}` | **baseline** | 3370 | 26.98 | 10.98 | -5.84 | 0.809 | – | 20.18 |  |

## Per-stage detail (only stages actually run are shown)

| Variant | Stage | n | gross bps | net bps | win | PF | Sharpe(d) | MDD bps | p(NW) | p(random) |
|---|---|---|---|---|---|---|---|---|---|---|
| H01 {"k": 2.0, "direction": 1, "horizon_min": 480} | discovery | 815 | 6.77 | -4.70 | 48.2% | 0.95 | -0.28 | -16748 | 0.698 | 0.135 |
| H01 {"k": 2.0, "direction": 1, "horizon_min": 1440} | discovery | 516 | 1.56 | -7.76 | 52.1% | 0.95 | -0.21 | -21745 | 0.768 | 0.395 |
| H01 {"k": 2.0, "direction": -1, "horizon_min": 480} | discovery | 815 | -6.77 | -21.73 | 42.6% | 0.78 | -1.32 | -23715 | 0.073 | 0.883 |
| H01 {"k": 2.0, "direction": -1, "horizon_min": 1440} | discovery | 516 | -1.56 | -18.76 | 42.2% | 0.88 | -0.51 | -25575 | 0.474 | 0.607 |
| H01 {"k": 3.0, "direction": 1, "horizon_min": 480} | discovery | 358 | -2.25 | -13.30 | 48.0% | 0.86 | -0.46 | -11174 | 0.450 | 0.422 |
| H01 {"k": 3.0, "direction": 1, "horizon_min": 1440} | discovery | 242 | 38.51 | 30.33 | 57.4% | 1.22 | 0.54 | -8989 | 0.434 | 0.033 |
| H01 {"k": 3.0, "direction": -1, "horizon_min": 480} | discovery | 358 | 2.25 | -13.13 | 42.2% | 0.87 | -0.47 | -11348 | 0.456 | 0.589 |
| H01 {"k": 3.0, "direction": -1, "horizon_min": 1440} | discovery | 242 | -38.51 | -56.91 | 38.0% | 0.69 | -1.02 | -18878 | 0.143 | 0.972 |
| H02 {"k": 2.5, "direction": 1, "horizon_min": 60} | discovery | 4862 | 2.19 | -10.85 | 41.4% | 0.73 | -3.19 | -52759 | 0.000 | 0.007 |
| H02 {"k": 2.5, "direction": 1, "horizon_min": 240} | discovery | 1929 | 6.57 | -6.14 | 46.4% | 0.91 | -0.59 | -24174 | 0.396 | 0.007 |
| H02 {"k": 2.5, "direction": -1, "horizon_min": 60} | discovery | 4862 | -2.19 | -15.45 | 39.2% | 0.64 | -4.73 | -75537 | 0.000 | 0.989 |
| H02 {"k": 2.5, "direction": -1, "horizon_min": 240} | discovery | 1929 | -6.57 | -20.27 | 43.1% | 0.74 | -1.95 | -39407 | 0.005 | 0.994 |
| H02 {"k": 3.5, "direction": 1, "horizon_min": 60} | discovery | 1488 | 4.85 | -8.08 | 44.6% | 0.83 | -1.10 | -14071 | 0.141 | 0.004 |
| H02 {"k": 3.5, "direction": 1, "horizon_min": 240} | discovery | 625 | 10.58 | -1.86 | 47.4% | 0.98 | -0.09 | -8113 | 0.908 | 0.014 |
| H02 {"k": 3.5, "direction": -1, "horizon_min": 60} | discovery | 1488 | -4.85 | -18.02 | 39.4% | 0.66 | -2.29 | -26814 | 0.001 | 0.995 |
| H02 {"k": 3.5, "direction": -1, "horizon_min": 240} | discovery | 625 | -10.58 | -24.27 | 43.2% | 0.74 | -1.10 | -16742 | 0.132 | 0.983 |
| H03 {"k": 2.0, "case": "short_covering", "horizon_min": 60} | discovery | 3603 | 4.09 | -9.08 | 48.9% | 0.82 | -2.02 | -40234 | 0.002 | 0.005 |
| H03 {"k": 2.0, "case": "short_covering", "horizon_min": 240} | discovery | 2760 | 3.17 | -10.15 | 51.9% | 0.87 | -1.34 | -31668 | 0.051 | 0.344 |
| H03 {"k": 2.0, "case": "new_positions", "horizon_min": 60} | discovery | 2688 | -3.67 | -17.01 | 37.3% | 0.73 | -3.57 | -46048 | 0.000 | 0.996 |
| H03 {"k": 2.0, "case": "new_positions", "horizon_min": 240} | discovery | 2045 | -4.15 | -17.69 | 41.8% | 0.81 | -1.82 | -37683 | 0.015 | 0.962 |
| H03 {"k": 3.0, "case": "short_covering", "horizon_min": 60} | discovery | 1627 | 6.06 | -7.07 | 50.6% | 0.88 | -0.79 | -20908 | 0.233 | 0.002 |
| H03 {"k": 3.0, "case": "short_covering", "horizon_min": 240} | discovery | 1312 | 0.43 | -12.87 | 52.3% | 0.86 | -0.91 | -19960 | 0.163 | 0.648 |
| H03 {"k": 3.0, "case": "new_positions", "horizon_min": 60} | discovery | 1167 | 2.41 | -11.03 | 40.7% | 0.84 | -1.26 | -15708 | 0.100 | 0.261 |
| H03 {"k": 3.0, "case": "new_positions", "horizon_min": 240} | discovery | 960 | 9.83 | -3.81 | 42.4% | 0.96 | -0.25 | -12535 | 0.736 | 0.090 |
| H04 {"k": 2.0, "direction": 1, "horizon_min": 30} | discovery | 5634 | -0.03 | -13.39 | 23.6% | 0.29 | -14.04 | -75415 | 0.000 | 0.526 |
| H04 {"k": 2.0, "direction": 1, "horizon_min": 120} | discovery | 4450 | 0.09 | -13.25 | 35.9% | 0.56 | -8.24 | -59132 | 0.000 | 0.465 |
| H04 {"k": 2.0, "direction": -1, "horizon_min": 30} | discovery | 5634 | 0.03 | -13.31 | 25.4% | 0.29 | -14.15 | -75017 | 0.000 | 0.472 |
| H04 {"k": 2.0, "direction": -1, "horizon_min": 120} | discovery | 4450 | -0.09 | -13.44 | 36.4% | 0.56 | -8.45 | -59798 | 0.000 | 0.503 |
| H04 {"k": 3.0, "direction": 1, "horizon_min": 30} | discovery | 553 | 0.38 | -13.06 | 21.7% | 0.25 | -5.86 | -7404 | 0.000 | 0.420 |
| H04 {"k": 3.0, "direction": 1, "horizon_min": 120} | discovery | 521 | 0.64 | -12.78 | 33.8% | 0.55 | -2.74 | -7264 | 0.000 | 0.420 |
| H04 {"k": 3.0, "direction": -1, "horizon_min": 30} | discovery | 553 | -0.38 | -13.83 | 20.3% | 0.23 | -6.17 | -7650 | 0.000 | 0.577 |
| H04 {"k": 3.0, "direction": -1, "horizon_min": 120} | discovery | 521 | -0.64 | -14.11 | 33.0% | 0.51 | -3.23 | -7690 | 0.000 | 0.550 |
| H05 {"pct": 0.1, "direction": 1, "horizon_min": 240} | discovery | 2699 | 3.62 | -9.72 | 37.6% | 0.76 | -2.02 | -28231 | 0.004 | 0.173 |
| H05 {"pct": 0.1, "direction": 1, "horizon_min": 720} | discovery | 1714 | 9.82 | -3.66 | 43.8% | 0.95 | -0.40 | -17408 | 0.560 | 0.088 |
| H05 {"pct": 0.1, "direction": -1, "horizon_min": 240} | discovery | 2699 | -3.62 | -16.80 | 43.5% | 0.62 | -3.51 | -45335 | 0.000 | 0.846 |
| H05 {"pct": 0.1, "direction": -1, "horizon_min": 720} | discovery | 1714 | -9.82 | -22.83 | 45.5% | 0.72 | -2.50 | -45038 | 0.000 | 0.891 |
| H05 {"pct": 0.2, "direction": 1, "horizon_min": 240} | discovery | 4573 | 3.17 | -10.14 | 38.9% | 0.77 | -2.77 | -49448 | 0.000 | 0.133 |
| H05 {"pct": 0.2, "direction": 1, "horizon_min": 720} | discovery | 2666 | 4.58 | -8.77 | 43.7% | 0.89 | -1.04 | -35730 | 0.133 | 0.264 |
| H05 {"pct": 0.2, "direction": -1, "horizon_min": 240} | discovery | 4573 | -3.17 | -16.35 | 44.7% | 0.64 | -4.50 | -76197 | 0.000 | 0.847 |
| H05 {"pct": 0.2, "direction": -1, "horizon_min": 720} | discovery | 2666 | -4.58 | -17.67 | 47.0% | 0.79 | -2.10 | -53325 | 0.002 | 0.734 |
| H06 {"k": 2.0, "horizon_min": 15} | discovery | 2186 | 2.79 | -11.01 | 37.6% | 0.65 | -3.69 | -24151 | 0.000 | 0.005 |
| H06 {"k": 2.0, "horizon_min": 60} | discovery | 1781 | 6.43 | -7.38 | 41.8% | 0.86 | -1.14 | -16807 | 0.129 | 0.002 |
| H06 {"k": 3.0, "horizon_min": 15} | discovery | 468 | -1.11 | -14.89 | 39.5% | 0.62 | -2.01 | -6980 | 0.003 | 0.703 |
| H06 {"k": 3.0, "horizon_min": 60} | discovery | 409 | 5.65 | -8.21 | 42.1% | 0.86 | -0.63 | -5382 | 0.383 | 0.099 |
| H07 {"window": "1h", "k": 3.0, "direction": 1, "horizon_min": 60} | discovery | 3408 | 2.92 | -10.22 | 51.0% | 0.84 | -1.64 | -38725 | 0.016 | 0.016 |
| H07 {"window": "1h", "k": 3.0, "direction": 1, "horizon_min": 240} | discovery | 2399 | -1.06 | -14.09 | 52.1% | 0.85 | -1.29 | -34583 | 0.062 | 0.604 |
| H07 {"window": "1h", "k": 3.0, "direction": -1, "horizon_min": 60} | discovery | 3408 | -2.92 | -16.09 | 38.8% | 0.76 | -2.71 | -55985 | 0.000 | 0.980 |
| H07 {"window": "1h", "k": 3.0, "direction": -1, "horizon_min": 240} | discovery | 2399 | 1.06 | -12.17 | 41.1% | 0.87 | -1.13 | -37312 | 0.106 | 0.416 |
| H07 {"window": "4h", "k": 3.0, "direction": 1, "horizon_min": 60} | discovery | 2200 | 5.89 | -7.18 | 50.1% | 0.89 | -1.05 | -18504 | 0.209 | 0.001 |
| H07 {"window": "4h", "k": 3.0, "direction": 1, "horizon_min": 240} | discovery | 1040 | 13.69 | 0.77 | 53.3% | 1.01 | 0.04 | -11999 | 0.951 | 0.004 |
| H07 {"window": "4h", "k": 3.0, "direction": -1, "horizon_min": 60} | discovery | 2200 | -5.89 | -19.08 | 38.5% | 0.74 | -3.02 | -43254 | 0.001 | 1.000 |
| H07 {"window": "4h", "k": 3.0, "direction": -1, "horizon_min": 240} | discovery | 1040 | -13.69 | -27.07 | 40.6% | 0.77 | -1.53 | -33014 | 0.032 | 0.999 |
| H08 {"k": 2.0, "horizon_min": 60} | discovery | 3635 | 3.50 | -9.66 | 50.5% | 0.81 | -2.02 | -39603 | 0.003 | 0.010 |
| H08 {"k": 2.0, "horizon_min": 240} | discovery | 2860 | 5.23 | -8.10 | 53.2% | 0.89 | -1.00 | -24710 | 0.144 | 0.120 |
| H08 {"k": 3.0, "horizon_min": 60} | discovery | 2345 | 0.67 | -12.46 | 51.0% | 0.77 | -2.02 | -33582 | 0.002 | 0.478 |
| H08 {"k": 3.0, "horizon_min": 240} | discovery | 1962 | 0.20 | -13.13 | 53.0% | 0.83 | -1.33 | -31609 | 0.048 | 0.712 |
| B01 {"long_only": false, "horizon_min": 1440} | discovery | 3365 | 0.22 | -13.22 | 44.2% | 0.90 | -0.92 | -72346 | 0.180 | 0.471 |
| B01 {"long_only": false, "horizon_min": 1440} | validation | 1260 | 8.91 | -4.56 | 48.0% | 0.97 | -0.28 | -35523 | 0.786 | – |
| B01 {"long_only": false, "horizon_min": 1440} | test | 1680 | 15.66 | 2.13 | 46.5% | 1.02 | 0.14 | -20821 | 0.872 | – |
| B01 {"long_only": true, "horizon_min": 1440} | discovery | 2098 | 28.85 | 12.66 | 45.0% | 1.11 | 0.71 | -30966 | 0.301 | 0.678 |
| B01 {"long_only": true, "horizon_min": 1440} | validation | 787 | 9.19 | -5.37 | 46.9% | 0.96 | -0.25 | -25522 | 0.805 | – |
| B01 {"long_only": true, "horizon_min": 1440} | test | 964 | -0.15 | -14.05 | 43.5% | 0.88 | -0.78 | -25651 | 0.411 | – |
| B02 {"horizon_min": 1440} | discovery | 3370 | 26.98 | 10.98 | 47.0% | 1.09 | 0.67 | -34950 | 0.301 | 0.809 |
| B02 {"horizon_min": 1440} | validation | 1260 | 11.54 | -2.81 | 47.8% | 0.98 | -0.14 | -38208 | 0.890 | – |
| B02 {"horizon_min": 1440} | test | 1680 | -11.89 | -25.47 | 44.5% | 0.80 | -1.51 | -56238 | 0.098 | – |

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
