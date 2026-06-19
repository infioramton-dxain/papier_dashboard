"""Streamlit session_state initialization & helpers.

Mirrors the prototype's state model exactly — see the handoff README § State Management.
"""
import streamlit as st


DEFAULTS = {
    "active_tab":      "pulse",      # pulse | symbol | sector | pipeline | driver
    "mode":            "treemap",    # treemap | grid | sector
    "sec_metric":      "sentiment",  # sentiment | materiality | geo_risk
    "selected_symbol": None,
    "theme_filter":    None,
    "selected_driver": None,         # canonical_term focused in Driver Detail
    "driver_page":     1,            # 1-indexed page for the affected-symbols table
    "driver_pill_page":1,            # 1-indexed page for the pill strip
    "driver_hours":    168,          # lookback (in hours) for Driver Detail. 168 = 7d
    "driver_corr_cell": None,        # (row_term, col_term, phi) of last clicked corr cell
    "corr_band":       (-1.0, 1.0),  # (low, high) shown in correlation heatmap (metric-relative)
    "corr_metric":     "phi",        # "phi" (Pearson on binary) or "jaccard" (|A∩B|/|A∪B|)
    "corr_min_symbols": 1,           # drop drivers appearing on fewer than this many symbols
    "corr_syms_page":  1,            # 1-indexed page for the SYMBOLS COVERED table
}


def init() -> None:
    """Idempotent — call once at the top of app.py before any view runs."""
    for k, v in DEFAULTS.items():
        st.session_state.setdefault(k, v)


def go_symbol(symbol: str) -> None:
    """Cross-filter: jump to Symbol Detail for a ticker."""
    st.session_state["selected_symbol"] = symbol
    st.session_state["active_tab"] = "symbol"


def filter_theme(canonical_term: str | None) -> None:
    """Cross-filter: set/clear theme filter and return to Today's Pulse."""
    st.session_state["theme_filter"] = canonical_term
    st.session_state["active_tab"] = "pulse"


def clear_theme() -> None:
    st.session_state["theme_filter"] = None


def select_driver(canonical_term: str | None) -> None:
    """Driver Detail focus. Resets pagination so a fresh driver always lands on page 1."""
    st.session_state["selected_driver"] = canonical_term
    st.session_state["driver_page"] = 1
