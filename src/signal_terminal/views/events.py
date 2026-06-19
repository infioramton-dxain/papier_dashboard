"""EVENTS — what event patterns travel together, and where do they fire?

Three descriptive charts (no clustering on this tab — cohort discovery
happens on the Cohorts tab):
  3.1 7×7 flag co-occurrence heatmap (diagonal = counts, off-diagonal = min-Jaccard)
  3.2 monthly stacked-area firing rates
  3.3 per-symbol firing-rate heatmap + sortable table (3.3.t)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from signal_terminal.analytics import data as andata
from signal_terminal.analytics import events as ev
from signal_terminal.config import Config
from signal_terminal.sectors import sector_of
from signal_terminal.style import (DIM, EVENT_LABEL, FAINT, GRIDCOLOR,
                                    PLOTLY_CONFIG, TEXT_HI, layout)
from signal_terminal.views import _analytics_chrome as chrome

# Distinct flag colors — categorical, never implies value.
FLAG_COLOR = {
    "contract_award":    "#6ea8fe",
    "guidance":          "#7ec9c9",
    "mna":               "#bb9af7",
    "regulatory_export": "#d29922",
    "litigation":        "#e5484d",
    "analyst_action":    "#e0a458",
    "commodity_move":    "#30a46c",
}


# --------------------------------------------------------------------------- #
# cached compute
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=3600, show_spinner=False)
def _df(db_path_str: str, filters: andata.Filters) -> pd.DataFrame:
    return andata.load_sentiment(db_path_str, filters)


@st.cache_data(ttl=3600, show_spinner=False)
def _cooc(db_path_str: str, filters: andata.Filters) -> pd.DataFrame:
    return ev.flag_cooccurrence(_df(db_path_str, filters))


@st.cache_data(ttl=3600, show_spinner=False)
def _over_time(db_path_str: str, filters: andata.Filters, freq: str) -> pd.DataFrame:
    return ev.firing_rates_over_time(_df(db_path_str, filters), freq=freq)


@st.cache_data(ttl=3600, show_spinner=False)
def _per_symbol(db_path_str: str, filters: andata.Filters) -> pd.DataFrame:
    return ev.firing_rates_per_symbol(_df(db_path_str, filters))


# --------------------------------------------------------------------------- #
# entrypoint
# --------------------------------------------------------------------------- #
def render(cfg: Config) -> None:
    if not chrome.require_live_db(cfg):
        return
    st.header("What event patterns travel together, and where do they fire?")
    st.markdown(
        f"<div style='color:{DIM}; font-size:12px; line-height:1.55; margin-top:-6px; "
        f"margin-bottom:14px;'>Descriptive view of the seven event flags — "
        f"co-occurrence between flags, monthly firing share over time, and "
        f"per-symbol firing rates. No clustering on this tab; cohort discovery "
        f"lives on the Cohorts tab.</div>",
        unsafe_allow_html=True,
    )

    filters = chrome.current_filters()
    ai_on = chrome.ai_enabled()
    db_str = str(cfg.db_path)

    df = _df(db_str, filters)
    if df.empty:
        st.warning("No event-flag rows at current filters.")
        return

    # ---------------------------- 3.1 cooc heatmap ---------------------------
    cooc = _cooc(db_str, filters)
    chrome.panel(
        "flag_cooccurrence", "3.1 · Flag co-occurrence — diagonal = count, off-diagonal = min-Jaccard",
        lambda: _draw_cooc(cooc),
        summary=_cooc_summary(cooc),
        ai_enabled=ai_on,
    )

    # ---------------------------- 3.2 over time -----------------------------
    over_time = _over_time(db_str, filters, "ME")
    chrome.panel(
        "flag_over_time", "3.2 · Monthly firing rate — stacked share",
        lambda: _draw_over_time(over_time),
        summary=_over_time_summary(over_time),
        ai_enabled=ai_on,
    )

    # ---------------------------- 3.3 per symbol + 3.3.t --------------------
    per_sym = _per_symbol(db_str, filters)
    with st.container(border=True):
        st.subheader("3.3 · Per-symbol flag firing rates")
        _draw_per_symbol(per_sym)
        chrome.static_description("flag_per_symbol")
        if ai_on:
            chrome.dynamic_description("flag_per_symbol", _per_symbol_summary(per_sym))

        # 3.3.t — the sortable table.
        if not per_sym.empty:
            tbl = per_sym.copy()
            tbl.insert(1, "sector", tbl["symbol"].map(sector_of))
            rate_cols = [c for c in tbl.columns if c.endswith("_rate")]
            for c in rate_cols:
                tbl[c] = tbl[c].round(3)
            st.markdown(
                f"<div style='color:{DIM}; font-size:10px; letter-spacing:1.5px; "
                f"margin:8px 0 -4px;'>3.3.t · PER-SYMBOL FIRING RATE TABLE</div>",
                unsafe_allow_html=True,
            )
            st.dataframe(tbl, hide_index=True, use_container_width=True)
            st.download_button(
                "DOWNLOAD CSV",
                data=tbl.to_csv(index=False).encode("utf-8"),
                file_name="events_per_symbol.csv",
                mime="text/csv",
                key="dl_events_per_symbol",
            )


# --------------------------------------------------------------------------- #
# drawers
# --------------------------------------------------------------------------- #
def _draw_cooc(cooc: pd.DataFrame) -> None:
    if cooc.empty or cooc.values.sum() == 0:
        st.info("No event-flag co-occurrences at current filters.")
        return
    labels = [EVENT_LABEL.get(c, c) for c in cooc.columns]
    arr = cooc.values.copy().astype(float)
    # Build a render array where the diagonal is normalized to [0,1] for color
    # but hover shows the raw count. Off-diagonals are already in [0,1].
    diag = np.diag(arr).copy()
    max_diag = float(diag.max()) if diag.size and diag.max() > 0 else 1.0
    z = arr.copy()
    np.fill_diagonal(z, diag / max_diag)
    # custom hover text — show raw values
    text = np.empty(arr.shape, dtype=object)
    n = arr.shape[0]
    for i in range(n):
        for j in range(n):
            text[i, j] = f"{int(arr[i, j])} fires" if i == j else f"{arr[i, j]:.2f}"
    fig = go.Figure(go.Heatmap(
        z=z,
        x=labels, y=labels,
        text=text,
        colorscale=chrome.SEQUENTIAL_BLUE,
        zmin=0.0, zmax=1.0,
        colorbar=dict(thickness=8, tickfont=dict(size=9, color=DIM), len=0.85),
        hovertemplate="%{y} × %{x}<br>%{text}<extra></extra>",
    ))
    fig.update_layout(
        **layout(
            height=420,
            margin=dict(l=110, r=20, t=10, b=80),
            xaxis=dict(gridcolor=GRIDCOLOR, tickangle=-40, tickfont=dict(size=9, color=DIM)),
            yaxis=dict(gridcolor=GRIDCOLOR, autorange="reversed",
                       tickfont=dict(size=10, color=TEXT_HI)),
        ),
    )
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def _draw_over_time(over: pd.DataFrame) -> None:
    if over.empty:
        st.info("No firing-rate history at current filters.")
        return
    fig = go.Figure()
    for col in over.columns:
        fig.add_trace(go.Scatter(
            x=over.index, y=over[col], stackgroup="one", mode="lines",
            line=dict(width=0.5, color=FLAG_COLOR.get(col, "#6ea8fe")),
            name=EVENT_LABEL.get(col, col),
            hovertemplate="%{x|%Y-%m}<br>" + EVENT_LABEL.get(col, col) + ": %{y:.1%}<extra></extra>",
        ))
    fig.update_layout(
        **layout(
            height=320,
            showlegend=True,
            legend=dict(orientation="h", y=-0.18, font=dict(size=10, color=DIM)),
            xaxis=dict(gridcolor=GRIDCOLOR),
            yaxis=dict(gridcolor=GRIDCOLOR, tickformat=".0%",
                       title=dict(text="firing share", font=dict(size=10, color=DIM))),
        ),
    )
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def _draw_per_symbol(per_sym: pd.DataFrame) -> None:
    if per_sym.empty:
        st.info("No per-symbol firing rates at current filters.")
        return
    rate_cols = [c for c in per_sym.columns if c.endswith("_rate")]
    if not rate_cols:
        st.info("No flag columns in the filtered data.")
        return
    M = per_sym.set_index("symbol")[rate_cols].fillna(0.0)
    # Sort symbols by total firing rate so the heatmap reads top-to-bottom.
    M = M.loc[M.sum(axis=1).sort_values(ascending=False).index]
    labels = [EVENT_LABEL.get(c.replace("_rate", ""), c) for c in rate_cols]
    fig = go.Figure(go.Heatmap(
        z=M.values,
        x=labels, y=list(M.index),
        colorscale=chrome.SEQUENTIAL_BLUE,
        zmin=0.0, zmax=float(M.values.max() or 1.0),
        colorbar=dict(thickness=8, tickfont=dict(size=9, color=DIM), len=0.85),
        hovertemplate="%{y} · %{x}: %{z:.1%}<extra></extra>",
    ))
    n_sym = M.shape[0]
    fig.update_layout(
        **layout(
            height=min(900, max(360, int(15 * n_sym))),
            margin=dict(l=80, r=20, t=10, b=80),
            xaxis=dict(gridcolor=GRIDCOLOR, tickangle=-40, tickfont=dict(size=9, color=DIM)),
            yaxis=dict(gridcolor=GRIDCOLOR, autorange="reversed",
                       showticklabels=n_sym <= 80,
                       tickfont=dict(size=8, color=TEXT_HI)),
        ),
    )
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
    if n_sym > 80:
        st.markdown(
            f"<div style='color:{FAINT}; font-size:10px; letter-spacing:1px; "
            f"margin-top:-2px;'>Y-axis labels hidden — too many symbols. Use the "
            f"table below to look up specific tickers.</div>",
            unsafe_allow_html=True,
        )


# --------------------------------------------------------------------------- #
# summaries (for Ollama)
# --------------------------------------------------------------------------- #
def _cooc_summary(cooc: pd.DataFrame) -> dict:
    if cooc.empty or cooc.values.sum() == 0:
        return {}
    arr = cooc.values
    n = arr.shape[0]
    diag = {cooc.columns[i]: int(arr[i, i]) for i in range(n)}
    pairs: list[tuple[str, str, float]] = []
    for i in range(n):
        for j in range(i + 1, n):
            pairs.append((cooc.columns[i], cooc.columns[j], float(arr[i, j])))
    pairs.sort(key=lambda x: x[2], reverse=True)
    top_pairs = [{"a": a, "b": b, "score": round(s, 3)} for a, b, s in pairs[:5]]
    return {"firing_counts": diag, "top_cooccurring_pairs": top_pairs}


def _over_time_summary(over: pd.DataFrame) -> dict:
    if over.empty:
        return {}
    return {
        "n_periods": int(over.shape[0]),
        "peak_period_per_flag": {
            str(c): str(over[c].idxmax().date())
            for c in over.columns
            if over[c].notna().any() and over[c].max() > 0
        },
    }


def _per_symbol_summary(per_sym: pd.DataFrame) -> dict:
    if per_sym.empty:
        return {}
    rate_cols = [c for c in per_sym.columns if c.endswith("_rate")]
    if not rate_cols:
        return {}
    out = {}
    for c in rate_cols:
        top = per_sym.sort_values(c, ascending=False).head(3)
        flag = c.replace("_rate", "")
        out[flag] = [
            {"symbol": r["symbol"], "rate": round(float(r[c]), 3)}
            for _, r in top.iterrows()
        ]
    return {"top_symbols_per_flag": out}
