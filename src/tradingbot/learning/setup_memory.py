"""Setup memory: learn from closed trades which setups to stop taking.

What it learns, and what it deliberately does not:

- It remembers every closed trade under a *context key*: the setup name,
  plus the setup in that coin, plus the setup in that market regime. A
  setup can be fine on SOL in a range and losing on DOGE in a trend; the
  memory can block the bad context without killing the good one.
- **Cooldown** after a streak of consecutive losses in a context (default
  3). Streaks happen to profitable setups too, so this is a pause, not a ban.
- **Permanent ban** once a context has enough trades to judge
  (`min_trades_to_judge`) and its average net result is negative with some
  statistical conviction (t <= `ban_t_threshold`). A banned context stays
  banned across restarts until an operator resets it.
- It never raises size, never re-enables early, and never trades *more*
  because of a loss. It can only block.

Why not "ban after one loss": every setup -- including genuinely profitable
ones -- loses a meaningful fraction of trades. A one-loss ban disables
everything within a day and learns nothing. Set `loss_streak_for_cooldown=1`
and `min_trades_to_judge` small if you really want harsher behaviour; the
knobs are there, the defaults are what the evidence supports.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class MemoryConfig:
    loss_streak_for_cooldown: int = 3
    cooldown_minutes: int = 24 * 60
    min_trades_to_judge: int = 15
    ban_t_threshold: float = -1.0       # mean/stderr of net bps at or below this -> ban
    judge_window: int = 50              # only the most recent N trades are judged (markets change)


@dataclass(slots=True)
class ContextStats:
    results_bps: list[float] = field(default_factory=list)
    loss_streak: int = 0
    cooldown_until_ms: int = 0
    banned: bool = False
    ban_reason: str = ""

    def summary(self) -> dict:
        r = self.results_bps
        return {
            "trades": len(r),
            "win_rate": sum(x > 0 for x in r) / len(r) if r else None,
            "mean_net_bps": sum(r) / len(r) if r else None,
            "loss_streak": self.loss_streak,
            "cooldown_until_ms": self.cooldown_until_ms,
            "banned": self.banned,
            "ban_reason": self.ban_reason,
        }


def context_keys(setup: str, symbol: str, regime: str | None) -> list[str]:
    keys = [f"setup={setup}", f"setup={setup}|symbol={symbol}"]
    if regime:
        keys.append(f"setup={setup}|regime={regime}")
    return keys


class SetupMemory:
    def __init__(self, config: MemoryConfig | None = None, path: str | Path | None = None) -> None:
        self.config = config or MemoryConfig()
        self.path = Path(path) if path else None
        self.contexts: dict[str, ContextStats] = {}
        if self.path and self.path.exists():
            self._load()

    def is_allowed(self, setup: str, symbol: str, regime: str | None, now_ms: int) -> tuple[bool, list[str]]:
        reasons = []
        for key in context_keys(setup, symbol, regime):
            st = self.contexts.get(key)
            if st is None:
                continue
            if st.banned:
                reasons.append(f"learned_ban:{key}:{st.ban_reason}")
            elif now_ms < st.cooldown_until_ms:
                mins = (st.cooldown_until_ms - now_ms) / 60_000
                reasons.append(f"learned_cooldown:{key}:{mins:.0f}min_left")
        return (not reasons, reasons)

    def record(self, setup: str, symbol: str, regime: str | None, net_bps: float, now_ms: int) -> list[str]:
        """Record one closed trade's net result (after fees). Returns the
        lessons learned, for logging (empty if nothing changed)."""
        cfg = self.config
        lessons = []
        for key in context_keys(setup, symbol, regime):
            st = self.contexts.setdefault(key, ContextStats())
            st.results_bps.append(float(net_bps))
            st.results_bps = st.results_bps[-cfg.judge_window:]
            if net_bps <= 0:
                st.loss_streak += 1
                if st.loss_streak >= cfg.loss_streak_for_cooldown and not st.banned:
                    st.cooldown_until_ms = now_ms + cfg.cooldown_minutes * 60_000
                    lessons.append(f"cooldown {key} for {cfg.cooldown_minutes}min after {st.loss_streak} losses in a row")
                    st.loss_streak = 0
            else:
                st.loss_streak = 0
            if not st.banned and len(st.results_bps) >= cfg.min_trades_to_judge:
                t = _t_stat(st.results_bps)
                if t is not None and t <= cfg.ban_t_threshold:
                    mean = sum(st.results_bps) / len(st.results_bps)
                    st.banned = True
                    st.ban_reason = f"mean {mean:.1f}bps over {len(st.results_bps)} trades, t={t:.2f}"
                    lessons.append(f"BAN {key}: {st.ban_reason}")
        self._save()
        return lessons

    def reset(self, key: str | None = None) -> None:
        """Operator action only: clear one context (or everything)."""
        if key is None:
            self.contexts.clear()
        else:
            self.contexts.pop(key, None)
        self._save()

    def report(self) -> dict[str, dict]:
        return {k: v.summary() for k, v in sorted(self.contexts.items())}

    def _save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({k: asdict(v) for k, v in self.contexts.items()}, indent=1))
        os.replace(tmp, self.path)  # atomic: a crash never corrupts what was learned

    def _load(self) -> None:
        raw = json.loads(self.path.read_text())
        self.contexts = {k: ContextStats(**v) for k, v in raw.items()}


def _t_stat(x: list[float]) -> float | None:
    n = len(x)
    if n < 2:
        return None
    m = sum(x) / n
    var = sum((v - m) ** 2 for v in x) / (n - 1)
    if var <= 0:
        return -math.inf if m < 0 else None
    return m / math.sqrt(var / n)
