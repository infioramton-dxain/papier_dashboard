"""Streamlit session_state initialization & helpers.

Mirrors the prototype's state model exactly — see the handoff README § State Management.
"""
import streamlit as st


DEFAULTS = {
    "active_tab":      "pulse",      # pulse | symbol | sector | pipeline
    "mode":            "treemap",    # treemap | grid | sector
    "sec_metric":      "sentiment",  # sentiment | materiality | geo_risk
    "selected_symbol": None,
    "theme_filter":    None,
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
