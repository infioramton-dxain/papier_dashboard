"""Today's Pulse — landing screen.

Stacking order (all full width):
  1. event-flag counter row
  2. trending themes pills
  3. UNIVERSE HEATMAP (with encoding switcher)  -- the visualization
  4. DRIVERS panel for currently selected symbol  -- why the click matters
  5. MOVERS row (|sentiment| + Δ24h side by side, together full-width)
  6. QA strip
"""
import streamlit as st

from signal_terminal import loader, state
from signal_terminal.components import (event_flag_row, heatmap, movers, qa_strip,
                                         symbol_drivers_panel, theme_pills)
from signal_terminal.config import Config
from signal_terminal.style import DIM


def render(cfg: Config) -> None:
    df_uni = loader.universe_latest(cfg)
    flag_df = loader.universe_event_flag_counts(cfg)
    qa = loader.universe_qa(cfg)
    themes = loader.trending_themes(cfg)

    n_syms = df_uni["symbol"].nunique() if not df_uni.empty else 0
    st.markdown(
        f"<div style='color:{DIM}; font-size:11px; letter-spacing:1.5px; "
        f"margin-bottom:8px;'>UNIVERSE · {n_syms} SYMBOLS · 24H WINDOW</div>",
        unsafe_allow_html=True,
    )

    # 1. event-flag counter row (full width)
    event_flag_row.render(flag_df)

    # 2. trending themes pills (full width)
    theme_pills.render(themes, active_theme=st.session_state.get("theme_filter"))

    # 3. UNIVERSE HEATMAP — full width
    st.markdown("<div class='panel-title' style='margin-top:10px'>UNIVERSE HEATMAP</div>",
                unsafe_allow_html=True)
    toggle_cols = st.columns([1, 1, 1, 6])
    with toggle_cols[0]:
        if st.button("TREEMAP",
                     type="primary" if st.session_state["mode"] == "treemap" else "secondary",
                     use_container_width=True):
            st.session_state["mode"] = "treemap"; st.rerun()
    with toggle_cols[1]:
        if st.button("DENSE GRID",
                     type="primary" if st.session_state["mode"] == "grid" else "secondary",
                     use_container_width=True):
            st.session_state["mode"] = "grid"; st.rerun()
    with toggle_cols[2]:
        if st.button("SECTOR GROUP",
                     type="primary" if st.session_state["mode"] == "sector" else "secondary",
                     use_container_width=True):
            st.session_state["mode"] = "sector"; st.rerun()

    # apply theme filter to universe if set
    filtered = df_uni
    active_theme = st.session_state.get("theme_filter")
    if active_theme and not df_uni.empty:
        peers = loader.symbols_for_theme(cfg, active_theme)
        filtered = df_uni[df_uni["symbol"].isin(peers)]

    heatmap.render(filtered, mode=st.session_state["mode"])

    # 4. DRIVERS — full width, directly below the visualization
    sel = st.session_state.get("selected_symbol")
    if sel and not df_uni.empty and sel in df_uni["symbol"].values:
        latest = df_uni.loc[df_uni["symbol"] == sel].iloc[0]
        drivers = loader.symbol_drivers(cfg, sel, latest["window_start"])
        symbol_drivers_panel.render(sel, drivers, latest["window_start"])
    else:
        symbol_drivers_panel.render_placeholder()

    # 5. MOVERS — full width row, two bordered panels side-by-side
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    mover_cols = st.columns(2, gap="medium")
    with mover_cols[0]:
        with st.container(border=True):
            movers.render_abs(loader.universe_movers_by_abs(cfg))
    with mover_cols[1]:
        with st.container(border=True):
            movers.render_delta(loader.universe_movers_by_delta(cfg))

    # 6. QA — full width at the bottom
    st.markdown("<div class='panel-title' style='margin-top:8px'>QA — 24H</div>",
                unsafe_allow_html=True)
    qa_strip.render(qa)
