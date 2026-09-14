from __future__ import annotations

import random

from tradingbot.risk.correlation import assign_clusters, cluster_size_multiplier, correlation_matrix


def test_correlated_series_land_in_same_cluster():
    rng = random.Random(1)
    base = [rng.uniform(-0.01, 0.01) for _ in range(200)]
    a = base
    b = [x + rng.uniform(-0.0005, 0.0005) for x in base]     # near-identical to `a`
    c = [rng.uniform(-0.01, 0.01) for _ in range(200)]        # independent

    matrix = correlation_matrix({"A": a, "B": b, "C": c})
    clusters = assign_clusters(matrix, threshold=0.7)

    assert clusters["A"] == clusters["B"]
    assert clusters["C"] != clusters["A"]


def test_cluster_size_multiplier_shrinks_as_cluster_fills_up():
    assert cluster_size_multiplier(current_cluster_exposure_pct=0.0, max_cluster_exposure_pct=10.0) == 1.0
    assert cluster_size_multiplier(current_cluster_exposure_pct=10.0, max_cluster_exposure_pct=10.0) == 0.0
    mid = cluster_size_multiplier(current_cluster_exposure_pct=5.0, max_cluster_exposure_pct=10.0)
    assert 0.4 < mid < 0.6


def test_cluster_size_multiplier_never_negative_when_over_cap():
    assert cluster_size_multiplier(current_cluster_exposure_pct=15.0, max_cluster_exposure_pct=10.0) == 0.0
