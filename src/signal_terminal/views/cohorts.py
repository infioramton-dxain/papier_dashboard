"""COHORTS — which symbols group together by sentiment co-movement and behavior?

Spearman correlation → hierarchical clustering (Mantegna distance, average
linkage) → dendrogram-reordered heatmap with a live cut-height slider.
KMeans on per-symbol features with elbow + silhouette tuning, 2-D PCA
projection, and a centroid feature heatmap.

Every clustering chart is followed by its membership table + CSV download
(spec §6, §7).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from signal_terminal.analytics import cohorts as co
from signal_terminal.analytics import data as andata
from signal_terminal.config import Config
from signal_terminal.style import (DIM, FAINT, GRIDCOLOR, PLOTLY_CONFIG,
                                    SURFACE, TEXT_HI, layout)
from signal_terminal.views import _analytics_chrome as chrome

# Qualitative cluster palette — fixed by cluster_id so cluster 1 looks the same
# in every chart on this tab (spec §7 visual style).
CLUSTER_PALETTE = (
    "#6ea8fe", "#e0a458", "#bb9af7", "#7ec9c9", "#d29922",
    "#30a46c", "#e5484d", "#a371f7", "#56b6c2", "#f5a97f",
)


def cluster_color(cid: int) -> str:
    if cid is None or cid <= 0:
        return "#4d5560"
    return CLUSTER_PALETTE[(int(cid) - 1) % len(CLUSTER_PALETTE)]


# --------------------------------------------------------------------------- #
# cached compute
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=3600, show_spinner=False)
def _corr(db_path_str: str, filters: andata.Filters, min_joint_obs: int) -> pd.DataFrame:
    return andata.correlation_matrix(db_path_str, filters, min_joint_obs=min_joint_obs)


@st.cache_data(ttl=3600, show_spinner=False)
def _features(db_path_str: str, filters: andata.Filters) -> pd.DataFrame:
    return andata.per_symbol_features(db_path_str, filters)


@st.cache_data(ttl=3600, show_spinner=False)
def _hierarchical(db_path_str: str, filters: andata.Filters, min_joint_obs: int,
                  cut_height: float):
    corr = _corr(db_path_str, filters, min_joint_obs)
    return corr, co.hierarchical_cluster(corr, cut_height=cut_height)


@st.cache_data(ttl=3600, show_spinner=False)
def _kmeans(db_path_str: str, filters: andata.Filters, k: int | None):
    feats = _features(db_path_str, filters)
    return feats, co.kmeans_cluster(feats, k=k)


# --------------------------------------------------------------------------- #
# entrypoint
# --------------------------------------------------------------------------- #
def render(cfg: Config) -> None:
    if not chrome.require_live_db(cfg):
        return
    st.header("Which symbols group together by sentiment co-movement and behavior?")
    st.markdown(
        f"<div style='color:{DIM}; font-size:12px; line-height:1.55; margin-top:-6px; "
        f"margin-bottom:14px;'>Hierarchical clustering on Mantegna distance "
        f"surfaces correlation-block structure; k-means on per-symbol behavior "
        f"surfaces feature-based cohorts. Both label every symbol — see the "
        f"membership table immediately below each chart.</div>",
        unsafe_allow_html=True,
    )

    filters = chrome.current_filters()
    ai_on = chrome.ai_enabled()
    db_str = str(cfg.db_path)

    # --- per-tab tuning row -------------------------------------------------
    tune = st.columns([1.4, 1.4, 1.4, 1.4, 4])
    with tune[0]:
        min_joint = st.number_input(
            "MIN JOINT OBS", min_value=5, max_value=200, value=20, step=5,
            key="an_co_min_joint",
            help="Mask symbol pairs with fewer overlapping periods than this.",
        )
    with tune[1]:
        cut = st.slider(
            "CUT HEIGHT", min_value=0.05, max_value=1.40, value=0.80, step=0.05,
            key="an_co_cut",
            help="Hierarchical-cluster cut, in Mantegna-distance units (0..√2).",
        )
    with tune[2]:
        k_override = st.number_input(
            "FORCE k", min_value=0, max_value=10, value=0, step=1,
            key="an_co_k_override",
            help="0 = argmax silhouette across k=2..10.",
        )
    with tune[3]:
        st.markdown(
            f"<div style='color:{FAINT}; font-size:10px; letter-spacing:1.5px; "
            f"margin-top:32px;'>0 = AUTO-PICK</div>",
            unsafe_allow_html=True,
        )

    # --- compute ------------------------------------------------------------
    with st.spinner("Computing correlation + clusters…"):
        corr, hres = _hierarchical(db_str, filters, int(min_joint), float(cut))
        feats, kres = _kmeans(db_str, filters, None if k_override == 0 else int(k_override))

    if corr.empty and feats.empty:
        st.warning("Not enough data at current filters to run cohort analysis.")
        return

    # ---------------------------- 2.1 raw heatmap --------------------------
    chrome.panel(
        "corr_raw", "2.1 · Raw correlation heatmap — alphabetical order",
        lambda: _draw_corr(corr.sort_index().sort_index(axis=1), masked_pct=_masked_pct(corr)),
        summary=_corr_summary(corr),
        ai_enabled=ai_on,
    )

    # ---------------------------- 2.2 reordered + 2.2.t table -------------
    with st.container(border=True):
        st.subheader("2.2 · Dendrogram-reordered correlation heatmap")
        reorder = list(hres.symbol_order) if hres.symbol_order else list(corr.index)
        _draw_corr(corr.loc[reorder, reorder] if not corr.empty else corr,
                    masked_pct=_masked_pct(corr), cluster_strip=hres.labels.reindex(reorder))
        chrome.static_description("corr_reordered")
        if ai_on:
            chrome.dynamic_description("corr_reordered", _hier_summary(hres))
        chrome.membership_table(
            hres.membership, key="hier_membership",
            filename="cohorts_hierarchical.csv",
            caption="2.2.t · COHORT MEMBERSHIP (HIERARCHICAL)",
        )

    # ---------------------------- 2.3 dendrogram ---------------------------
    chrome.panel(
        "dendrogram", "2.3 · Dendrogram — Mantegna distance, average linkage",
        lambda: _draw_dendrogram(hres, cut_height=float(cut)),
        summary=_hier_summary(hres),
        ai_enabled=ai_on,
    )

    # ---------------------------- 2.4 + 2.6 side-by-side -------------------
    sbs = st.columns(2, gap="small")
    with sbs[0]:
        chrome.panel(
            "kmeans_tuning", "2.4 · K-means tuning — inertia + silhouette",
            lambda: _draw_kmeans_tuning(kres),
            summary={
                "chosen_k": int(kres.chosen_k),
                "silhouette": {int(k): round(float(v), 3) for k, v in kres.silhouette.dropna().items()},
            },
            ai_enabled=ai_on,
        )
    with sbs[1]:
        chrome.panel(
            "kmeans_centroids", "2.6 · K-means centroid feature heatmap",
            lambda: _draw_centroids(kres),
            summary=_centroid_summary(kres),
            ai_enabled=ai_on,
        )

    # ---------------------------- 2.5 projection + 2.5.t table --------------
    with st.container(border=True):
        st.subheader("2.5 · K-means 2-D projection")
        _draw_projection(kres)
        chrome.static_description("kmeans_projection")
        if ai_on:
            chrome.dynamic_description("kmeans_projection",
                                   {"chosen_k": int(kres.chosen_k),
                                    "n_symbols": int(len(kres.labels))})
        chrome.membership_table(
            kres.membership, key="kmeans_membership",
            filename="cohorts_kmeans.csv",
            caption="2.5.t · COHORT MEMBERSHIP (K-MEANS)",
        )


# --------------------------------------------------------------------------- #
# drawers
# --------------------------------------------------------------------------- #
def _draw_corr(corr: pd.DataFrame, *, masked_pct: float = 0.0,
                cluster_strip: pd.Series | None = None) -> None:
    if corr is None or corr.empty:
        st.info("No correlation matrix at current filters.")
        return
    fig = go.Figure(go.Heatmap(
        z=corr.values,
        x=list(corr.columns), y=list(corr.index),
        colorscale=chrome.DIVERGING_RDBU,
        zmid=0.0, zmin=-1.0, zmax=1.0,
        colorbar=dict(thickness=8, tickfont=dict(size=9, color=DIM), len=0.85),
        hovertemplate="%{y} × %{x}: %{z:.2f}<extra></extra>",
    ))
    n = corr.shape[0]
    fig.update_layout(
        **layout(
            height=min(720, max(360, 6 * n)),
            margin=dict(l=60, r=20, t=10, b=40),
            xaxis=dict(gridcolor=GRIDCOLOR, showticklabels=n <= 60,
                       tickangle=-60, tickfont=dict(size=8, color=DIM)),
            yaxis=dict(gridcolor=GRIDCOLOR, autorange="reversed",
                       showticklabels=n <= 60, tickfont=dict(size=8, color=TEXT_HI)),
        ),
    )
    if cluster_strip is not None and not cluster_strip.empty:
        # Build a per-row cluster color strip on the right edge as a secondary
        # heatmap trace (Plotly doesn't have native side-annotation strips).
        cmap = {int(c): cluster_color(int(c)) for c in cluster_strip.dropna().unique()}
        # build a fake colorscale stepping through clusters in order
        sorted_cids = sorted(cmap.keys())
        if sorted_cids:
            steps = []
            n_c = len(sorted_cids)
            for i, cid in enumerate(sorted_cids):
                t = i / max(1, n_c - 1) if n_c > 1 else 0.0
                steps.append([t, cmap[cid]])
            # mapping: cluster_id -> 0..1 index
            id_to_pos = {cid: (i / max(1, n_c - 1) if n_c > 1 else 0.0)
                         for i, cid in enumerate(sorted_cids)}
            z_strip = np.array([[id_to_pos[int(c)]] for c in cluster_strip]).reshape(-1, 1)
            fig.add_trace(go.Heatmap(
                z=z_strip,
                x=["cluster"], y=list(cluster_strip.index),
                colorscale=steps if n_c > 1 else [[0, cmap[sorted_cids[0]]], [1, cmap[sorted_cids[0]]]],
                showscale=False,
                xaxis="x2",
                hovertemplate="%{y} · cluster %{customdata}<extra></extra>",
                customdata=np.array(cluster_strip.values.reshape(-1, 1)),
            ))
            fig.update_layout(
                xaxis2=dict(domain=[0.97, 1.0], showticklabels=False,
                             showgrid=False, zeroline=False),
                xaxis=dict(domain=[0.0, 0.96], gridcolor=GRIDCOLOR,
                           showticklabels=n <= 60, tickangle=-60,
                           tickfont=dict(size=8, color=DIM)),
            )
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
    if masked_pct > 0:
        st.markdown(
            f"<div style='color:{FAINT}; font-size:10px; letter-spacing:1px; "
            f"margin-top:-2px;'>{masked_pct:.1f}% of off-diagonal cells masked "
            f"for low joint observations.</div>",
            unsafe_allow_html=True,
        )


def _draw_dendrogram(hres: co.HierarchicalResult, *, cut_height: float) -> None:
    if hres.linkage_matrix.size == 0:
        st.info("Hierarchical clustering did not run — not enough symbols.")
        return
    coords = co.dendrogram_coords(hres.linkage_matrix, list(hres.labels.index))
    icoord = np.array(coords["icoord"])
    dcoord = np.array(coords["dcoord"])
    leaves = coords["ivl"]
    fig = go.Figure()
    for xs, ys in zip(icoord, dcoord):
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines",
            line=dict(color="#6ea8fe", width=1.0),
            hoverinfo="skip", showlegend=False,
        ))
    fig.add_hline(y=cut_height, line=dict(color="#e0a458", width=1.0, dash="dash"))
    n_leaf = len(leaves)
    fig.update_layout(
        **layout(
            height=380,
            margin=dict(l=46, r=16, t=12, b=60),
            xaxis=dict(showgrid=False, zeroline=False,
                       tickvals=[5 + 10 * i for i in range(n_leaf)],
                       ticktext=leaves, tickangle=-80,
                       tickfont=dict(size=8, color=DIM)),
            yaxis=dict(gridcolor=GRIDCOLOR,
                       title=dict(text="distance √(2(1−ρ))", font=dict(size=10, color=DIM))),
        ),
    )
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def _draw_kmeans_tuning(kres: co.KMeansResult) -> None:
    if kres.inertia.empty:
        st.info("K-means did not run — not enough symbols.")
        return
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=kres.inertia.index, y=kres.inertia.values,
        name="inertia", mode="lines+markers",
        line=dict(color="#6ea8fe", width=1.4),
        marker=dict(size=6),
        yaxis="y",
        hovertemplate="k=%{x}<br>inertia %{y:.1f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=kres.silhouette.index, y=kres.silhouette.values,
        name="silhouette", mode="lines+markers",
        line=dict(color="#e0a458", width=1.4),
        marker=dict(size=6),
        yaxis="y2",
        hovertemplate="k=%{x}<br>silhouette %{y:.3f}<extra></extra>",
    ))
    fig.add_vline(x=kres.chosen_k, line=dict(color="#d29922", width=1.0, dash="dash"))
    fig.update_layout(
        **layout(
            height=320,
            showlegend=True,
            legend=dict(orientation="h", y=-0.18, font=dict(size=10, color=DIM)),
            xaxis=dict(gridcolor=GRIDCOLOR, dtick=1,
                       title=dict(text="k", font=dict(size=10, color=DIM))),
            yaxis=dict(gridcolor=GRIDCOLOR,
                       title=dict(text="inertia", font=dict(size=10, color="#6ea8fe"))),
            yaxis2=dict(overlaying="y", side="right", showgrid=False,
                         title=dict(text="silhouette", font=dict(size=10, color="#e0a458"))),
        ),
    )
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def _draw_projection(kres: co.KMeansResult) -> None:
    if kres.projection.empty:
        st.info("K-means projection unavailable.")
        return
    df = kres.projection.copy()
    df["cluster_id"] = kres.labels.reindex(df.index).fillna(0).astype(int)
    fig = go.Figure()
    for cid, sub in df.groupby("cluster_id"):
        fig.add_trace(go.Scatter(
            x=sub["PC1"], y=sub["PC2"], mode="markers+text",
            text=sub.index, textposition="top center",
            textfont=dict(size=8, color=DIM),
            marker=dict(size=8, color=cluster_color(int(cid)),
                        line=dict(color=SURFACE, width=0.5)),
            name=f"cluster {int(cid)}",
            hovertemplate="<b>%{text}</b><br>PC1 %{x:.2f}<br>PC2 %{y:.2f}<extra>cluster " + str(int(cid)) + "</extra>",
        ))
    fig.update_layout(
        **layout(
            height=460,
            showlegend=True,
            legend=dict(orientation="h", y=-0.14, font=dict(size=10, color=DIM)),
            xaxis=dict(gridcolor=GRIDCOLOR, zeroline=True, zerolinecolor="#2b333d",
                       title=dict(text="PC1 (features)", font=dict(size=10, color=DIM))),
            yaxis=dict(gridcolor=GRIDCOLOR, zeroline=True, zerolinecolor="#2b333d",
                       title=dict(text="PC2 (features)", font=dict(size=10, color=DIM))),
        ),
    )
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def _draw_centroids(kres: co.KMeansResult) -> None:
    if kres.centroids.empty:
        st.info("K-means did not run — not enough symbols.")
        return
    C = kres.centroids
    # Normalize per column so the heatmap shows relative profile across
    # clusters, not absolute feature scale.
    col_min = C.min(axis=0)
    col_max = C.max(axis=0)
    rng = (col_max - col_min).replace(0.0, 1.0)
    Cn = (C - col_min) / rng
    fig = go.Figure(go.Heatmap(
        z=Cn.values,
        x=[c.replace("_rate", "").replace("_", " ").upper() for c in Cn.columns],
        y=[f"cluster {int(cid)}" for cid in Cn.index],
        colorscale=chrome.SEQUENTIAL_BLUE,
        zmin=0.0, zmax=1.0,
        colorbar=dict(thickness=8, tickfont=dict(size=9, color=DIM), len=0.85),
        hovertemplate="%{y} · %{x}: %{z:.2f} (rel)<extra></extra>",
    ))
    fig.update_layout(
        **layout(
            height=max(220, 36 * Cn.shape[0] + 80),
            margin=dict(l=80, r=20, t=10, b=80),
            xaxis=dict(gridcolor=GRIDCOLOR, tickangle=-40, tickfont=dict(size=9, color=DIM)),
            yaxis=dict(gridcolor=GRIDCOLOR, autorange="reversed",
                       tickfont=dict(size=10, color=TEXT_HI)),
        ),
    )
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


# --------------------------------------------------------------------------- #
# summary helpers
# --------------------------------------------------------------------------- #
def _masked_pct(corr: pd.DataFrame) -> float:
    if corr.empty:
        return 0.0
    arr = corr.values
    n = arr.shape[0]
    # off-diagonal cells = n*(n-1)
    nan = np.isnan(arr).sum() - 0  # diagonal is 1.0, not NaN
    total = n * (n - 1)
    if total == 0:
        return 0.0
    return 100.0 * float(nan) / float(total)


def _corr_summary(corr: pd.DataFrame) -> dict:
    if corr.empty:
        return {}
    vals = corr.values.copy()
    np.fill_diagonal(vals, np.nan)
    flat = vals[~np.isnan(vals)]
    return {
        "n_symbols": int(corr.shape[0]),
        "mean_corr": round(float(np.mean(flat)), 3) if flat.size else 0.0,
        "p95_corr":  round(float(np.percentile(flat, 95)), 3) if flat.size else 0.0,
        "p05_corr":  round(float(np.percentile(flat, 5)), 3) if flat.size else 0.0,
        "masked_pct": round(_masked_pct(corr), 1),
    }


def _hier_summary(hres: co.HierarchicalResult) -> dict:
    if hres.membership is None or hres.membership.empty:
        return {"n_clusters": 0}
    sizes = hres.membership["n_members"].tolist()
    return {
        "cut_height": round(float(hres.cut_height), 2),
        "n_clusters": int(hres.n_clusters),
        "largest_cluster_n": int(max(sizes) if sizes else 0),
        "singleton_clusters": int(sum(1 for s in sizes if s == 1)),
    }


def _centroid_summary(kres: co.KMeansResult) -> dict:
    if kres.centroids.empty:
        return {}
    out = {}
    for cid, row in kres.centroids.iterrows():
        out[f"cluster {int(cid)}"] = {
            "top_features": [str(c) for c in row.nlargest(3).index.tolist()],
        }
    return out
