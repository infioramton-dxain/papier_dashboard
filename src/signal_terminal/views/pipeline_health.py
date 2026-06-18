"""Pipeline Health — stub (full build tomorrow)."""
import streamlit as st

from signal_terminal import loader
from signal_terminal.config import Config
from signal_terminal.style import DIM, NEGATIVE, POSITIVE, TEXT_HI, WARN


def render(cfg: Config) -> None:
    qa = loader.universe_qa(cfg)
    runs = loader.pipeline_runs(cfg)
    succ_total = len(runs) if not runs.empty else 0
    succ_ok = (runs["status"] == "ok").sum() if not runs.empty else 0
    succ_pct = (succ_ok / succ_total * 100) if succ_total else 0
    succ_color = POSITIVE if succ_pct >= 95 else (WARN if succ_pct >= 80 else NEGATIVE)

    cards = [
        ("MALFORMED_JSON · 24H", qa["malformed_json"], NEGATIVE if qa["malformed_json"] else TEXT_HI),
        ("TRUNCATED · 24H",      qa["truncated"], WARN if qa["truncated"] else TEXT_HI),
        ("DROPPED ARTICLES · 24H", qa["dropped_articles"], TEXT_HI),
        ("RUN SUCCESS RATE",     f"{succ_pct:.0f}%", succ_color),
    ]
    cols = st.columns(len(cards))
    for col, (label, val, color) in zip(cols, cards):
        with col:
            st.markdown(
                f"""
                <div class="panel" style="padding:14px 16px;">
                  <div style="color:{DIM}; font-size:10px; letter-spacing:1.5px; font-weight:600;">{label}</div>
                  <div class='num' style='color:{color}; font-size:27px; font-weight:700; line-height:1.05;'>{val}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("<div class='panel-title' style='margin-top:14px'>RUN HISTORY (most recent)</div>", unsafe_allow_html=True)
    if runs.empty:
        st.markdown(f"<div style='color:{DIM}'>no runs recorded</div>", unsafe_allow_html=True)
        return
    show = runs[["run_id", "command", "started_at", "ended_at", "duration_min",
                 "rows_written", "errors", "status"]].copy()
    st.dataframe(show, use_container_width=True, hide_index=True)
