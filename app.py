"""Signal Terminal — single-page dashboard with 4 tabs."""
import sys
from pathlib import Path

import streamlit as st

# Make src/ importable without installing
sys.path.insert(0, str(Path(__file__).parent / "src"))

from signal_terminal import state
from signal_terminal.components.styling import inject as inject_css
from signal_terminal.config import load as load_config
from signal_terminal.style import DIM, FRESH, TEXT_HI
from signal_terminal.views import (driver_correlation, driver_detail,
                                    pipeline_health, pulse, sector_lens,
                                    symbol_detail)

st.set_page_config(
    page_title="Signal Terminal",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="collapsed",
)

inject_css()
state.init()
cfg = load_config()

# --- top bar ---
bar = st.columns([2, 4, 1])
with bar[0]:
    st.markdown(
        f"""<div style='display:flex; align-items:center; gap:10px; padding:6px 0 4px;'>
            <span style='color:{FRESH}; font-size:18px'>◆</span>
            <span style='color:{TEXT_HI}; font-size:16px; font-weight:700; letter-spacing:2px;'>
              SIGNAL TERMINAL
            </span>
            <span style='color:{DIM}; font-size:10px; letter-spacing:1.5px; margin-left:8px;'>
              · PAPIER
            </span>
        </div>""",
        unsafe_allow_html=True,
    )
with bar[2]:
    if st.button("↻ REFRESH", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- tabs ---
# Note: st.tabs is client-side, so programmatic switching from a cross-filter
# isn't supported. Cross-filter writes `selected_symbol` to session_state;
# clicking the SYMBOL DETAIL tab picks it up.
(pulse_tab, symbol_tab, sector_tab, driver_tab, driver_corr_tab,
 pipeline_tab) = st.tabs([
    "TODAY'S PULSE", "SYMBOL DETAIL", "SECTOR LENS",
    "DRIVER DETAIL", "DRIVER CORRELATION", "PIPELINE HEALTH",
])

with pulse_tab:
    pulse.render(cfg)
with symbol_tab:
    symbol_detail.render(cfg)
with sector_tab:
    sector_lens.render(cfg)
with driver_tab:
    driver_detail.render(cfg)
with driver_corr_tab:
    driver_correlation.render(cfg)
with pipeline_tab:
    pipeline_health.render(cfg)
