"""Driver Correlation — cross-driver structure + the symbols the surviving
drivers actually touch.

Stacking order (full width):
  1. lookback selector (shared with Driver Detail via `driver_hours` state)
  2. METRIC toggle (φ / JACCARD) + MIN SYMBOLS slider + score-range slider
  3. heatmap (click any cell to inspect; hover for value)
  4. SYMBOLS COVERED — paginated table of stocks touched by the surviving drivers
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from signal_terminal import loader
from signal_terminal.config import Config
from signal_terminal.state import select_driver
from signal_terminal.style import (DIM, FAINT, FRESH, NEUTRAL, PLOTLY_CONFIG,
                                    POSITIVE, SENTIMENT_COLORSCALE, TEXT_HI,
                                    layout)
from signal_terminal.views._common import (apply_band, correlation_filter_controls,
                                            hint, window_label, window_selector)

# Same sentiment ramp as the treemap — anti-correlated drivers read NEG, co-
# moving drivers read POS, decoupled drivers sit at NEUTRAL gray.
CORR_COLORSCALE = SENTIMENT_COLORSCALE

# Jaccard is in [0, 1] — half the sentiment scale would mislead, so a sequential
# single-hue ramp from NEUTRAL (no overlap) to POSITIVE (total overlap).
JACCARD_COLORSCALE = [
    [0.0, NEUTRAL],
    [1.0, POSITIVE],
]

PAGE_SIZE = 10
DENSE_LABEL_THRESHOLD = 40
DENSE_HEIGHT = 720


# ---------- heatmap ----------
def _corr_heatmap(corr: pd.DataFrame, metric: str = "phi") -> go.Figure:
    n = max(len(corr.columns), 1)
    dense = n > DENSE_LABEL_THRESHOLD

    if metric == "jaccard":
        symbol = "J"
        colorscale = JACCARD_COLORSCALE
        z_format = ".2f"
        hm_kwargs = dict(zmin=0.0, zmax=1.0, colorscale=colorscale)
    else:
        symbol = "φ"
        colorscale = CORR_COLORSCALE
        z_format = "+.2f"
        hm_kwargs = dict(zmin=-1.0, zmax=1.0, zmid=0.0, colorscale=colorscale)

    fig = go.Figure(go.Heatmap(
        z=corr.values,
        x=list(corr.columns),
        y=list(corr.index),
        hovertemplate="<b>%{y}</b>  ↔  <b>%{x}</b><br>"
                       + symbol + "=%{z:" + z_format + "}<extra></extra>",
        xgap=1, ygap=1,
        colorbar=dict(
            title=dict(text=symbol, font=dict(family="JetBrains Mono", color=DIM)),
            tickfont=dict(family="JetBrains Mono", color=DIM, size=10),
            outlinewidth=0, thickness=10, len=0.7,
        ),
        **hm_kwargs,
    ))

    if dense:
        height = DENSE_HEIGHT
        left, bottom = 16, 24
        xaxis = dict(showticklabels=False, showgrid=False, side="bottom")
        yaxis = dict(showticklabels=False, showgrid=False, autorange="reversed")
    else:
        height = max(360, 28 * n + 80)
        left, bottom = 120, 120
        xaxis = dict(tickangle=-45,
                     tickfont=dict(family="JetBrains Mono", size=10, color=DIM),
                     showgrid=False, side="bottom")
        yaxis = dict(tickfont=dict(family="JetBrains Mono", size=10, color=DIM),
                     showgrid=False, autorange="reversed")

    fig.update_layout(**layout(
        height=height,
        margin=dict(l=left, r=20, t=12, b=bottom),
        xaxis=xaxis, yaxis=yaxis,
    ))
    return fig


def _extract_corr_click(event) -> tuple[str, str, float] | None:
    """Pull (row_driver, col_driver, score) from a plotly selection event."""
    if not event:
        return None
    sel = getattr(event, "selection", None) or (
        event.get("selection") if isinstance(event, dict) else None
    )
    if not sel:
        return None
    points = sel.get("points") if isinstance(sel, dict) else getattr(sel, "points", None)
    if not points:
        return None
    p = points[0]
    get = (lambda k: p.get(k)) if isinstance(p, dict) else (lambda k: getattr(p, k, None))
    x, y, z = get("x"), get("y"), get("z")
    if x is None or y is None:
        return None
    try:
        z_val = float(z) if z is not None else 0.0
    except (TypeError, ValueError):
        z_val = 0.0
    return (str(y), str(x), z_val)


def _corr_inspector(pair: tuple[str, str, float] | None, metric: str = "phi") -> None:
    symbol = "J" if metric == "jaccard" else "φ"
    if not pair:
        st.markdown(
            f"<div style='color:{FAINT}; font-size:10px; letter-spacing:1.5px; "
            f"margin-top:4px;'>"
            f"click any cell to inspect the pair  ·  hover for {symbol}"
            f"</div>",
            unsafe_allow_html=True,
        )
        return

    row, col, val = pair
    val_str = (f"{val:.2f}" if metric == "jaccard"
               else f"{'+' if val >= 0 else ''}{val:.2f}")
    cols = st.columns([5, 1, 1, 1])
    with cols[0]:
        st.markdown(
            f"<div style='padding-top:8px; color:{TEXT_HI}; letter-spacing:1.5px; "
            f"font-size:12px;'>"
            f"<span style='color:{DIM}'>SELECTED ·</span> "
            f"<b>{row}</b> &nbsp;↔&nbsp; <b>{col}</b> "
            f"<span style='color:{DIM}'>·</span> {symbol} = "
            f"<span style='color:{FRESH if abs(val) >= 0.5 else TEXT_HI}'>"
            f"{val_str}</span></div>",
            unsafe_allow_html=True,
        )
    with cols[1]:
        if st.button(f"FOCUS  {row[:14]}", key="corrtab_focus_row",
                     use_container_width=True):
            select_driver(row)
            st.session_state["driver_corr_cell"] = None
            st.session_state["active_tab_hint"] = "driver"
            st.rerun()
    with cols[2]:
        if st.button(f"FOCUS  {col[:14]}", key="corrtab_focus_col",
                     use_container_width=True,
                     disabled=(row == col)):
            select_driver(col)
            st.session_state["driver_corr_cell"] = None
            st.session_state["active_tab_hint"] = "driver"
            st.rerun()
    with cols[3]:
        if st.button("× CLEAR", key="corrtab_cell_clear", use_container_width=True):
            st.session_state["driver_corr_cell"] = None
            st.rerun()


# ---------- SYMBOLS COVERED table ----------
def _symbols_table(df: pd.DataFrame) -> None:
    total = len(df)
    page_count = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = int(st.session_state.get("corr_syms_page", 1))
    page = max(1, min(page, page_count))

    head = st.columns([1, 4, 1, 1])
    with head[0]:
        if st.button("◀ PREV", key="corr_syms_prev",
                     use_container_width=True, disabled=(page <= 1)):
            st.session_state["corr_syms_page"] = page - 1
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
        if st.button("NEXT ▶", key="corr_syms_next",
                     use_container_width=True, disabled=(page >= page_count)):
            st.session_state["corr_syms_page"] = page + 1
            st.rerun()

    start = (page - 1) * PAGE_SIZE
    slice_ = df.iloc[start:start + PAGE_SIZE].copy()
    slice_["·"] = slice_["fresh"].map(lambda v: "◆" if v else "")
    show = slice_[[
        "·", "symbol", "sector", "n_drivers", "top_drivers",
        "mean_weight", "mean_term_sentiment",
        "latest_sentiment", "latest_materiality", "latest_geo_risk",
        "latest_article_count", "hours_since_published",
    ]].rename(columns={
        "n_drivers":              "drivers",
        "mean_weight":            "avg_weight",
        "mean_term_sentiment":    "avg_drv_sent",
        "latest_sentiment":       "sentiment",
        "latest_materiality":     "materiality",
        "latest_geo_risk":        "geo_risk",
        "latest_article_count":   "articles",
        "hours_since_published":  "hrs_ago",
    })

    st.dataframe(
        show,
        hide_index=True,
        use_container_width=True,
        column_config={
            "·":            st.column_config.TextColumn("·", width="small", help="◆ = fresh (<1h)"),
            "symbol":       st.column_config.TextColumn("SYMBOL"),
            "sector":       st.column_config.TextColumn("SECTOR"),
            "drivers":      st.column_config.NumberColumn(
                "DRIVERS",
                help="# of surviving drivers (from the heatmap) carrying this symbol",
                format="%d",
            ),
            "top_drivers":  st.column_config.TextColumn(
                "TOP DRIVERS", help="top 3 surviving drivers on this symbol, by max weight",
            ),
            "avg_weight":   st.column_config.ProgressColumn(
                "AVG WEIGHT", help="average term weight across the surviving drivers",
                min_value=0.0, max_value=1.0, format="%.2f",
            ),
            "avg_drv_sent": st.column_config.NumberColumn(
                "AVG DRIVER SENT", help="mean term_sentiment across the surviving drivers",
                format="%+.2f",
            ),
            "sentiment":    st.column_config.NumberColumn(
                "SENTIMENT", help="symbol's latest overall sentiment", format="%+.2f",
            ),
            "materiality":  st.column_config.ProgressColumn(
                "MATERIALITY", min_value=0.0, max_value=1.0, format="%.2f",
            ),
            "geo_risk":     st.column_config.ProgressColumn(
                "GEO RISK", min_value=0.0, max_value=1.0, format="%.2f",
            ),
            "articles":     st.column_config.NumberColumn("ART", format="%d"),
            "hrs_ago":      st.column_config.NumberColumn("HRS AGO", format="%.1f"),
        },
    )


# ---------- view ----------
def _on_window_change(_new_hours: int) -> None:
    st.session_state["driver_corr_cell"] = None
    st.session_state["corr_syms_page"] = 1


def render(cfg: Config) -> None:
    hours = window_selector("corrtab", on_change=_on_window_change)
    hint("how far back in PAPIER's data to look. longer windows surface more "
         "drivers but include older news.")

    st.markdown(
        f"<div style='color:{DIM}; font-size:11px; letter-spacing:1.5px; "
        f"margin-bottom:8px;'>DRIVER CORRELATION · {window_label(hours)} WINDOW</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        f"<div class='panel-title' style='margin-top:6px'>"
        f"CORRELATION MATRIX</div>",
        unsafe_allow_html=True,
    )
    metric, min_symbols, low, high = correlation_filter_controls("corrtab")
    symbol = "J" if metric == "jaccard" else "φ"
    slider_min = 0.0 if metric == "jaccard" else -1.0
    slider_max = 1.0

    # Any control change → reset the clicked-cell selection and symbols page.
    state_key = (metric, min_symbols, low, high, hours)
    prev_state = st.session_state.get("_prev_corr_state")
    if prev_state is not None and prev_state != state_key:
        st.session_state["driver_corr_cell"] = None
        st.session_state["corr_syms_page"] = 1
    st.session_state["_prev_corr_state"] = state_key

    corr = loader.driver_correlation_matrix(
        cfg, hours=hours, limit=10_000,
        metric=metric, min_symbols=min_symbols,
    )
    full_n = len(corr.columns)
    if corr.empty or full_n < 2:
        st.markdown(
            f"<div class='panel' style='color:{FAINT}'>not enough drivers in this "
            f"window to compute correlations (try lowering MIN SYMBOLS or extending "
            f"the lookback).</div>",
            unsafe_allow_html=True,
        )
        return

    masked, hidden_drivers, hidden_cells = apply_band(corr, low, high)
    if masked.empty:
        band_str = (f"{symbol} ∈ [{low:+.2f}, {high:+.2f}]"
                    if metric == "phi" else
                    f"{symbol} ∈ [{low:.2f}, {high:.2f}]")
        st.markdown(
            f"<div class='panel' style='color:{FAINT}'>no driver pairs with "
            f"{band_str} in {window_label(hours)} — "
            f"{full_n} drivers, all dropped.</div>",
            unsafe_allow_html=True,
        )
        return

    n = len(masked.columns)
    dense = n > DENSE_LABEL_THRESHOLD
    event = st.plotly_chart(
        _corr_heatmap(masked, metric=metric),
        config=PLOTLY_CONFIG,
        use_container_width=True,
        on_select="rerun",
        selection_mode="points",
        key=f"corrtab_heatmap_{metric}",
    )
    clicked = _extract_corr_click(event)
    if clicked and st.session_state.get("driver_corr_cell") != clicked:
        st.session_state["driver_corr_cell"] = clicked
        st.rerun()

    _corr_inspector(st.session_state.get("driver_corr_cell"), metric=metric)

    density_note = (
        f"tick labels hidden for density — hover any cell for the pair + {symbol}"
        if dense else
        f"ranked by symbol-count desc — diagonal = self ({symbol}=1)"
    )
    band_active = (low, high) != (slider_min, slider_max)
    if band_active:
        band_str = (f"[{low:+.2f}, {high:+.2f}]" if metric == "phi"
                    else f"[{low:.2f}, {high:.2f}]")
        filter_note = (
            f" · band {symbol} ∈ {band_str} · "
            f"{hidden_drivers} drivers hidden, {hidden_cells:,} cells masked"
        )
    else:
        filter_note = ""
    metric_desc = (
        "Jaccard = |A∩B|/|A∪B|, symbol overlap"
        if metric == "jaccard" else
        "φ = phi coefficient over symbol presence"
    )
    min_syms_note = (f" · drivers filtered to ≥{min_symbols} symbols"
                      if min_symbols > 1 else "")
    st.markdown(
        f"<div style='color:{FAINT}; font-size:10px; letter-spacing:1.5px; "
        f"margin-top:-6px;'>{n} × {n} shown of {full_n} · {metric_desc} "
        f"(co-occurrence in {window_label(hours)}){min_syms_note}"
        f"{filter_note} · {density_note}</div>",
        unsafe_allow_html=True,
    )

    # --- SYMBOLS COVERED — the stocks touched by the surviving drivers ---
    surviving = list(masked.columns)
    st.markdown(
        "<div class='panel-title' style='margin-top:18px'>"
        "SYMBOLS COVERED BY THE FILTERED DRIVERS</div>",
        unsafe_allow_html=True,
    )
    hint("the stocks any surviving driver in the heatmap above is currently "
         "moving. tighten the filters (raise MIN SYMBOLS, narrow the range) "
         "and this list shrinks with the matrix.")

    sym_df = loader.symbols_carrying_drivers(
        cfg, hours=hours, canonical_terms=surviving,
    )
    if sym_df.empty:
        st.markdown(
            f"<div class='panel' style='color:{FAINT}'>no symbols carry any of the "
            f"{len(surviving)} surviving drivers — check the lookback / metric "
            f"choice.</div>",
            unsafe_allow_html=True,
        )
        return
    _symbols_table(sym_df)
