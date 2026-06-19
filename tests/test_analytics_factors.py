"""Tests for src/signal_terminal/analytics/factors.py.

Inject one strong shared factor across symbols and verify PCA recovers it as
PC1 explaining most of the variance. For NMF, build per-symbol feature vectors
with two obvious 'themes' and assert symbols on the same theme get the highest
weight on the same component.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from signal_terminal.analytics.factors import run_nmf, run_pca
from signal_terminal.style import EVENT_FLAGS


def _make_pivot_with_shared_factor(seed: int = 0) -> pd.DataFrame:
    """Build a 200-period × 12-symbol pivot where every symbol = α_i * F + noise.

    F is a single time series → PC1 should explain ~all the variance.
    """
    rng = np.random.default_rng(seed)
    n_periods, n_symbols = 200, 12
    F = rng.normal(0, 1, size=n_periods)             # the shared factor
    alphas = rng.uniform(0.5, 1.5, size=n_symbols)   # loadings
    noise = rng.normal(0, 0.05, size=(n_periods, n_symbols))
    data = np.outer(F, alphas) + noise
    idx = pd.date_range("2026-01-01", periods=n_periods, freq="D")
    cols = [f"SYM{i:02d}" for i in range(n_symbols)]
    return pd.DataFrame(data, index=idx, columns=cols)


def test_pca_recovers_injected_factor() -> None:
    pivot = _make_pivot_with_shared_factor(seed=42)
    res = run_pca(pivot, min_obs=30, n_components=5)
    assert res.explained_variance[0] > 0.7, (
        f"PC1 should dominate when one factor drives every symbol; "
        f"got {res.explained_variance[0]:.3f}"
    )
    # All loadings on PC1 should have the same sign (every symbol = +α * F).
    pc1 = res.loadings["PC1"]
    assert (pc1 > 0).all() or (pc1 < 0).all()


def test_pca_drops_symbols_below_min_obs() -> None:
    pivot = _make_pivot_with_shared_factor()
    # Knock out 90% of one symbol's observations.
    pivot["SYM00"] = np.where(np.arange(len(pivot)) < 180, np.nan, pivot["SYM00"].values)
    res = run_pca(pivot, min_obs=30, n_components=3)
    assert "SYM00" in res.dropped_symbols


def test_pca_empty_input_returns_empty_result() -> None:
    res = run_pca(pd.DataFrame())
    assert res.explained_variance.size == 0
    assert res.loadings.empty
    assert res.scores.empty


def test_nmf_recovers_two_themes() -> None:
    """Symbols 0-4 fire mainly 'mna' / 'analyst_action' → theme A.
    Symbols 5-9 fire mainly 'regulatory_export' / 'litigation' → theme B.
    NMF should assign the highest weight on A to the first group and on B
    to the second.
    """
    rows = []
    for i in range(10):
        row = {"symbol": f"SYM{i:02d}",
               "abs_mean_sentiment": 0.3 + 0.05 * (i % 3),
               "mean_materiality": 0.4 + 0.05 * (i % 2),
               "mean_geo_risk": 0.4,
               }
        is_group_a = i < 5
        for flag in EVENT_FLAGS:
            if is_group_a:
                row[f"{flag}_rate"] = 0.7 if flag in ("mna", "analyst_action") else 0.05
            else:
                row[f"{flag}_rate"] = 0.7 if flag in ("regulatory_export", "litigation") else 0.05
        rows.append(row)
    feats = pd.DataFrame(rows)
    res = run_nmf(feats, n_components=2)
    W = res.symbol_weights
    # Determine which theme column the group-A symbols dominate
    group_a = [f"SYM{i:02d}" for i in range(5)]
    group_b = [f"SYM{i:02d}" for i in range(5, 10)]
    a_theme = W.loc[group_a].mean(axis=0).idxmax()
    b_theme = W.loc[group_b].mean(axis=0).idxmax()
    assert a_theme != b_theme, "NMF collapsed both groups into the same theme"


def test_nmf_handles_too_few_symbols() -> None:
    rows = [{"symbol": "S0", "abs_mean_sentiment": 0.5,
             "mean_materiality": 0.1, "mean_geo_risk": 0.1,
             **{f"{f}_rate": 0.1 for f in EVENT_FLAGS}}]
    feats = pd.DataFrame(rows)
    res = run_nmf(feats, n_components=4)
    assert res.symbol_weights.empty
