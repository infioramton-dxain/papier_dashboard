"""QA strip — 3 metrics, malformed (red>0) / truncated (amber>0) / dropped."""
import streamlit as st

from signal_terminal.style import DIM, NEGATIVE, TEXT_HI, WARN


def render(qa: dict) -> None:
    cols = st.columns(3)
    cells = [
        ("MALFORMED_JSON", qa.get("malformed_json", 0), NEGATIVE),
        ("TRUNCATED",      qa.get("truncated", 0),      WARN),
        ("DROPPED ARTICLES", qa.get("dropped_articles", 0), TEXT_HI),
    ]
    for col, (label, value, accent) in zip(cols, cells):
        color = accent if value > 0 else TEXT_HI
        with col:
            st.markdown(
                f"""
                <div class="panel" style="padding:10px 14px;">
                  <div style="color:{DIM}; font-size:10px; letter-spacing:1.5px; font-weight:600;">{label}</div>
                  <div class="num" style="color:{color}; font-size:23px; font-weight:700; line-height:1.05; margin-top:2px;">{value}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
