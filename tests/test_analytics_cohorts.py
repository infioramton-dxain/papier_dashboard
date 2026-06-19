"""Tests for src/signal_terminal/analytics/cohorts.py.

Construct a synthetic correlation matrix with two obvious blocks of
co-moving symbols and assert hierarchical clustering recovers them. Same
goal for k-means: build feature vectors with two well-separated clusters
and assert the labels match the ground truth.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from signal_terminal.analytics.cohorts import (hierarchical_cluster,
                                                  kmeans_cluster)
from signal_terminal.style import EVENT_FLAGS


# --------------------------------------------------------------------------- #
# Hierarchical
# --------------------------------------------------------------------------- #
def _block_correlation(n_per_block: int = 5, n_blocks: int = 2,
                        intra: float = 0.9, inter: float = 0.05) -> pd.DataFrame:
    n = n_per_block * n_blocks
    symbols = [f"SYM{i:02d}" for i in range(n)]
    M = np.full((n, n), inter, dtype=float)
    for b in range(n_blocks):
        s = b * n_per_block
        e = s + n_per_block
        M[s:e, s:e] = intra
    np.fill_diagonal(M, 1.0)
    return pd.DataFrame(M, index=symbols, columns=symbols)


def test_hierarchical_recovers_blocks() -> None:
    corr = _block_correlation(n_per_block=4, n_blocks=2, intra=0.95, inter=0.0)
    # Mantegna distance: intra=√(0.1) ≈ 0.316, inter=√(2.0) ≈ 1.414. Cut at 1.0
    # cleanly separates them.
    res = hierarchical_cluster(corr, cut_height=1.0)
    assert res.n_clusters == 2
    a = set(res.labels.iloc[:4].unique())
    b = set(res.labels.iloc[4:].unique())
    assert a != b, "first and second block ended up in the same cluster"
    # Membership table sanity
    assert {"cluster_id", "n_members", "symbols", "mean_intra_corr"} <= set(res.membership.columns)


def test_hierarchical_loose_cut_collapses_into_one() -> None:
    corr = _block_correlation(n_per_block=4, n_blocks=2, intra=0.95, inter=0.0)
    res = hierarchical_cluster(corr, cut_height=2.0)  # well above max distance
    assert res.n_clusters == 1


def test_hierarchical_empty_input() -> None:
    res = hierarchical_cluster(pd.DataFrame(), cut_height=0.5)
    assert res.n_clusters == 0
    assert res.labels.empty


# --------------------------------------------------------------------------- #
# K-means
# --------------------------------------------------------------------------- #
def test_kmeans_recovers_two_well_separated_clusters() -> None:
    """Cluster A: low sentiment, high materiality. Cluster B: opposite."""
    rng = np.random.default_rng(0)
    rows = []
    for i in range(8):
        rows.append({
            "symbol": f"A{i}",
            "mean_sentiment": rng.normal(-0.6, 0.05),
            "std_sentiment":  rng.normal(0.2, 0.02),
            "abs_mean_sentiment": rng.normal(0.6, 0.05),
            "mean_materiality": rng.normal(0.8, 0.03),
            "mean_geo_risk":   rng.normal(0.5, 0.05),
            **{f"{f}_rate": rng.uniform(0.05, 0.15) for f in EVENT_FLAGS},
        })
    for i in range(8):
        rows.append({
            "symbol": f"B{i}",
            "mean_sentiment": rng.normal(0.6, 0.05),
            "std_sentiment":  rng.normal(0.2, 0.02),
            "abs_mean_sentiment": rng.normal(0.6, 0.05),
            "mean_materiality": rng.normal(0.2, 0.03),
            "mean_geo_risk":   rng.normal(0.1, 0.05),
            **{f"{f}_rate": rng.uniform(0.05, 0.15) for f in EVENT_FLAGS},
        })
    feats = pd.DataFrame(rows)
    res = kmeans_cluster(feats, k=2)
    a_labels = res.labels.loc[[f"A{i}" for i in range(8)]]
    b_labels = res.labels.loc[[f"B{i}" for i in range(8)]]
    assert a_labels.nunique() == 1
    assert b_labels.nunique() == 1
    assert a_labels.iloc[0] != b_labels.iloc[0]


def test_kmeans_silhouette_picks_correct_k() -> None:
    """Two blobs that separate strongly along every feature → silhouette
    should pick k=2 over k=3..10."""
    rng = np.random.default_rng(1)
    rows = []
    for label, scale in (("A", -1.0), ("B", 1.0)):
        for i in range(10):
            row = {
                "symbol": f"{label}{i}",
                "mean_sentiment": rng.normal(scale * 0.6, 0.05),
                "std_sentiment":  rng.normal(0.2 + 0.05 * scale, 0.02),
                "abs_mean_sentiment": rng.normal(0.6, 0.05),
                "mean_materiality": rng.normal(0.5 + 0.3 * scale, 0.04),
                "mean_geo_risk":   rng.normal(0.3 + 0.3 * scale, 0.04),
            }
            for j, f in enumerate(EVENT_FLAGS):
                base_rate = 0.5 if (scale > 0) == (j % 2 == 0) else 0.05
                row[f"{f}_rate"] = rng.normal(base_rate, 0.02)
            rows.append(row)
    feats = pd.DataFrame(rows)
    res = kmeans_cluster(feats)  # auto-pick k via silhouette
    assert res.chosen_k == 2


def test_kmeans_empty_input() -> None:
    res = kmeans_cluster(pd.DataFrame())
    assert res.chosen_k == 0
    assert res.labels.empty
