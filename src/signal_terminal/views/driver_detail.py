"""Driver Detail — pick a driver (canonical_term), explore who it's moving.

Stacking order (full width):
  1. lookback selector (shared with Driver Correlation via `driver_hours` state)
  2. driver picker — paginated pill row over trending themes
  3. treemap of affected symbols (area = relevance weight, color = sentiment)
  4. paginated symbol table (10/page) with relevance + context measures

The cross-driver correlation heatmap + symbols-covered table live on the
DRIVER CORRELATION tab.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from signal_terminal import loader
from signal_terminal.config import Config
from signal_terminal.state import select_driver
from signal_terminal.style import (DIM, FAINT, FRESH, PLOTLY_CONFIG, SURFACE,
                                    TEXT_HI, layout, sentiment_color)
from signal_terminal.views._common import hint, window_label, window_selector

PAGE_SIZE = 10
PILLS_PER_PAGE = 12


# ---------- driver picker ----------
def _pill_label(row: dict) -> str:
    dot = "●" if abs(row["mean_term_sentiment"]) > 0.1 else "·"
    badge = f"  ◆{int(row['fresh_count'])}" if row.get("fresh_count") else ""
    return f"{dot}  {row['canonical_term']}  ·{int(row['n_symbols'])}{badge}"


def _driver_picker(themes: pd.DataFrame, active: str | None) -> None:
    if themes.empty:
        st.markdown(
            f"<div class='panel' style='color:{FAINT}'>no drivers — PAPIER hasn't "
            "surfaced any terms in this window.</div>",
            unsafe_allow_html=True,
        )
        return

    total = len(themes)
    page_count = max(1, (total + PILLS_PER_PAGE - 1) // PILLS_PER_PAGE)
    page = int(st.session_state.get("driver_pill_page", 1))
    page = max(1, min(page, page_count))

    header_cols = st.columns([3, 1, 2, 1, 1])
    with header_cols[0]:
        active_html = (
            f"<span style='color:{FRESH}'>active: {active}</span>"
            if active else f"<span style='color:{FAINT}'>pick a driver to drill in</span>"
        )
        st.markdown(
            f"<div class='panel-title'>DRIVERS — {active_html}</div>",
            unsafe_allow_html=True,
        )
    with header_cols[1]:
        if st.button("◀ PREV", key="driver_pill_prev",
                     use_container_width=True, disabled=(page <= 1)):
            st.session_state["driver_pill_page"] = page - 1
            st.rerun()
    with header_cols[2]:
        st.markdown(
            f"<div style='text-align:center; color:{DIM}; padding-top:10px; "
            f"letter-spacing:1.5px; font-size:11px;'>"
            f"PAGE {page} / {page_count}  ·  {total} DRIVERS"
            f"</div>",
            unsafe_allow_html=True,
        )
    with header_cols[3]:
        if st.button("NEXT ▶", key="driver_pill_next",
                     use_container_width=True, disabled=(page >= page_count)):
            st.session_state["driver_pill_page"] = page + 1
            st.rerun()
    with header_cols[4]:
        if active and st.button("× CLEAR", key="driver_clear_btn",
                                 use_container_width=True):
            select_driver(None)
            st.rerun()

    start = (page - 1) * PILLS_PER_PAGE
    rows = themes.iloc[start:start + PILLS_PER_PAGE].to_dict("records")
    for chunk_start in (0, 6):
        chunk = rows[chunk_start:chunk_start + 6]
        if not chunk:
            continue
        cols = st.columns(6)
        for i in range(6):
            with cols[i]:
                if i >= len(chunk):
                    st.markdown("&nbsp;", unsafe_allow_html=True)
                    continue
                row = chunk[i]
                is_on = (active == row["canonical_term"])
                if st.button(
                    _pill_label(row),
                    key=f"driver_pill_{row['canonical_term']}_{start + chunk_start + i}",
                    use_container_width=True,
                    type=("primary" if is_on else "secondary"),
                ):
                    select_driver(row["canonical_term"])
                    st.rerun()


# ---------- treemap ----------
def _treemap(df: pd.DataFrame, driver: str) -> go.Figure:
    """area = driver weight (relevance), color = symbol's latest sentiment."""
    if df.empty:
        fig = go.Figure()
        fig.update_layout(**layout(height=380))
        return fig

    df = df.copy()
    df["area"] = df["weight"].fillna(0.0) + 0.04

    sectors = list(df["sector"].fillna("Other").unique())
    labels = list(df["symbol"]) + sectors
    parents = list(df["sector"].fillna("Other")) + ["" for _ in sectors]
    values = (
        df["area"].tolist()
        + [df.loc[df["sector"].fillna("Other") == s, "area"].sum() for s in sectors]
    )
    colors = (
        [sentiment_color(v) for v in df["latest_sentiment"].tolist()]
        + [SURFACE for _ in sectors]
    )

    hover = (
        "<b>%{label}</b><br>"
        "weight=%{customdata[0]:.2f}<br>"
        "term_sent=%{customdata[1]:+.2f}<br>"
        "sentiment=%{customdata[2]:+.2f}<extra></extra>"
    )
    custom = df[["weight", "term_sentiment", "latest_sentiment"]].values.tolist()
    custom += [[0, 0, 0] for _ in sectors]

    fig = go.Figure(go.Treemap(
        labels=labels, parents=parents, values=values, branchvalues="total",
        marker=dict(colors=colors, line=dict(color="#0a0e13", width=1)),
        customdata=custom,
        hovertemplate=hover,
        textfont=dict(family="JetBrains Mono", size=10, color=TEXT_HI),
        textinfo="label",
    ))
    fig.update_layout(**layout(
        height=380,
        margin=dict(l=2, r=2, t=24, b=2),
    ))
    fig.add_annotation(
        x=0, y=1.04, xref="paper", yref="paper",
        text=f"<b>{driver.upper()}</b>  ·  {len(df)} SYMBOLS  ·  AREA = WEIGHT, COLOR = SENTIMENT",
        showarrow=False, xanchor="left",
        font=dict(family="JetBrains Mono", size=10, color=DIM),
    )
    return fig


