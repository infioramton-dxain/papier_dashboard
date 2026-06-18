"""Event-flag counter row — 7 cells, one per event flag, with fresh marker."""
import pandas as pd
import streamlit as st

from signal_terminal.style import DIM, FRESH, TEXT_HI, Type


def render(df: pd.DataFrame) -> None:
    """df columns: flag, label, count, fresh_count"""
    cols = st.columns(len(df))
    for col, (_, row) in zip(cols, df.iterrows()):
        fresh = row["fresh_count"] > 0
        edge = f"border-left: 3px solid {FRESH};" if fresh else "border-left: 3px solid transparent;"
        fresh_html = (
            f"<div style='color:{FRESH}; font-size:9px; letter-spacing:1.5px; "
            f"font-weight:700; margin-top:2px;'>◆ {row['fresh_count']} NEW</div>"
            if fresh else "<div style='height:14px'></div>"
        )
        with col:
            st.markdown(
                f"""
                <div class="panel" style="{edge} padding:10px 12px;">
                  <div style="color:{DIM}; font-size:10px; letter-spacing:1.5px; font-weight:600;">
                    {row['label']}
                  </div>
                  <div class="num" style="color:{TEXT_HI}; font-size:25px; font-weight:700; line-height:1.05;">
                    {row['count']}
                  </div>
                  {fresh_html}
                </div>
                """,
                unsafe_allow_html=True,
            )
