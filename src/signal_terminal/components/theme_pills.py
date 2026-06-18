"""Trending themes — horizontal pill strip. Click to filter Pulse by theme."""
import pandas as pd
import streamlit as st

from signal_terminal.state import clear_theme, filter_theme
from signal_terminal.style import FRESH, NEGATIVE, POSITIVE


def _dot(v: float) -> str:
    if v > 0.1:
        return "●"
    if v < -0.1:
        return "●"
    return "·"


def _label(p: dict) -> str:
    """Compact pill label: sentiment glyph + term + symbol count [+ fresh badge]."""
    dot = _dot(p["mean_term_sentiment"])
    badge = f"  ◆{int(p['fresh_count'])}" if p["fresh_count"] else ""
    return f"{dot}  {p['canonical_term']}  ·{int(p['n_symbols'])}{badge}"


def _row(pills: list[dict], active_theme: str | None, offset: int) -> None:
    if not pills:
        return
    cols = st.columns(len(pills))
    for i, p in enumerate(pills):
        with cols[i]:
            is_active = (active_theme == p["canonical_term"])
            if st.button(
                _label(p),
                key=f"pill_{p['canonical_term']}_{offset + i}",
                use_container_width=True,
                type=("primary" if is_active else "secondary"),
            ):
                filter_theme(p["canonical_term"])
                st.rerun()


def render(df: pd.DataFrame, active_theme: str | None = None) -> None:
    """df columns: canonical_term, n_symbols, n_windows, mean_term_sentiment,
                   mean_weight, fresh_count, influence
    """
    if df.empty:
        st.markdown(
            "<div class='panel' style='padding:8px 14px; color:#6e7681'>no trending themes — "
            "PAPIER hasn't surfaced any terms in the last 24h yet</div>",
            unsafe_allow_html=True,
        )
        return

    if active_theme:
        col_a, col_b = st.columns([6, 1])
        with col_a:
            st.markdown(
                f"<div class='panel-title'>TRENDING THEMES — "
                f"<span style='color:{FRESH}'>active: {active_theme}</span></div>",
                unsafe_allow_html=True,
            )
        with col_b:
            if st.button("× CLEAR FILTER", key="clear_theme_btn"):
                clear_theme()
                st.rerun()
    else:
        st.markdown("<div class='panel-title'>TRENDING THEMES</div>", unsafe_allow_html=True)

    pills = df.head(12).to_dict("records")
    _row(pills[:6], active_theme, offset=0)
    _row(pills[6:12], active_theme, offset=6)
