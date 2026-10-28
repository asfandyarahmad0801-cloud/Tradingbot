"""Pre-registered hypotheses for Milestone 1.

Each hypothesis is written down -- mechanism, competing explanation, signal
definition, parameter grid, and the result that would refute it -- *before*
it is evaluated. Parameter grids are deliberately small; every grid point is
a separate test in the multiple-testing family, so a larger grid makes every
hypothesis harder to accept.

Where the competing explanation predicts the opposite sign, the opposite
direction is registered as its own variant (`direction=-1`) instead of
being 'discovered' after looking at the data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product
from typing import Callable

import numpy as np
import pandas as pd

SignalFn = Callable[[pd.DataFrame, dict], pd.Series]


@dataclass(frozen=True)
class Hypothesis:
    hid: str
    name: str
    mechanism: str
    competing: str
    data_required: list[str]
    signal_definition: str
    works_when: str
    fails_when: str
    why_not_arbitraged: str
    holding: str
    refutation: str
    signal_fn: SignalFn
    grid: dict[str, list] = field(default_factory=dict)
    symbols: str = "all"            # "all" or "alts" (needs BTC reference features)

    def variants(self) -> list[dict]:
        keys = list(self.grid)
        return [dict(zip(keys, vals)) for vals in product(*(self.grid[k] for k in keys))]


def _sig(cond_long: pd.Series, cond_short: pd.Series) -> pd.Series:
    s = pd.Series(0.0, index=cond_long.index)
    s[cond_long.fillna(False).astype(bool)] = 1.0
    s[cond_short.fillna(False).astype(bool)] = -1.0
    return s


def _funding(f: pd.DataFrame, p: dict) -> pd.Series:
    z = f["funding_z"]
    return p["direction"] * _sig(z < -p["k"], z > p["k"])


def _premium(f: pd.DataFrame, p: dict) -> pd.Series:
    z = f["prem_1h_z"]
    return p["direction"] * _sig(z < -p["k"], z > p["k"])


def _oi_divergence(f: pd.DataFrame, p: dict) -> pd.Series:
    r, d = f["ret_1h_z"], f["doi_1h_z"]
    if p["case"] == "short_covering":     # price up on falling OI: fade (shorts exiting, not new demand)
        return _sig((r < -p["k"]) & (d < -1.0), (r > p["k"]) & (d < -1.0))
    # "new_positions": price up on rising OI: follow (fresh directional commitment)
    return _sig((r > p["k"]) & (d > 1.0), (r < -p["k"]) & (d > 1.0))


def _absorption(f: pd.DataFrame, p: dict) -> pd.Series:
    imb, r = f["imb_30m_z"], f["ret_30m_z"]
    stalled_up = (imb > p["k"]) & (r < 0.25)      # heavy taker buying, price not progressing
    stalled_dn = (imb < -p["k"]) & (r > -0.25)
    return p["direction"] * _sig(stalled_dn, stalled_up)


def _compression_breakout(f: pd.DataFrame, p: dict) -> pd.Series:
    comp = f["rv_4h_pct"].shift(1) < p["pct"]
    return p["direction"] * _sig(comp & (f["break_up"] == 1), comp & (f["break_dn"] == 1))


def _lead_lag(f: pd.DataFrame, p: dict) -> pd.Series:
    b, a = f["btc_ret_30m_z"], f["ret_30m_z"]
    return _sig((b > p["k"]) & (a < 0.5), (b < -p["k"]) & (a > -0.5))


def _reversal(f: pd.DataFrame, p: dict) -> pd.Series:
    z = f[f"ret_{p['window']}_z"]
    return p["direction"] * _sig(z < -p["k"], z > p["k"])


def _forced_flow(f: pd.DataFrame, p: dict) -> pd.Series:
    flush = f["doi_15m_z"] < -p["k"]
    r = f["ret_30m_z"]
    return _sig(flush & (r < -2.0), flush & (r > 2.0))


def _tsmom(f: pd.DataFrame, p: dict) -> pd.Series:
    r = f["ret_24h"]
    on_hour = (f.index.to_numpy() // 3_600_000) % 24 == 0  # decide once a day, 00:00 UTC
    s = np.sign(r).where(on_hour, 0.0)
    if p["long_only"]:
        s = s.clip(lower=0)
    return s


def _always_long(f: pd.DataFrame, p: dict) -> pd.Series:
    on_hour = (f.index.to_numpy() // 3_600_000) % 24 == 0
    return pd.Series(np.where(on_hour & f["valid"].to_numpy(), 1.0, 0.0), index=f.index)


HYPOTHESES: list[Hypothesis] = [
    Hypothesis(
        hid="H01", name="funding_crowding",
        mechanism="Extreme funding (vs. its own trailing 30d distribution) marks one-sided leveraged "
                  "positioning; those positions are expensive to hold and fragile, so returns over the "
                  "next funding cycles should be against the crowd.",
        competing="Funding is high *because* demand is persistent (trend); it is a momentum signal, so "
                  "returns continue in the crowd's direction (direction=-1 variant).",
        data_required=["funding settlements", "perp 1m klines"],
        signal_definition="z = (funding - mean_30d) / std_30d of last settled rate; short if z>k, long if z<-k "
                          "(times direction).",
        works_when="Leverage is elevated and price stalls; funding spikes are idiosyncratic to the asset.",
        fails_when="Strong trends where funding stays elevated for weeks; funding regime shifts (cap changes).",
        why_not_arbitraged="Basis/carry desks harvest funding delta-neutral, not directionally; the directional "
                           "component may persist because it is volatile and hard to size.",
        holding="8h-24h", refutation="Mean net return <= random-timing null, or sign flips across years.",
        signal_fn=_funding, grid={"k": [2.0, 3.0], "direction": [1, -1], "horizon_min": [480, 1440]},
    ),
    Hypothesis(
        hid="H02", name="premium_dislocation",
        mechanism="A large perp premium/discount over the spot index reflects temporary leveraged "
                  "pressure on the perp that should mean-revert via perp price (not spot).",
        competing="Premium leads spot: perp traders are better informed, so spot (and the perp) follow "
                  "the premium's direction (direction=-1).",
        data_required=["premium index 1m klines", "perp 1m klines"],
        signal_definition="z of 1h-mean premium vs trailing 30d; fade if |z|>k.",
        works_when="Premium spike without corresponding spot flow.", fails_when="News-driven repricing.",
        why_not_arbitraged="Cash-and-carry arb compresses the basis but via both legs; directional perp "
                           "return after costs may still be zero.",
        holding="1h-4h", refutation="No excess vs random timing after taker costs.",
        signal_fn=_premium, grid={"k": [2.5, 3.5], "direction": [1, -1], "horizon_min": [60, 240]},
    ),
    Hypothesis(
        hid="H03", name="oi_price_divergence",
        mechanism="A price move on *falling* OI is position closing (e.g. short covering), which exhausts "
                  "itself -> fade. A move on *rising* OI is new directional commitment -> continuation.",
        competing="OI changes are dominated by hedging/basis trades and carry no directional information.",
        data_required=["5m open interest", "perp 1m klines"],
        signal_definition="ret_1h_z beyond +-k with doi_1h_z < -1 (fade) or > +1 (follow).",
        works_when="Positioning-driven moves.", fails_when="Spot-led moves where perp OI is incidental.",
        why_not_arbitraged="OI is public but only at 5m granularity; interpretation is ambiguous.",
        holding="1h-4h", refutation="Neither case beats random timing; or both cases have same sign.",
        signal_fn=_oi_divergence,
        grid={"k": [2.0, 3.0], "case": ["short_covering", "new_positions"], "horizon_min": [60, 240]},
    ),
    Hypothesis(
        hid="H04", name="flow_absorption",
        mechanism="Heavy aggressive buying that fails to move price means passive sellers are absorbing it; "
                  "when the aggressors stop, price should drift toward the absorber (fade the flow).",
        competing="Absorbed flow is accumulation; once the passive seller is exhausted price breaks in the "
                  "flow direction (direction=-1).",
        data_required=["perp 1m klines with taker-buy volume"],
        signal_definition="imb_30m_z > k and ret_30m_z < 0.25 -> short (mirror for long), times direction.",
        works_when="Range regimes with a large passive participant.", fails_when="Trending, news-driven flow.",
        why_not_arbitraged="Requires interpreting order flow; taker share from klines is coarse and public.",
        holding="30m-2h", refutation="No excess vs random timing; result driven by one symbol/year.",
        signal_fn=_absorption, grid={"k": [2.0, 3.0], "direction": [1, -1], "horizon_min": [30, 120]},
    ),
    Hypothesis(
        hid="H05", name="compression_breakout",
        mechanism="Volatility clusters and mean-reverts: after compression, a range break starts an "
                  "expansion that carries in the break direction.",
        competing="Breaks out of quiet ranges are liquidity sweeps that fail and reverse (direction=-1).",
        data_required=["perp 1m klines"],
        signal_definition="rv_4h percentile (trailing 30d, prior bar) < pct and close breaks prior 4h high/low.",
        works_when="Regime transitions into trend.", fails_when="Choppy, mean-reverting low-liquidity hours.",
        why_not_arbitraged="Widely traded; any edge may already be competed away -- that is what we test.",
        holding="4h-12h", refutation="Follow and fade variants both <= null.",
        signal_fn=_compression_breakout,
        grid={"pct": [0.10, 0.20], "direction": [1, -1], "horizon_min": [240, 720]},
    ),
    Hypothesis(
        hid="H06", name="btc_lead_lag", symbols="alts",
        mechanism="Information is priced into BTC first; alts that have not yet moved catch up.",
        competing="The lag is a microstructure effect of seconds, fully exploited by HFT; at 5m+ there is "
                  "nothing left after costs.",
        data_required=["perp 1m klines for BTC and alts"],
        signal_definition="btc_ret_30m_z > k while alt ret_30m_z < 0.5 -> long alt (mirror short).",
        works_when="Market-wide shocks.", fails_when="Alt-specific news; decoupled alt regimes.",
        why_not_arbitraged="It almost certainly is at short horizons; included as a cost-realism check.",
        holding="15m-1h", refutation="Gross may be positive but net <= null.",
        signal_fn=_lead_lag, grid={"k": [2.0, 3.0], "horizon_min": [15, 60]},
    ),
    Hypothesis(
        hid="H07", name="short_term_reversal",
        mechanism="Large short-horizon moves overshoot due to liquidity demand (stop runs, liquidations) "
                  "and partially revert as liquidity providers are compensated.",
        competing="Large moves reflect information and continue (time-series momentum, direction=-1).",
        data_required=["perp 1m klines"],
        signal_definition="fade if |ret_window_z| > k (times direction).",
        works_when="Liquidity-driven moves in ranges.", fails_when="Trend days, news shocks.",
        why_not_arbitraged="Providing liquidity into crashes is risky and capital-intensive.",
        holding="1h-4h", refutation="No excess over null in either direction.",
        signal_fn=_reversal,
        grid={"window": ["1h", "4h"], "k": [3.0], "direction": [1, -1], "horizon_min": [60, 240]},
    ),
    Hypothesis(
        hid="H08", name="forced_flow_reversal",
        mechanism="A sharp OI drop with a large price move is a proxy for liquidation cascades (forced, "
                  "price-insensitive flow); price should partially recover once the forced flow ends.",
        competing="Cascades mark regime breaks; price keeps going.",
        data_required=["5m open interest", "perp 1m klines"],
        signal_definition="doi_15m_z < -k and |ret_30m_z| > 2 -> fade the move. "
                          "(Proxy only: historical liquidation prints are not available.)",
        works_when="Leverage flushes.", fails_when="Fundamental repricing.",
        why_not_arbitraged="Catching knives requires risk capital at the worst moment.",
        holding="1h-4h", refutation="No excess vs null; negative skew dominates.",
        signal_fn=_forced_flow, grid={"k": [2.0, 3.0], "horizon_min": [60, 240]},
    ),
    Hypothesis(
        hid="B01", name="baseline_tsmom",
        mechanism="Baseline: daily time-series momentum (sign of trailing 24h return), rebalanced 00:00 UTC.",
        competing="n/a (baseline).", data_required=["perp 1m klines"],
        signal_definition="sign(ret_24h) at 00:00 UTC, hold 24h.", works_when="Trending markets.",
        fails_when="Choppy markets.", why_not_arbitraged="n/a", holding="24h",
        refutation="n/a", signal_fn=_tsmom, grid={"long_only": [False, True], "horizon_min": [1440]},
    ),
    Hypothesis(
        hid="B02", name="baseline_always_long",
        mechanism="Baseline: long every day at 00:00 UTC for 24h (buy-and-hold proxy that pays the same "
                  "costs and funding as the other strategies).",
        competing="n/a (baseline).", data_required=["perp 1m klines", "funding"],
        signal_definition="+1 daily.", works_when="Bull markets.", fails_when="Bear markets.",
        why_not_arbitraged="n/a", holding="24h", refutation="n/a",
        signal_fn=_always_long, grid={"horizon_min": [1440]},
    ),
]


def by_id(hid: str) -> Hypothesis:
    for h in HYPOTHESES:
        if h.hid == hid:
            return h
    raise KeyError(hid)
