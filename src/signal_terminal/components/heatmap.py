"""Universe heatmap — three encodings: treemap, dense grid, sector group.

Clickable: dense_grid and sector_group both attach `customdata=symbol` so a
plotly point-click writes `selected_symbol` to session_state. Treemap fires a
click event with `label` which we also try. After clicking, switch to the
SYMBOL DETAIL tab manually to view the selected ticker.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from signal_terminal.state import go_symbol
from signal_terminal.style import (BORDER, LAYOUT, NEUTRAL, PLOTLY_CONFIG, SECTOR_COLOR,
                                    SENTIMENT_COLORSCALE, SURFACE, layout, sentiment_color)


def _treemap(df: pd.DataFrame) -> go.Figure:
    df = df.copy()
    df["area"] = df["materiality"].fillna(0.0) + 0.04
    labels = [df["sector"].iloc[0], *df["symbol"].tolist()] if not df.empty else [""]
    parents = ["", *(df["sector"].tolist())]
    values = [df["area"].sum(), *df["area"].tolist()]
    colors = [SURFACE, *[sentiment_color(v) for v in df["sentiment"].tolist()]]

    # Multiple sector parents → restructure
    parents = []
    labels = list(df["symbol"])
    parents = list(df["sector"])
    # Inject unique sector parents
    for sec in df["sector"].unique():
        labels.append(sec)
        parents.append("")
    values_parent = df.groupby("sector")["area"].sum().to_dict()
    values = df["area"].tolist() + [values_parent[s] for s in df["sector"].unique()]
    colors = [sentiment_color(v) for v in df["sentiment"].tolist()] + [SURFACE for _ in df["sector"].unique()]

    fig = go.Figure(go.Treemap(
        labels=labels, parents=parents, values=values, branchvalues="total",
        marker=dict(colors=colors, line=dict(color="#0a0e13", width=1)),
        hovertemplate="<b>%{label}</b><br>area=%{value:.2f}<extra></extra>",
        textfont=dict(family="JetBrains Mono", size=10),
        textinfo="label",
    ))
    fig.update_layout(**layout(height=400, margin=dict(l=2, r=2, t=2, b=2)))
    return fig


def _dense_grid(df: pd.DataFrame) -> go.Figure:
    """Bar-on-grid via go.Heatmap-ish using scatter; for v1 we use a simple sorted-bar layout."""
    df = df.sort_values("sentiment", ascending=False).reset_index(drop=True)
    cols = 12
    df["row"] = df.index // cols
    df["col"] = df.index % cols
    fig = go.Figure(go.Scatter(
        x=df["col"], y=df["row"],
        mode="markers+text",
        text=df["symbol"],
        customdata=df[["symbol"]].values,
        textfont=dict(family="JetBrains Mono", size=9, color="#e6edf3"),
        marker=dict(
            color=df["sentiment"], colorscale=SENTIMENT_COLORSCALE, cmin=-1, cmax=1,
            size=42, symbol="square", line=dict(
                color="#1f2630",
                width=(1 + df["materiality"].fillna(0.0) * 2),
            ),
        ),
        hovertemplate="<b>%{text}</b><br>sentiment=%{marker.color:+.2f}<extra></extra>",
    ))
    fig.update_layout(**layout(
        height=400,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False, autorange="reversed"),
    ))
    return fig


def _sector_group(df: pd.DataFrame) -> go.Figure:
    sectors = sorted(df["sector"].unique())
    cols_per_sector = 6
    rows_data = []
    for s_idx, sector in enumerate(sectors):
        sub = df[df["sector"] == sector].sort_values("sentiment", ascending=False).reset_index(drop=True)
        for i, row in sub.iterrows():
            rows_data.append({
                "sector": sector,
                "x": s_idx,
                "y": i // cols_per_sector,
                "sub_x": i % cols_per_sector,
                "symbol": row["symbol"],
                "sentiment": row["sentiment"],
                "materiality": row["materiality"] or 0,
            })
    if not rows_data:
        fig = go.Figure()
        fig.update_layout(**layout(height=400))
        return fig
    d = pd.DataFrame(rows_data)
    # Layout: x = sector_index * cols_per_sector + sub_x
    d["plot_x"] = d["x"] * (cols_per_sector + 1) + d["sub_x"]
    fig = go.Figure(go.Scatter(
        x=d["plot_x"], y=d["y"],
        mode="markers+text", text=d["symbol"],
        textfont=dict(family="JetBrains Mono", size=9, color="#e6edf3"),
        marker=dict(
            color=d["sentiment"], colorscale=SENTIMENT_COLORSCALE, cmin=-1, cmax=1,
            size=38, symbol="square",
            line=dict(color="#1f2630", width=(1 + d["materiality"] * 2)),
        ),
        hovertemplate="<b>%{text}</b><br>sector=%{customdata[0]}<br>sentiment=%{marker.color:+.2f}<extra></extra>",
        customdata=d[["sector"]].values,
    ))
    # sector header labels along the top
    annotations = []
    for s_idx, sector in enumerate(sectors):
        sub = df[df["sector"] == sector]
        annotations.append(dict(
            x=s_idx * (cols_per_sector + 1) + (cols_per_sector - 1) / 2,
            y=-1.0, xref="x", yref="y",
            text=f"<b>{sector.upper()}</b> ·  μ {sub['sentiment'].mean():+.2f}",
            font=dict(family="JetBrains Mono", size=10, color=SECTOR_COLOR.get(sector, "#8b949e")),
            showarrow=False,
        ))
    fig.update_layout(**layout(
        height=400,
        annotations=annotations,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False, autorange="reversed"),
        margin=dict(l=10, r=10, t=30, b=10),
    ))
    return fig


def render(df: pd.DataFrame, mode: str) -> None:
    """df columns: symbol, sector, sentiment, materiality. mode: treemap|grid|sector"""
    if df.empty:
        st.info("No symbols to display — universe is empty.")
        return

    if mode == "treemap":
        fig = _treemap(df)
    elif mode == "grid":
        fig = _dense_grid(df)
    elif mode == "sector":
        fig = _sector_group(df)
    else:
        fig = _dense_grid(df)

    event = st.plotly_chart(
        fig, config=PLOTLY_CONFIG, use_container_width=True,
        on_select="rerun", selection_mode="points",
        key=f"heatmap_chart_{mode}",
    )

    # Plotly click handler: scatter (grid / sector) uses customdata; treemap
    # passes a `label`. Try both. Only fire if the symbol is in the universe.
    sym: str | None = None
    if event and getattr(event, "selection", None):
        sel = event.selection
        points = sel.get("points") if isinstance(sel, dict) else getattr(sel, "points", None)
        if points:
            p = points[0]
            if isinstance(p, dict):
                cd = p.get("customdata")
                sym = (cd[0] if cd else None) or p.get("label")
            else:
                cd = getattr(p, "customdata", None)
                sym = (cd[0] if cd else None) or getattr(p, "label", None)

    if sym and sym in set(df["symbol"].values):
        # de-dup so the same click doesn't fire twice across reruns
        fired_key = f"heatmap_chart_{mode}__fired"
        if st.session_state.get(fired_key) != sym:
            st.session_state[fired_key] = sym
            go_symbol(sym)
            st.rerun()
