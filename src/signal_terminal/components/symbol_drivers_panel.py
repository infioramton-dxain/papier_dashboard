"""Drivers panel — shows term-level breakdown for a selected symbol's latest window.

Used on Today's Pulse below the heatmap so the user can see WHY a tile is what
it is without leaving the page.
"""
import pandas as pd
import streamlit as st

from signal_terminal.style import (DIM, FRESH, NEGATIVE, POSITIVE, TEXT_HI, sentiment_color)


def _sentiment_dot(v: float) -> str:
    if v > 0.1:
        return f"<span style='color:{POSITIVE}; font-size:11px'>●</span>"
    if v < -0.1:
        return f"<span style='color:{NEGATIVE}; font-size:11px'>●</span>"
    return f"<span style='color:#4d5560; font-size:11px'>·</span>"


def _bar(weight: float, width_px: int = 110, color: str = TEXT_HI) -> str:
    pct = max(0.0, min(1.0, float(weight)))
    return (
        f"<div style='display:inline-block; width:{width_px}px; height:5px; "
        f"background:#11161d; vertical-align:middle; margin-right:8px;'>"
        f"<div style='width:{int(pct*width_px)}px; height:5px; background:{color};'></div></div>"
    )


def render_placeholder() -> None:
    st.markdown(
        f"""
        <div class='panel' style='padding:14px 16px; margin-top:12px;'>
          <div class='panel-title'>DRIVERS</div>
          <div style='color:{DIM}; font-size:11px; padding:8px 0;'>
            Click a tile on the heatmap or a mover row to see term drivers for that symbol.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render(symbol: str, drivers_df: pd.DataFrame, window_start: str | None) -> None:
    """drivers_df columns: term, canonical_term, weight, term_sentiment"""
    label = f"DRIVERS — {symbol}"
    if window_start:
        label += f"  ·  WINDOW {window_start[:13].replace('T', ' ')}Z"

    st.markdown(f"<div class='panel-title' style='margin-top:12px'>{label}</div>",
                unsafe_allow_html=True)

    if drivers_df is None or drivers_df.empty:
        st.markdown(
            f"<div class='panel' style='padding:10px 14px; color:{DIM}; font-size:11px;'>"
            f"no terms recorded for this symbol's latest window — the model decided nothing "
            f"was tag-worthy, or this symbol predates the terms-aware backfill.</div>",
            unsafe_allow_html=True,
        )
        return

    df = drivers_df.sort_values("weight", ascending=False).head(20).copy()
    rows_html = []
    for _, r in df.iterrows():
        term = r.get("canonical_term") or r["term"]
        bar_color = sentiment_color(r["term_sentiment"])
        rows_html.append(
            f"<tr>"
            f"<td style='padding:5px 10px; vertical-align:middle;'>{_sentiment_dot(r['term_sentiment'])}</td>"
            f"<td style='padding:5px 10px; color:{TEXT_HI}; font-size:12px;'>{term}</td>"
            f"<td style='padding:5px 10px;'>{_bar(r['weight'], color=bar_color)}</td>"
            f"<td class='num' style='padding:5px 10px; color:{TEXT_HI}; font-size:11px; text-align:right;'>"
            f"  w {r['weight']:.2f}"
            f"</td>"
            f"<td class='num' style='padding:5px 10px; color:{TEXT_HI}; font-size:11px; text-align:right;'>"
            f"  s {r['term_sentiment']:+.2f}"
            f"</td>"
            f"</tr>"
        )
    st.markdown(
        "<div class='panel' style='padding:6px 6px;'>"
        "<table style='width:100%; border-collapse:collapse; font-family:JetBrains Mono;'>"
        "<thead><tr>"
        f"<th style='text-align:left; color:{DIM}; font-size:9px; letter-spacing:1.5px; padding:6px 10px;'></th>"
        f"<th style='text-align:left; color:{DIM}; font-size:9px; letter-spacing:1.5px; padding:6px 10px;'>TERM</th>"
        f"<th style='text-align:left; color:{DIM}; font-size:9px; letter-spacing:1.5px; padding:6px 10px;'>WEIGHT</th>"
        f"<th style='text-align:right; color:{DIM}; font-size:9px; letter-spacing:1.5px; padding:6px 10px;'>W</th>"
        f"<th style='text-align:right; color:{DIM}; font-size:9px; letter-spacing:1.5px; padding:6px 10px;'>SENT</th>"
        "</tr></thead><tbody>"
        + "".join(rows_html)
        + "</tbody></table></div>",
        unsafe_allow_html=True,
    )

    # Small "view full symbol detail" link via a button
    cols = st.columns([6, 1])
    with cols[1]:
        if st.button("× clear", key=f"drivers_clear_{symbol}"):
            st.session_state["selected_symbol"] = None
            st.rerun()
