"""FACTORS — what latent drivers exist in symbol sentiment?

PCA on the time × symbol pivot + NMF on per-symbol non-negative features.
Each chart is wrapped in the standard analytics panel (chrome.panel) with a
static 'how to read' line and an optional Ollama-generated takeaway.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from signal_terminal.analytics import data as andata
from signal_terminal.analytics import factors as fa
from signal_terminal.config import Config
from signal_terminal.sectors import sector_of
from signal_terminal.style import (DIM, GRIDCOLOR, PLOTLY_CONFIG, SECTOR_COLOR,
                                    SURFACE, TEXT_HI, layout)
from signal_terminal.views import _analytics_chrome as chrome


# --------------------------------------------------------------------------- #
# cached compute (keyed off filters)
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=3600, show_spinner=False)
def _pivot(db_path_str: str, filters: andata.Filters) -> pd.DataFrame:
    return andata.pivot_sentiment(db_path_str, filters)


@st.cache_data(ttl=3600, show_spinner=False)
def _features(db_path_str: str, filters: andata.Filters) -> pd.DataFrame:
    return andata.per_symbol_features(db_path_str, filters)


@st.cache_data(ttl=3600, show_spinner=False)
def _run_pca(db_path_str: str, filters: andata.Filters, min_obs: int, n_components: int):
    pivot = _pivot(db_path_str, filters)
    return fa.run_pca(pivot, min_obs=min_obs, n_components=n_components)


@st.cache_data(ttl=3600, show_spinner=False)
def _run_nmf(db_path_str: str, filters: andata.Filters, n_components: int):
    features = _features(db_path_str, filters)
    return fa.run_nmf(features, n_components=n_components)


# --------------------------------------------------------------------------- #
# entrypoint
# --------------------------------------------------------------------------- #
def render(cfg: Config) -> None:
    if not chrome.require_live_db(cfg):
        return
    st.header("What latent drivers exist in symbol sentiment?")
    st.markdown(
        f"<div style='color:{DIM}; font-size:12px; line-height:1.55; margin-top:-6px; "
        f"margin-bottom:14px;'>PCA decomposes the time × symbol sentiment matrix "
        f"into orthogonal factors; NMF finds additive, non-negative themes across "
        f"per-symbol features. Together they expose the unobserved drivers behind "
        f"co-movement.</div>",
        unsafe_allow_html=True,
    )

    filters = chrome.current_filters()
    ai_on = chrome.ai_enabled()
    db_str = str(cfg.db_path)

    # --- per-tab tuning row -------------------------------------------------
    tune = st.columns([1.2, 1.2, 1.2, 6])
    with tune[0]:
        min_obs = st.number_input(
            "MIN OBS / SYMBOL", min_value=5, max_value=500, value=30, step=5,
            key="an_pca_min_obs",
            help="Symbols with fewer non-NaN periods than this are dropped from PCA.",
        )
    with tune[1]:
        n_pca = st.number_input(
            "PCA COMPONENTS", min_value=2, max_value=20, value=10, step=1,
            key="an_pca_n",
        )
    with tune[2]:
        n_nmf = st.number_input(
            "NMF THEMES (k)", min_value=2, max_value=12, value=4, step=1,
            key="an_nmf_k",
        )

    # --- compute ------------------------------------------------------------
    with st.spinner("Fitting PCA + NMF…"):
        pca_res = _run_pca(db_str, filters, int(min_obs), int(n_pca))
        nmf_res = _run_nmf(db_str, filters, int(n_nmf))

    if pca_res.loadings.empty and nmf_res.symbol_weights.empty:
        st.warning("Not enough data at current filters to fit factors. "
                   "Widen the date range or include more symbols.")
        return

    if pca_res.dropped_symbols:
        st.caption(
            f"PCA: dropped {len(pca_res.dropped_symbols)} symbols with fewer than "
            f"{int(min_obs)} non-NaN periods — {pca_res.n_observations} time observations used."
        )

    # ---------------------------- 1.1 scree --------------------------------
    chrome.panel(
        "pca_scree", "1.1 · PCA scree — explained variance per component",
        lambda: _draw_scree(pca_res),
        summary={
            "explained_variance": [round(float(x), 4) for x in pca_res.explained_variance[:10]],
            "n_symbols": int(pca_res.loadings.shape[0]),
            "n_observations": int(pca_res.n_observations),
        },
        ai_enabled=ai_on,
    )

    # ---------------------------- 1.2 loadings ------------------------------
    chrome.panel(
        "pca_loadings", "1.2 · PCA loadings heatmap — symbols × PC1–PC5",
        lambda: _draw_loadings(pca_res),
        summary={
            "top_pc1_positive": _top_n(pca_res.loadings, "PC1", n=8, asc=False),
            "top_pc1_negative": _top_n(pca_res.loadings, "PC1", n=8, asc=True),
            "top_pc2_positive": _top_n(pca_res.loadings, "PC2", n=8, asc=False) if "PC2" in pca_res.loadings.columns else [],
        },
        ai_enabled=ai_on,
    )

    # ---------------------------- 1.3 biplot --------------------------------
    chrome.panel(
        "pca_biplot", "1.3 · PCA biplot — PC1 × PC2 with sector coloring",
        lambda: _draw_biplot(pca_res),
        summary={
            "pc1_pc2_evr": [
                round(float(pca_res.explained_variance[0]), 3) if len(pca_res.explained_variance) > 0 else 0.0,
                round(float(pca_res.explained_variance[1]), 3) if len(pca_res.explained_variance) > 1 else 0.0,
            ],
            "n_symbols": int(pca_res.loadings.shape[0]),
            "sectors_present": sorted(set(pca_res.loadings.index.map(sector_of))),
        },
        ai_enabled=ai_on,
    )

    # ---------------------------- 1.4 scores --------------------------------
    chrome.panel(
        "pca_scores", "1.4 · Factor score time series — PC1, PC2, PC3",
        lambda: _draw_scores(pca_res),
        summary=_score_summary(pca_res),
        ai_enabled=ai_on,
    )

    # ---------------------------- 1.5 NMF components ------------------------
    chrome.panel(
        "nmf_components", "1.5 · NMF component heatmap — themes × features",
        lambda: _draw_nmf_components(nmf_res),
        summary={
            "n_themes": int(nmf_res.components.shape[0]) if not nmf_res.components.empty else 0,
            "top_feature_per_theme": _top_feature_per_theme(nmf_res),
            "reconstruction_err": round(float(nmf_res.reconstruction_err), 3),
        },
        ai_enabled=ai_on,
    )

    # ---------------------------- 1.6 NMF symbol weights table --------------
    with st.container(border=True):
        st.subheader("1.6 · NMF symbol weights — soft theme membership")
        if nmf_res.symbol_weights.empty:
            st.info("Not enough symbols to fit NMF at current filters.")
        else:
            tbl = nmf_res.symbol_weights.copy().round(3)
            tbl.insert(0, "sector", [sector_of(s) for s in tbl.index])
            tbl = tbl.reset_index().rename(columns={"index": "symbol"})
            st.dataframe(tbl, hide_index=True, use_container_width=True)
            st.download_button(
                "DOWNLOAD CSV",
                data=tbl.to_csv(index=False).encode("utf-8"),
                file_name="nmf_symbol_weights.csv",
                mime="text/csv",
                key="dl_nmf_weights",
            )
            chrome.static_description("nmf_weights")


# --------------------------------------------------------------------------- #
# chart drawers
# --------------------------------------------------------------------------- #
def _draw_scree(res: fa.PCAResult) -> None:
    if res.explained_variance.size == 0:
        st.info("PCA did not run — no data.")
        return
    evr = res.explained_variance
    k = len(evr)
    fig = go.Figure(go.Bar(
        x=[f"PC{i+1}" for i in range(k)],
        y=[float(v) for v in evr],
        marker=dict(color="#6ea8fe", line=dict(color="#3d5a8a", width=0.5)),
        hovertemplate="%{x}: %{y:.2%}<extra></extra>",
    ))
    fig.update_layout(
        **layout(
            height=280,
            xaxis=dict(gridcolor=GRIDCOLOR, title=None),
            yaxis=dict(gridcolor=GRIDCOLOR, title=dict(text="explained variance", font=dict(color=DIM, size=10)), tickformat=".0%"),
        ),
    )
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def _draw_loadings(res: fa.PCAResult) -> None:
    if res.loadings.empty:
        st.info("PCA did not run — no data.")
        return
    k = min(5, res.loadings.shape[1])
    L = res.loadings.iloc[:, :k]
    # Sort symbols by PC1 to make the heatmap structure visible.
    L = L.reindex(L["PC1"].sort_values(ascending=False).index)
    vmax = float(np.nanmax(np.abs(L.values))) or 1.0
    fig = go.Figure(go.Heatmap(
        z=L.values,
        x=list(L.columns),
        y=list(L.index),
        colorscale=chrome.DIVERGING_RDBU,
        zmid=0.0, zmin=-vmax, zmax=vmax,
        colorbar=dict(thickness=8, tickfont=dict(size=9, color=DIM), len=0.85),
        hovertemplate="%{y} · %{x}: %{z:.3f}<extra></extra>",
    ))
    h = max(320, min(900, int(20 * L.shape[0])))
    fig.update_layout(
        **layout(
            height=h,
            margin=dict(l=60, r=20, t=10, b=30),
            xaxis=dict(gridcolor=GRIDCOLOR, side="top"),
            yaxis=dict(gridcolor=GRIDCOLOR, autorange="reversed", tickfont=dict(size=9, color=TEXT_HI)),
        ),
    )
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def _draw_biplot(res: fa.PCAResult) -> None:
    if res.loadings.empty or "PC2" not in res.loadings.columns:
        st.info("Need at least 2 PCs to draw the biplot.")
        return
    L = res.loadings
    df = pd.DataFrame({
        "symbol": L.index,
        "PC1": L["PC1"].values,
        "PC2": L["PC2"].values,
    })
    df["sector"] = df["symbol"].map(sector_of)
    fig = go.Figure()
    for sec in sorted(df["sector"].unique()):
        sub = df[df["sector"] == sec]
        fig.add_trace(go.Scatter(
            x=sub["PC1"], y=sub["PC2"],
            mode="markers+text",
            text=sub["symbol"],
            textposition="top center",
            textfont=dict(size=9, color=DIM),
            marker=dict(size=8, color=SECTOR_COLOR.get(sec, SECTOR_COLOR["Other"]),
                        line=dict(color=SURFACE, width=0.5)),
            name=sec,
            hovertemplate="<b>%{text}</b><br>PC1 %{x:.3f}<br>PC2 %{y:.3f}<extra>" + sec + "</extra>",
        ))
    evr = res.explained_variance
    fig.update_layout(
        **layout(
            height=480,
            showlegend=True,
            legend=dict(orientation="h", y=-0.12, font=dict(size=10, color=DIM)),
            xaxis=dict(gridcolor=GRIDCOLOR, zeroline=True, zerolinecolor="#2b333d",
                       title=dict(text=f"PC1  ({evr[0]:.0%})", font=dict(size=10, color=DIM))),
            yaxis=dict(gridcolor=GRIDCOLOR, zeroline=True, zerolinecolor="#2b333d",
                       title=dict(text=f"PC2  ({evr[1]:.0%})", font=dict(size=10, color=DIM))),
        ),
    )
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def _draw_scores(res: fa.PCAResult) -> None:
    if res.scores.empty:
        st.info("PCA did not run — no data.")
        return
    fig = go.Figure()
    pcs = [c for c in ("PC1", "PC2", "PC3") if c in res.scores.columns]
    palette = {"PC1": "#6ea8fe", "PC2": "#e0a458", "PC3": "#bb9af7"}
    for pc in pcs:
        fig.add_trace(go.Scatter(
            x=res.scores.index, y=res.scores[pc],
            mode="lines",
            line=dict(color=palette[pc], width=1.4),
            name=pc,
            hovertemplate="%{x|%Y-%m-%d}<br>" + pc + ": %{y:.2f}<extra></extra>",
        ))
    fig.update_layout(
        **layout(
            height=320,
            showlegend=True,
            legend=dict(orientation="h", y=-0.18, font=dict(size=10, color=DIM)),
            xaxis=dict(gridcolor=GRIDCOLOR),
            yaxis=dict(gridcolor=GRIDCOLOR, zeroline=True, zerolinecolor="#2b333d",
                       title=dict(text="factor score", font=dict(size=10, color=DIM))),
        ),
    )
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def _draw_nmf_components(res: fa.NMFResult) -> None:
    if res.components.empty:
        st.info("NMF did not run — not enough symbols.")
        return
    H = res.components
    # Normalize each row to its own max so the visual contrast isn't dominated
    # by the loudest theme.
    row_max = H.max(axis=1).replace(0.0, 1.0)
    Hn = H.div(row_max, axis=0)
    fig = go.Figure(go.Heatmap(
        z=Hn.values,
        x=[c.replace("_rate", "").replace("_", " ").upper() for c in Hn.columns],
        y=list(Hn.index),
        colorscale=chrome.SEQUENTIAL_BLUE,
        zmin=0.0, zmax=1.0,
        colorbar=dict(thickness=8, tickfont=dict(size=9, color=DIM), len=0.85),
        hovertemplate="%{y} · %{x}: %{z:.2f}<extra></extra>",
    ))
    fig.update_layout(
        **layout(
            height=max(220, 60 * Hn.shape[0]),
            margin=dict(l=80, r=20, t=10, b=80),
            xaxis=dict(gridcolor=GRIDCOLOR, tickangle=-40, tickfont=dict(size=9, color=DIM)),
            yaxis=dict(gridcolor=GRIDCOLOR, autorange="reversed",
                       tickfont=dict(size=10, color=TEXT_HI)),
        ),
    )
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


# --------------------------------------------------------------------------- #
# summary builders for Ollama
# --------------------------------------------------------------------------- #
def _top_n(df: pd.DataFrame, col: str, *, n: int, asc: bool) -> list[dict]:
    s = df[col].sort_values(ascending=asc).head(n)
    return [{"symbol": k, "value": round(float(v), 3)} for k, v in s.items()]


def _score_summary(res: fa.PCAResult) -> dict:
    if res.scores.empty:
        return {}
    out: dict = {}
    for pc in ("PC1", "PC2", "PC3"):
        if pc not in res.scores.columns:
            continue
        s = res.scores[pc]
        out[pc] = {
            "min": round(float(s.min()), 2),
            "max": round(float(s.max()), 2),
            "argmax_date": str(s.idxmax().date()),
            "argmin_date": str(s.idxmin().date()),
        }
    return out


def _top_feature_per_theme(res: fa.NMFResult) -> dict:
    if res.components.empty:
        return {}
    out: dict[str, str] = {}
    for theme, row in res.components.iterrows():
        out[theme] = str(row.idxmax())
    return out
