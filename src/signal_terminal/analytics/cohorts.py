"""Symbol cohorts: hierarchical (Mantegna-distance, average linkage) and
k-means with elbow + silhouette tuning.

Pure functions of pandas inputs. Membership DataFrames are returned so the
view layer doesn't need to know the algorithm output shape.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import dendrogram, fcluster, leaves_list, linkage
from scipy.spatial.distance import squareform
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from signal_terminal.analytics.factors import NMF_FEATURE_ORDER
from signal_terminal.sectors import sector_of

# k-means inputs differ from NMF: include std_sentiment + raw mean_sentiment
# (signed). z-scored instead of [0,1]-scaled so KMeans sees comparable spreads
# across features.
KMEANS_FEATURE_ORDER = (
    "mean_sentiment",
    "std_sentiment",
    "abs_mean_sentiment",
    "mean_materiality",
    "mean_geo_risk",
    *NMF_FEATURE_ORDER[3:],  # the *_rate columns
)


@dataclass(frozen=True)
class HierarchicalResult:
    linkage_matrix: np.ndarray
    labels:    pd.Series          # index=symbol, values=cluster_id (1-based)
    symbol_order: tuple[str, ...] # left-to-right leaf order
    membership: pd.DataFrame      # one row per cluster_id (see spec §6 Tab 2)
    cut_height: float
    n_clusters: int


@dataclass(frozen=True)
class KMeansResult:
    inertia: pd.Series            # index=k, values=inertia
    silhouette: pd.Series         # index=k, values=silhouette
    chosen_k: int
    labels: pd.Series             # index=symbol, values=cluster_id (1-based)
    centroids: pd.DataFrame       # index=cluster_id, columns=feature names
    projection: pd.DataFrame      # index=symbol, columns=PC1, PC2
    membership: pd.DataFrame


# --------------------------------------------------------------------------- #
# hierarchical
# --------------------------------------------------------------------------- #
def _mantegna_distance(corr: pd.DataFrame) -> np.ndarray:
    """sqrt(2*(1-corr)) — Mantegna's distance metric on a correlation matrix.

    NaN → 0 correlation (i.e. distance √2) so masked pairs don't crash the
    linkage. View layer is responsible for warning the user when masking is
    aggressive.
    """
    c = np.array(corr.fillna(0.0).values, dtype=float, copy=True)
    np.fill_diagonal(c, 1.0)
    d2 = np.clip(2.0 * (1.0 - c), 0.0, None)
    d = np.sqrt(d2)
    np.fill_diagonal(d, 0.0)
    # enforce symmetry (floating-point fuzz can break squareform's checksum)
    d = 0.5 * (d + d.T)
    return d


def hierarchical_cluster(
    corr: pd.DataFrame, *, cut_height: float
) -> HierarchicalResult:
    """Cluster symbols on Mantegna distance, average linkage, cut at `cut_height`.

    The cut height is in distance units (0..√2) — the same axis as the
    dendrogram in the view.
    """
    if corr.empty or corr.shape[0] < 2:
        return HierarchicalResult(
            linkage_matrix=np.zeros((0, 4)),
            labels=pd.Series(dtype="int64"),
            symbol_order=tuple(),
            membership=pd.DataFrame(),
            cut_height=cut_height,
            n_clusters=0,
        )

    d = _mantegna_distance(corr)
    dvec = squareform(d, checks=False)
    Z = linkage(dvec, method="average")
    cluster_ids = fcluster(Z, t=cut_height, criterion="distance")
    labels = pd.Series(cluster_ids, index=corr.index, name="cluster_id").astype(int)
    order_idx = leaves_list(Z)
    symbol_order = tuple(corr.index[order_idx].tolist())

    membership = _build_membership(corr, labels, kind="hierarchical")
    return HierarchicalResult(
        linkage_matrix=Z,
        labels=labels,
        symbol_order=symbol_order,
        membership=membership,
        cut_height=cut_height,
        n_clusters=int(labels.nunique()),
    )


def dendrogram_coords(linkage_matrix: np.ndarray, labels: list[str]) -> dict:
    """Reuse scipy's dendrogram() to get xy coordinates for a Plotly drawing,
    without actually rendering matplotlib."""
    return dendrogram(linkage_matrix, labels=labels, no_plot=True)


# --------------------------------------------------------------------------- #
# k-means
# --------------------------------------------------------------------------- #
def _kmeans_matrix(features: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    """Slice → z-scored matrix in KMEANS_FEATURE_ORDER. Returns (raw, scaled)."""
    have = [c for c in KMEANS_FEATURE_ORDER if c in features.columns]
    raw = features.set_index("symbol")[have].copy().fillna(0.0)
    scaler = StandardScaler()
    scaled = scaler.fit_transform(raw.values)
    return raw, scaled


def kmeans_cluster(
    features: pd.DataFrame,
    *,
    k_range: range = range(2, 11),
    k: int | None = None,
) -> KMeansResult:
    """Fit KMeans across `k_range`, choose `k` (argmax silhouette if None).

    Returns the per-k inertia & silhouette curves plus the chosen-k fit:
    labels, centroids (in raw feature space, not scaled), and a 2-D PCA
    projection for the scatter plot.
    """
    if features.empty:
        empty = pd.DataFrame()
        return KMeansResult(
            inertia=pd.Series(dtype="float64"),
            silhouette=pd.Series(dtype="float64"),
            chosen_k=0,
            labels=pd.Series(dtype="int64"),
            centroids=empty,
            projection=empty,
            membership=empty,
        )

    raw, X = _kmeans_matrix(features)
    n_samples = X.shape[0]
    valid_k = [kk for kk in k_range if 2 <= kk < n_samples]
    if not valid_k:
        empty = pd.DataFrame()
        return KMeansResult(
            inertia=pd.Series(dtype="float64"),
            silhouette=pd.Series(dtype="float64"),
            chosen_k=0,
            labels=pd.Series(dtype="int64"),
            centroids=empty,
            projection=empty,
            membership=empty,
        )

    inertias, sils = {}, {}
    label_cache: dict[int, np.ndarray] = {}
    for kk in valid_k:
        model = KMeans(n_clusters=kk, n_init=20, random_state=42)
        lbl = model.fit_predict(X)
        inertias[kk] = float(model.inertia_)
        try:
            sils[kk] = float(silhouette_score(X, lbl))
        except ValueError:
            sils[kk] = float("nan")
        label_cache[kk] = lbl

    sil_series = pd.Series(sils).sort_index()
    inertia_series = pd.Series(inertias).sort_index()

    if k is None:
        finite = sil_series.dropna()
        chosen_k = int(finite.idxmax()) if not finite.empty else valid_k[0]
    else:
        chosen_k = int(k)
        if chosen_k not in label_cache:
            model = KMeans(n_clusters=chosen_k, n_init=20, random_state=42)
            label_cache[chosen_k] = model.fit_predict(X)
            inertia_series.loc[chosen_k] = float(model.inertia_)
            try:
                sil_series.loc[chosen_k] = float(silhouette_score(X, label_cache[chosen_k]))
            except ValueError:
                sil_series.loc[chosen_k] = float("nan")
            sil_series = sil_series.sort_index()
            inertia_series = inertia_series.sort_index()

    chosen_labels = label_cache[chosen_k] + 1  # 1-based cluster_id
    labels = pd.Series(chosen_labels, index=raw.index, name="cluster_id").astype(int)

    # centroids in raw feature space (interpretable rows in the centroid heatmap)
    raw_with_label = raw.copy()
    raw_with_label["cluster_id"] = labels.values
    centroids = (
        raw_with_label.groupby("cluster_id")[list(raw.columns)].mean()
        .sort_index()
    )

    # 2-D projection for the scatter — PCA on the scaled matrix
    proj_k = int(min(2, X.shape[1]))
    pca = PCA(n_components=proj_k, svd_solver="full")
    proj = pca.fit_transform(X)
    if proj.shape[1] == 1:
        proj = np.column_stack([proj, np.zeros(len(proj))])
    projection = pd.DataFrame(
        proj[:, :2], index=raw.index, columns=["PC1", "PC2"]
    )

    membership = _build_membership(raw, labels, kind="kmeans", centroids=centroids)
    return KMeansResult(
        inertia=inertia_series,
        silhouette=sil_series,
        chosen_k=chosen_k,
        labels=labels,
        centroids=centroids,
        projection=projection,
        membership=membership,
    )


# --------------------------------------------------------------------------- #
# membership table builder (shared)
# --------------------------------------------------------------------------- #
def _build_membership(
    inputs: pd.DataFrame,
    labels: pd.Series,
    *,
    kind: str,
    centroids: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Membership DataFrame: one row per cluster, columns per spec §6.

    For hierarchical, `inputs` is the correlation matrix (used for
    mean_intra_corr). For k-means, `inputs` is the raw feature matrix and
    `centroids` is appended verbatim.
    """
    if labels.empty:
        return pd.DataFrame()

    rows = []
    for cid, group in labels.groupby(labels):
        symbols = sorted(group.index.tolist())
        sectors = pd.Series(symbols).map(sector_of)
        row = {
            "cluster_id": int(cid),
            "n_members": int(len(symbols)),
            "symbols": ", ".join(symbols),
            "mean_sector": _modal_sector(sectors),
        }
        if kind == "hierarchical" and isinstance(inputs, pd.DataFrame) and not inputs.empty:
            sub = inputs.loc[symbols, symbols].values
            n = len(symbols)
            if n >= 2:
                triu = sub[np.triu_indices(n, k=1)]
                triu = triu[~np.isnan(triu)]
                row["mean_intra_corr"] = float(triu.mean()) if triu.size else float("nan")
            else:
                row["mean_intra_corr"] = float("nan")
        if kind == "kmeans" and centroids is not None and cid in centroids.index:
            for c in centroids.columns:
                row[f"centroid_{c}"] = float(centroids.loc[cid, c])
        rows.append(row)
    df = pd.DataFrame(rows).sort_values("cluster_id").reset_index(drop=True)
    return df


def _modal_sector(s: pd.Series) -> str:
    if s.empty:
        return ""
    counts = s.value_counts()
    top = counts.index[0]
    if len(counts) > 1 and counts.iloc[1] == counts.iloc[0]:
        return "mixed"
    return str(top)
