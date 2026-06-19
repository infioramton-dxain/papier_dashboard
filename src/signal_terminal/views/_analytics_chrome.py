"""Shared chrome for the Factors / Cohorts / Events tabs.

Every chart on these tabs follows the same pattern (spec §6):

  st.container(border=True):
    st.subheader(title)
    <chart>
    italic 'how to read this' block          (always shown)
    italic 'AI takeaway' block               (only when toggle on + Ollama up)
    cluster membership table + CSV download  (clustering charts only)

This module owns that pattern so each view can stay focused on data shaping.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd
import streamlit as st

from signal_terminal.analytics import descriptions, llm_interpret
from signal_terminal.analytics.data import Filters
from signal_terminal.config import Config
from signal_terminal.db import db_has_data
from signal_terminal.style import DIM, FAINT, NEGATIVE, NEUTRAL, POSITIVE, SURFACE_2, WARN

# --------------------------------------------------------------------------- #
# colorscales (anchored at 0 / [0,1] sequential)
# --------------------------------------------------------------------------- #
# Diverging — anchored at 0 in CALLER-NORMALIZED space [0,1].
# Use plotly's zmid=0 with these to anchor the white-equivalent at zero.
DIVERGING_RDBU = [
    [0.0, NEGATIVE],
    [0.5, NEUTRAL],
    [1.0, POSITIVE],
]

# Sequential — non-negative [0,1]. Surface-dark to defense-blue.
SEQUENTIAL_BLUE = [
    [0.0, SURFACE_2],
    [0.5, "#3d5a8a"],
    [1.0, "#6ea8fe"],
]


# --------------------------------------------------------------------------- #
# panel + description blocks
# --------------------------------------------------------------------------- #
def panel(
    chart_id: str,
    title: str,
    render: Callable[[], None],
    *,
    summary: dict[str, Any] | None = None,
    ai_enabled: bool = False,
) -> None:
    """Standard chart panel: title → chart → static description → optional AI takeaway.

    `render` is a zero-arg callable that draws the chart (so the panel can wrap
    it in the container). `summary` is the compact dict handed to Ollama if
    `ai_enabled` is True.
    """
    with st.container(border=True):
        st.subheader(title)
        render()
        _static_block(chart_id)
        if ai_enabled and summary is not None:
            _dynamic_block(chart_id, summary)


def static_description(chart_id: str) -> None:
    """Public wrapper around the static 'how to read' block.

    Use when the chart_id is a table or another non-Plotly artifact and you
    don't want the full panel() chrome — just the italic explainer line.
    """
    _static_block(chart_id)


def dynamic_description(chart_id: str, summary: dict[str, Any]) -> None:
    """Public wrapper around the dynamic AI takeaway block. Use alongside
    `static_description()` for non-Plotly artifacts (tables).
    """
    _dynamic_block(chart_id, summary)


def _static_block(chart_id: str) -> None:
    text = descriptions.get(chart_id)
    if not text:
        return
    st.markdown(
        f"<div style='color:{DIM}; font-size:11px; line-height:1.45; "
        f"font-style:italic; margin-top:8px;'>"
        f"<span style='color:{FAINT}; font-style:normal; letter-spacing:1px;'>"
        f"HOW TO READ — </span>{text}</div>",
        unsafe_allow_html=True,
    )


def _dynamic_block(chart_id: str, summary: dict[str, Any]) -> None:
    with st.spinner("Generating AI takeaway…"):
        text = llm_interpret.interpret(chart_id, summary, enabled=True)
    if not text:
        return
    label_color = FAINT if text == llm_interpret.UNAVAILABLE else "#6ea8fe"
    st.markdown(
        f"<div style='color:{DIM}; font-size:11px; line-height:1.45; "
        f"font-style:italic; margin-top:6px;'>"
        f"<span style='color:{label_color}; font-style:normal; letter-spacing:1px;'>"
        f"AI TAKEAWAY — </span>{text}</div>",
        unsafe_allow_html=True,
    )


def require_live_db(cfg: Config) -> bool:
    """Render the 'analytics tab needs a live DB' banner and return False
    when papier.db is absent. Returns True when the analytics tab body
    should proceed.

    Mirrors the spec rule that analytics never returns mock data — the live
    paths and mock paths are separate by design (mock is for the existing 6
    tabs only).
    """
    if db_has_data(cfg.db_path):
        return True
    st.markdown(
        f"<div style='color:{WARN}; font-size:12px; line-height:1.55; "
        f"padding:10px 12px; border:1px solid {WARN}; border-radius:4px;'>"
        f"<b>Analytics tabs require a live papier.db.</b><br>"
        f"Configure <code>paper.db</code> in <code>config.toml</code> and "
        f"point it at PAPIER's <code>data/papier.db</code>. The other six "
        f"tabs run on mock data when the DB is missing.</div>",
        unsafe_allow_html=True,
    )
    return False


def current_filters() -> Filters:
    """Read the sidebar filter widgets out of session_state into a Filters
    dataclass. Defaults are set by state.init() so this never raises KeyError.
    """
    return Filters(
        date_start=st.session_state.get("an_date_start"),
        date_end=st.session_state.get("an_date_end"),
        symbols=tuple(st.session_state.get("an_symbols") or ()) or None,
        sectors=tuple(st.session_state.get("an_sectors") or ()) or None,
        min_article_count=int(st.session_state.get("an_min_articles", 1)),
        grain=st.session_state.get("an_grain", "daily"),
        status=tuple(st.session_state.get("an_status") or ("ok",)),
    )


def ai_enabled() -> bool:
    return bool(st.session_state.get("an_ai_takeaways", True))


def membership_table(
    df: pd.DataFrame, *, key: str, filename: str, caption: str = ""
) -> None:
    """Render a cluster membership DataFrame + CSV download below the chart."""
    if df is None or df.empty:
        st.markdown(
            f"<div style='color:{FAINT}; font-size:11px; font-style:italic; "
            f"margin-top:6px;'>(no cluster membership at the current filters)</div>",
            unsafe_allow_html=True,
        )
        return
    if caption:
        st.markdown(
            f"<div style='color:{DIM}; font-size:10px; letter-spacing:1.5px; "
            f"margin:8px 0 -4px;'>{caption}</div>",
            unsafe_allow_html=True,
        )
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.download_button(
        label="DOWNLOAD CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=filename,
        mime="text/csv",
        key=f"dl_{key}",
        use_container_width=False,
    )
