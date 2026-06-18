"""Sector Lens — stub (full build tomorrow)."""
import streamlit as st

from signal_terminal import loader
from signal_terminal.config import Config
from signal_terminal.style import DIM, SECTOR_COLOR


def render(cfg: Config) -> None:
    agg = loader.sector_aggregates(cfg)
    st.markdown("<div class='panel-title'>SECTOR CARDS</div>", unsafe_allow_html=True)
    if agg.empty:
        st.markdown(f"<div style='color:{DIM}'>no sector data yet</div>", unsafe_allow_html=True)
        return
    cols = st.columns(len(agg))
    for col, (_, row) in zip(cols, agg.iterrows()):
        color = SECTOR_COLOR.get(row["sector"], "#4d5560")
        with col:
            st.markdown(
                f"""
                <div class="panel" style="border-left: 4px solid {color};">
                  <div style="color:{color}; font-size:10px; letter-spacing:1.5px; font-weight:700;">{row['sector'].upper()}</div>
                  <div class='num' style='color:#e6edf3; font-size:20px; font-weight:700'>{row['mean_sentiment']:+.2f}</div>
                  <div style='color:{DIM}; font-size:10px; letter-spacing:1.5px'>
                    {int(row['n_symbols'])} SYM · MAT {row['mean_materiality']:.2f} · GEO {row['mean_geo_risk']:.2f}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    st.markdown("<div class='panel-title' style='margin-top:14px'>TRAILING 180D · MEAN SENTIMENT BY SECTOR</div>", unsafe_allow_html=True)
    hist = loader.sector_history(cfg, "sentiment", days=180)
    if not hist.empty:
        import plotly.graph_objects as go
        from signal_terminal.style import PLOTLY_CONFIG, layout
        fig = go.Figure()
        for sector in hist["sector"].unique():
            sub = hist[hist["sector"] == sector]
            fig.add_trace(go.Scatter(
                x=sub["day"], y=sub["value"], mode="lines", name=sector,
                line=dict(color=SECTOR_COLOR.get(sector, "#8b949e"), width=1.4),
            ))
        fig.update_layout(**layout(
            height=320, yaxis=dict(range=[-1, 1]),
            showlegend=True, legend=dict(orientation="h", font=dict(size=9)),
        ))
        st.plotly_chart(fig, config=PLOTLY_CONFIG, use_container_width=True)