# ---------- paginated table ----------
def _table(df: pd.DataFrame) -> None:
    total = len(df)
    page_count = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = int(st.session_state.get("driver_page", 1))
    page = max(1, min(page, page_count))

    head = st.columns([1, 4, 1, 1])
    with head[0]:
        if st.button("◀ PREV", key="driver_page_prev",
                     use_container_width=True, disabled=(page <= 1)):
            st.session_state["driver_page"] = page - 1
            st.rerun()
    with head[1]:
        st.markdown(
            f"<div style='text-align:center; color:{DIM}; padding-top:6px; "
            f"letter-spacing:1.5px; font-size:11px;'>"
            f"PAGE {page} / {page_count}  ·  {total} SYMBOLS"
            f"</div>",
            unsafe_allow_html=True,
        )
    with head[3]:
        if st.button("NEXT ▶", key="driver_page_next",
                     use_container_width=True, disabled=(page >= page_count)):
            st.session_state["driver_page"] = page + 1
            st.rerun()

    start = (page - 1) * PAGE_SIZE
    slice_ = df.iloc[start:start + PAGE_SIZE].copy()
    slice_["·"] = slice_["fresh"].map(lambda v: "◆" if v else "")
    show = slice_[[
        "·", "symbol", "sector",
        "weight", "term_sentiment", "n_windows_with_term",
        "latest_sentiment", "latest_materiality", "latest_geo_risk",
        "latest_article_count", "hours_since_published",
    ]].rename(columns={
        "weight":                "relevance",
        "term_sentiment":        "driver_sent",
        "n_windows_with_term":   "windows",
        "latest_sentiment":      "sentiment",
        "latest_materiality":    "materiality",
        "latest_geo_risk":       "geo_risk",
        "latest_article_count":  "articles",
        "hours_since_published": "hrs_ago",
    })

    st.dataframe(
        show,
        hide_index=True,
        use_container_width=True,
        column_config={
            "·": st.column_config.TextColumn("·", width="small", help="◆ = fresh (<1h)"),
            "symbol":      st.column_config.TextColumn("SYMBOL"),
            "sector":      st.column_config.TextColumn("SECTOR"),
            "relevance":   st.column_config.ProgressColumn(
                "RELEVANCE", help="max term weight in window (0..1)",
                min_value=0.0, max_value=1.0, format="%.2f",
            ),
            "driver_sent": st.column_config.NumberColumn(
                "DRIVER SENT", help="mean term_sentiment for this driver (-1..1)",
                format="%+.2f",
            ),
            "windows":     st.column_config.NumberColumn("WIN", format="%d"),
            "sentiment":   st.column_config.NumberColumn(
                "SENTIMENT", help="symbol's latest overall sentiment", format="%+.2f",
            ),
            "materiality": st.column_config.ProgressColumn(
                "MATERIALITY", min_value=0.0, max_value=1.0, format="%.2f",
            ),
            "geo_risk":    st.column_config.ProgressColumn(
                "GEO RISK", min_value=0.0, max_value=1.0, format="%.2f",
            ),
            "articles":    st.column_config.NumberColumn("ART", format="%d"),
            "hrs_ago":     st.column_config.NumberColumn("HRS AGO", format="%.1f"),
        },
    )


# ---------- view ----------
def _on_window_change(_new_hours: int) -> None:
    st.session_state["selected_driver"] = None
    st.session_state["driver_page"] = 1
    st.session_state["driver_pill_page"] = 1


def render(cfg: Config) -> None:
    hours = window_selector("driver", on_change=_on_window_change)
    hint("how far back in PAPIER's data to look. longer windows surface more "
         "drivers but include older news.")
    themes = loader.trending_themes(cfg, hours=hours, limit=2000)
    active = st.session_state.get("selected_driver")

    n_drivers = len(themes)
    st.markdown(
        f"<div style='color:{DIM}; font-size:11px; letter-spacing:1.5px; "
        f"margin-bottom:8px;'>DRIVER DETAIL · {n_drivers} TRENDING IN {window_label(hours)} WINDOW</div>",
        unsafe_allow_html=True,
    )

    # 1. driver picker
    _driver_picker(themes, active)

    # 2 + 3. affected symbols
    if not active:
        st.markdown(
            f"<div class='panel' style='color:{FAINT}; margin-top:8px;'>"
            f"select a driver above to see the symbols it's moving."
            f"</div>",
            unsafe_allow_html=True,
        )
        return

    symbols_df = loader.driver_symbols(cfg, active, hours=hours)
    st.markdown(
        "<div class='panel-title' style='margin-top:10px'>AFFECTED SYMBOLS</div>",
        unsafe_allow_html=True,
    )
    if symbols_df.empty:
        st.markdown(
            f"<div class='panel' style='color:{FAINT}'>no symbols carry "
            f"<b>{active}</b> in the last {window_label(hours)}.</div>",
            unsafe_allow_html=True,
        )
        return

    symbols_df = symbols_df.sort_values("weight", ascending=False).reset_index(drop=True)
    st.plotly_chart(
        _treemap(symbols_df, active),
        config=PLOTLY_CONFIG,
        use_container_width=True,
        key="driver_treemap",
    )
    _table(symbols_df)
