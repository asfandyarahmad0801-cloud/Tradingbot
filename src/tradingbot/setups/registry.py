"""Registry of active setups.

Adding a new setup means implementing `Setup` and appending it here -- the
scanner iterates this list for every eligible symbol on every cycle. Setups
are independent; the scanner (see `scanner/scanner.py`) is responsible for
preventing duplicate/conflicting positions on the same symbol when more than
one setup fires (spec section 48).
"""
from __future__ import annotations

from tradingbot.setups.base import Setup
from tradingbot.setups.breakout import BreakoutSetup
from tradingbot.setups.failed_breakout_reversal import FailedBreakoutReversalSetup
from tradingbot.setups.liquidation_reversal import LiquidationReversalSetup
from tradingbot.setups.mean_reversion import MeanReversionSetup
from tradingbot.setups.momentum_continuation import MomentumContinuationSetup
from tradingbot.setups.vwap_reclaim import VwapReclaimSetup


def default_setups() -> list[Setup]:
    return [
        MomentumContinuationSetup(),
        BreakoutSetup(),
        MeanReversionSetup(),
        LiquidationReversalSetup(),
        VwapReclaimSetup(),
        FailedBreakoutReversalSetup(),
    ]
