"""Correlation engine (spec section 20).

Purpose: prevent the scanner from treating five highly-correlated altcoins
as five independent bets when they are really one leveraged bet on the same
underlying factor (usually BTC beta). Clusters are recomputed periodically
from rolling returns, not hard-coded, since correlation regimes shift.
"""
from __future__ import annotations

import numpy as np


def returns_from_closes(closes: list[float]) -> list[float]:
    return [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes)) if closes[i - 1] != 0]


def correlation_matrix(returns_by_symbol: dict[str, list[float]]) -> dict[str, dict[str, float]]:
    """Pairwise Pearson correlation using each pair's overlapping tail
    length (symbols may have slightly different history lengths)."""
    symbols = list(returns_by_symbol.keys())
    matrix: dict[str, dict[str, float]] = {s: {} for s in symbols}
    for i, a in enumerate(symbols):
        for b in symbols[i:]:
            ra, rb = returns_by_symbol[a], returns_by_symbol[b]
            n = min(len(ra), len(rb))
            if n < 5:
                corr = 0.0
            else:
                arr_a = np.array(ra[-n:])
                arr_b = np.array(rb[-n:])
                if arr_a.std() == 0 or arr_b.std() == 0:
                    corr = 0.0
                else:
                    corr = float(np.corrcoef(arr_a, arr_b)[0, 1])
            matrix[a][b] = corr
            matrix[b][a] = corr
    return matrix


def assign_clusters(matrix: dict[str, dict[str, float]], threshold: float = 0.7) -> dict[str, str]:
    """Connected-components clustering on the correlation graph
    (edge when |corr| >= threshold). Returns symbol -> cluster_id, where
    cluster_id is the alphabetically-first member of that cluster."""
    symbols = list(matrix.keys())
    parent = {s: s for s in symbols}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for a in symbols:
        for b in symbols:
            if a != b and abs(matrix[a].get(b, 0.0)) >= threshold:
                union(a, b)

    return {s: find(s) for s in symbols}


def cluster_size_multiplier(
    current_cluster_exposure_pct: float,
    max_cluster_exposure_pct: float,
) -> float:
    """Shrinks new-position size as a cluster fills up its exposure budget;
    returns 0.0 once the cluster is already at/over its cap (spec section
    20: reject or reduce, never silently ignore existing correlated risk)."""
    if max_cluster_exposure_pct <= 0:
        return 0.0
    remaining_fraction = 1.0 - (current_cluster_exposure_pct / max_cluster_exposure_pct)
    return max(0.0, min(1.0, remaining_fraction))
