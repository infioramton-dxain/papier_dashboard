"""Ranked movers panel — click a row to jump to Symbol Detail."""
import pandas as pd
import streamlit as st

from signal_terminal.state import go_symbol
from signal_terminal.style import (DIM, FRESH, NEGATIVE, POSITIVE, SECTOR_COLOR,
                                    TEXT_HI, sentiment_color)


def _bar(value: float, width_px: int = 90) -> str:
    """Inline sentiment-colored mini bar. value ∈ [-1, 1]."""
    pct = min(1.0, abs(value))
    color = sentiment_color(value)
    return (
        f"<div style='display:inline-block; width:{width_px}px; height:6px; "
        f"background:#11161d; vertical-align:middle; margin-right:8px;'>"
        f"<div style='width:{int(pct*width_px)}px; height:6px; background:{color};'></div></div>"
    )


def render_abs(df: pd.DataFrame, title: str = "MOVERS — |SENTIMENT|") -> None:
    """df columns: symbol, sector, sentiment, materiality, article_count, fresh"""
    if df.empty:
        st.markdown(f"<div class='panel-title'>{title}</div><div style='color:#6e7681'>no rows</div>", unsafe_allow_html=True)
        return
    st.markdown(f"<div class='panel-title'>{title}</div>", unsafe_allow_html=True)
    for i, (_, row) in enumerate(df.iterrows(), 1):
        sector_color = SECTOR_COLOR.get(row["sector"], "#4d5560")
        fresh_mark = " <span class='fresh-mark'>◆</span>" if row.get("fresh") else ""
        cols = st.columns([0.5, 1.2, 1.5, 4.0, 1.0, 0.8])
        with cols[0]:
            st.markdown(f"<div style='color:#6e7681; font-size:11px'>{i}</div>", unsafe_allow_html=True)
        with cols[1]:
            if st.button(row["symbol"], key=f"mover_abs_{row['symbol']}_{i}",
                         use_container_width=True, type="secondary"):
                go_symbol(row["symbol"])
                st.rerun()
        with cols[2]:
            st.markdown(
                f"<div style='color:{sector_color}; font-size:10px; letter-spacing:1.5px; "
                f"font-weight:600; padding-top:7px'>{row['sector'].upper()}{fresh_mark}</div>",
                unsafe_allow_html=True,
            )
        with cols[3]:
            st.markdown(_bar(row["sentiment"]), unsafe_allow_html=True)
        with cols[4]:
            st.markdown(
                f"<div class='num' style='color:{TEXT_HI}; padding-top:5px'>{row['sentiment']:+.2f}</div>",
                unsafe_allow_html=True,
            )
        with cols[5]:
            st.markdown(
                f"<div style='color:#6e7681; font-size:10px; padding-top:7px'>{int(row['article_count'])}a</div>",
                unsafe_allow_html=True,
            )


def render_delta(df: pd.DataFrame, title: str = "MOVERS — Δ VS PRIOR 24H") -> None:
    """df columns: symbol, sector, sentiment_now, sentiment_prior, delta, abs_delta, fresh"""
    if df.empty:
        st.markdown(f"<div class='panel-title'>{title}</div><div style='color:#6e7681'>no rows</div>", unsafe_allow_html=True)
        return
    st.markdown(f"<div class='panel-title'>{title}</div>", unsafe_allow_html=True)
    for i, (_, row) in enumerate(df.iterrows(), 1):
        sector_color = SECTOR_COLOR.get(row["sector"], "#4d5560")
        arrow = "▲" if row["delta"] > 0 else "▼"
        arrow_color = POSITIVE if row["delta"] > 0 else NEGATIVE
        fresh_mark = " <span class='fresh-mark'>◆</span>" if row.get("fresh") else ""
        cols = st.columns([0.5, 1.2, 1.5, 3.5, 1.6, 0.7])
        with cols[0]:
            st.markdown(f"<div style='color:#6e7681; font-size:11px'>{i}</div>", unsafe_allow_html=True)
        with cols[1]:
            if st.button(row["symbol"], key=f"mover_delta_{row['symbol']}_{i}",
                         use_container_width=True, type="secondary"):
                go_symbol(row["symbol"])
                st.rerun()
        with cols[2]:
            st.markdown(
                f"<div style='color:{sector_color}; font-size:10px; letter-spacing:1.5px; "
                f"font-weight:600; padding-top:7px'>{row['sector'].upper()}{fresh_mark}</div>",
                unsafe_allow_html=True,
            )
        with cols[3]:
            st.markdown(_bar(row["delta"]), unsafe_allow_html=True)
        with cols[4]:
            st.markdown(
                f"<div class='num' style='color:{arrow_color}; padding-top:5px'>"
                f"{arrow} {abs(row['delta']):.2f} "
                f"<span style='color:{DIM}; font-size:10px'>{row['sentiment_prior']:+.1f}→{row['sentiment_now']:+.1f}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
        with cols[5]:
            st.markdown(" ", unsafe_allow_html=True)
