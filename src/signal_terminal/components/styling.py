"""Inject CSS once at page-load — tightens Streamlit's chrome and pins the typeface."""
import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&display=swap');

html, body, [class*="css"] { font-family: 'JetBrains Mono', monospace !important; }

[data-testid="stAppViewContainer"] { background: #0d1117; }
[data-testid="stHeader"] { background: #0b0f14; border-bottom: 1px solid #1f2630; }

/* tighten the main block — terminal density */
.main .block-container { padding-top: 0.6rem; padding-bottom: 0.5rem; padding-left: 1rem; padding-right: 1rem; max-width: 100% !important; }

/* tabs — active = white underline, no cyan */
[data-baseweb="tab-list"] { border-bottom: 1px solid #1f2630; }
[data-baseweb="tab"] {
    font-family: 'JetBrains Mono', monospace !important;
    color: #6e7681 !important; padding: 8px 18px !important;
    text-transform: uppercase; letter-spacing: 1.5px; font-size: 10px;
}
[data-baseweb="tab"][aria-selected="true"] {
    color: #e6edf3 !important;
    border-bottom: 2px solid #e6edf3 !important;
}

/* panels look like frames */
.panel {
    background: #0a0e13; border: 1px solid #1f2630; padding: 12px 14px;
    margin-bottom: 8px;
}
.panel-title {
    text-transform: uppercase;
    letter-spacing: 1.5px;
    font-size: 16px;
    font-weight: 400;
    color: #00e5ff;
    margin: 10px 0 6px;
}

/* tabular figures everywhere */
.metric, .num { font-variant-numeric: tabular-nums; }

/* the cyan diamond glyph */
.fresh-mark { color: #00e5ff; font-weight: 700; }

/* a "boot" splash for the initial render */
.boot {
    color: #00e5ff; font-family: 'JetBrains Mono', monospace; font-size: 14px;
    text-align: center; padding: 60px 0; letter-spacing: 2px;
}
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def panel(title: str | None = None) -> None:
    """Open a panel via a contextmanager-like wrapper — use as `with panel(...):`."""
    raise NotImplementedError  # placeholder
