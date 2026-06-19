"""Latent factor models: PCA on time × symbol sentiment, NMF on per-symbol
non-negative feature vectors.

Pure functions of pandas inputs; no DB, no Streamlit. Wrapped at the view layer.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.decomposition import NMF, PCA

from signal_terminal.style import EVENT_FLAGS


@dataclass(frozen=True)
class PCAResult:
    explained_variance: np.ndarray   # shape (n_components,)
    loadings:  pd.DataFrame          # index=symbol,  columns=PC1..PCk
    scores:    pd.DataFrame          # index=period,  columns=PC1..PCk
    dropped_symbols: tuple[str, ...]
    n_observations: int              # number of time periods used


@dataclass(frozen=True)
class NMFResult:
    components:     pd.DataFrame     # index=Theme1..K, columns=feature names
    symbol_weights: pd.DataFrame     # index=symbol,    columns=Theme1..K
    feature_columns: tuple[str, ...]
    reconstruction_err: float


# --------------------------------------------------------------------------- #
# PCA
# --------------------------------------------------------------------------- #
def run_pca(
    pivot: pd.DataFrame, *, min_obs: int = 30, n_components: int = 10
) -> PCAResult:
    """Fit PCA on the time × symbol pivot.

    Pipeline:
      1. Drop symbols with fewer than `min_obs` non-NaN periods.
      2. Z-score each symbol column independently (mean/std over its own series).
      3. Impute remaining NaN to 0 — post-standardization, so 0 = symbol mean,
         which is the maximally neutral fill.
      4. PCA(n_components, svd_solver='full'). Cap n_components by min(shape).
    """
    if pivot.empty:
        empty = pd.DataFrame()
        return PCAResult(np.zeros(0), empty, empty, tuple(), 0)

    n_obs = pivot.notna().sum(axis=0)
    keep = n_obs[n_obs >= int(min_obs)].index
    dropped = tuple(c for c in pivot.columns if c not in keep)
    sub = pivot[keep]
    if sub.shape[1] < 2 or sub.shape[0] < 2:
        empty = pd.DataFrame()
        return PCAResult(np.zeros(0), empty, empty, dropped, int(sub.shape[0]))

    mu = sub.mean(axis=0)
    sigma = sub.std(axis=0).replace(0.0, 1.0)
    z = ((sub - mu) / sigma).fillna(0.0)

    k = int(min(n_components, z.shape[1], z.shape[0]))
    pca = PCA(n_components=k, svd_solver="full")
    scores = pca.fit_transform(z.values)  # (n_periods, k)
    loadings = pca.components_.T          # (n_symbols, k) — V^T transposed back

    pc_cols = [f"PC{i+1}" for i in range(k)]
    loadings_df = pd.DataFrame(loadings, index=z.columns, columns=pc_cols)
    scores_df   = pd.DataFrame(scores,   index=z.index,   columns=pc_cols)
    return PCAResult(
        explained_variance=pca.explained_variance_ratio_,
        loadings=loadings_df,
        scores=scores_df,
        dropped_symbols=dropped,
        n_observations=int(z.shape[0]),
    )


# --------------------------------------------------------------------------- #
# NMF
# --------------------------------------------------------------------------- #
NMF_FEATURE_ORDER = (
    "abs_mean_sentiment",
    "mean_materiality",
    "mean_geo_risk",
    *[f"{f}_rate" for f in EVENT_FLAGS],
)


def _nmf_feature_matrix(features: pd.DataFrame) -> pd.DataFrame:
    """Slice → [0,1]-scaled per-symbol matrix in NMF_FEATURE_ORDER.

    Inputs are already in [0,1] (rates) or [0, 1+] (sentiment magnitude, capped
    at 1 by construction). Per-feature min-max so NMF doesn't latch onto the
    feature with the widest raw range.
    """
    have = [c for c in NMF_FEATURE_ORDER if c in features.columns]
    m = features.set_index("symbol")[have].copy().fillna(0.0)
    m = m.clip(lower=0.0)
    lo = m.min(axis=0)
    hi = m.max(axis=0).replace(0.0, 1.0)
    rng = (hi - lo).replace(0.0, 1.0)
    return (m - lo) / rng


def run_nmf(features: pd.DataFrame, *, n_components: int = 4) -> NMFResult:
    """Fit NMF on per-symbol non-negative features.

    `features` is the output of data.per_symbol_features(). Returns the
    components (themes × features) and symbol_weights (symbols × themes).
    """
    if features.empty:
        empty = pd.DataFrame()
        return NMFResult(empty, empty, NMF_FEATURE_ORDER, 0.0)
    m = _nmf_feature_matrix(features)
    if m.empty or m.shape[0] < n_components:
        empty = pd.DataFrame()
        return NMFResult(empty, empty, tuple(m.columns), 0.0)

    k = int(min(n_components, m.shape[0], m.shape[1]))
    model = NMF(n_components=k, init="nndsvd", random_state=42, max_iter=500)
    W = model.fit_transform(m.values)  # (n_symbols, k)
    H = model.components_              # (k, n_features)

    theme_cols = [f"Theme {i+1}" for i in range(k)]
    components_df = pd.DataFrame(H, index=theme_cols, columns=m.columns)
    weights_df    = pd.DataFrame(W, index=m.index,    columns=theme_cols)
    return NMFResult(
        components=components_df,
        symbol_weights=weights_df,
        feature_columns=tuple(m.columns),
        reconstruction_err=float(model.reconstruction_err_),
    )
