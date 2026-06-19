"""Signal Terminal — single-page dashboard.

Tabs (left → right):
  1. TODAY'S PULSE          — landing terminal
  2. SYMBOL DETAIL          — drill into one ticker
  3. SECTOR LENS            — sector aggregates over time
  4. DRIVER DETAIL          — focus on a single canonical_term
  5. DRIVER CORRELATION     — pairwise driver structure
  6. PIPELINE HEALTH        — runs / drops / QA
  7. FACTORS                — PCA + NMF latent factors  (analytics)
  8. COHORTS                — hierarchical + k-means cohorts (analytics)
  9. EVENTS                 — event-flag co-occurrence / firing rates (analytics)

The last three are governed by a shared sidebar (`an_*` keys in session_state);
the first six ignore the sidebar.
"""
import sys
from pathlib import Path

import streamlit as st

# Make src/ importable without installing
sys.path.insert(0, str(Path(__file__).parent / "src"))

from signal_terminal import state
from signal_terminal.analytics import data as andata
from signal_terminal.components.styling import inject as inject_css
from signal_terminal.config import load as load_config
from signal_terminal.db import db_has_data
from signal_terminal.sectors import all_sectors
from signal_terminal.style import DIM, FAINT, FRESH, TEXT_HI, WARN
from signal_terminal.views import (cohorts, driver_correlation, driver_detail,
                                    events, factors, pipeline_health, pulse,
                                    sector_lens, symbol_detail)

st.set_page_config(
    page_title="Signal Terminal",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="collapsed",
)

inject_css()
state.init()
cfg = load_config()


# --- analytics sidebar ------------------------------------------------------
# Collapsed by default. Drives only the FACTORS / COHORTS / EVENTS tabs; the
# other six tabs ignore it.
def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown(
            f"<div style='color:{TEXT_HI}; font-size:13px; font-weight:700; "
            f"letter-spacing:2px;'>ANALYTICS FILTERS</div>"
            f"<div style='color:{FAINT}; font-size:10px; letter-spacing:1px; "
            f"margin:-2px 0 12px;'>applies to factors · cohorts · events</div>",
            unsafe_allow_html=True,
        )
        if not db_has_data(cfg.db_path):
            st.markdown(
                f"<div style='color:{WARN}; font-size:11px; line-height:1.5;'>"
                f"papier.db not found or empty — analytics tabs will be inert. "
                f"The first six tabs will run on mock data.</div>",
                unsafe_allow_html=True,
            )
            return
        # Date range — defaults to full coverage on first render.
        lo, hi = andata.coverage_bounds(str(cfg.db_path))
        if lo is not None and st.session_state.get("an_date_start") is None:
            st.session_state["an_date_start"] = lo
            st.session_state["an_date_end"] = hi
        c1, c2 = st.columns(2)
        with c1:
            st.date_input("FROM (UTC)", key="an_date_start",
                          min_value=lo, max_value=hi)
        with c2:
            st.date_input("TO (UTC)", key="an_date_end",
                          min_value=lo, max_value=hi)
        # Symbol multiselect — searchable.
        universe = andata.universe_symbols(str(cfg.db_path))
        st.multiselect("SYMBOLS", options=universe, key="an_symbols",
                        placeholder="all symbols",
                        help="empty = full universe")
        st.multiselect("SECTORS", options=list(all_sectors()), key="an_sectors",
                        placeholder="all sectors")
        st.slider("MIN ARTICLE COUNT / WINDOW", min_value=1, max_value=10,
                  step=1, key="an_min_articles")
        st.radio("AGGREGATION GRAIN",
                 options=["hourly", "daily", "weekly"],
                 horizontal=True, key="an_grain")
        st.multiselect("STATUS",
                       options=["ok", "malformed_json", "flagged"],
                       key="an_status", default=["ok"])
        st.toggle("AI TAKEAWAYS (LOCAL OLLAMA)", key="an_ai_takeaways",
                  help="Layer 2 dynamic interpretations cached in "
                       "data/cache/descriptions.json. Falls back to a quiet "
                       "'unavailable' line if Ollama is not running.")
        # Cross-model warning banner
        filters = andata.Filters(
            date_start=st.session_state.get("an_date_start"),
            date_end=st.session_state.get("an_date_end"),
            symbols=tuple(st.session_state.get("an_symbols") or ()) or None,
            sectors=tuple(st.session_state.get("an_sectors") or ()) or None,
            min_article_count=int(st.session_state.get("an_min_articles", 1)),
            grain=st.session_state.get("an_grain", "daily"),
            status=tuple(st.session_state.get("an_status") or ("ok",)),
        )
        sources = andata.distinct_score_sources(str(cfg.db_path), filters)
        if len(sources) > 1:
            st.markdown(
                f"<div style='background:#26210e; border:1px solid {WARN}; "
                f"padding:8px 10px; border-radius:4px; margin-top:10px;'>"
                f"<div style='color:{WARN}; font-size:10px; letter-spacing:1.5px; "
                f"font-weight:700;'>CROSS-MODEL WARNING</div>"
                f"<div style='color:{DIM}; font-size:11px; margin-top:4px;'>"
                f"Filtered data spans {len(sources)} score_source values — "
                f"results before the last model change are not directly "
                f"comparable.</div></div>",
                unsafe_allow_html=True,
            )
            with st.expander("see model ids"):
                for s in sources:
                    st.markdown(f"<div style='color:{DIM}; font-size:10px;'>· {s}</div>",
                                 unsafe_allow_html=True)


_render_sidebar()


# --- top bar ----------------------------------------------------------------
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

# --- tabs -------------------------------------------------------------------
# Note: st.tabs is client-side, so programmatic switching from a cross-filter
# isn't supported. Cross-filter writes `selected_symbol` to session_state;
# clicking the SYMBOL DETAIL tab picks it up.
(pulse_tab, symbol_tab, sector_tab, driver_tab, driver_corr_tab,
 pipeline_tab, factors_tab, cohorts_tab, events_tab) = st.tabs([
    "TODAY'S PULSE", "SYMBOL DETAIL", "SECTOR LENS",
    "DRIVER DETAIL", "DRIVER CORRELATION", "PIPELINE HEALTH",
    "FACTORS", "COHORTS", "EVENTS",
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
with factors_tab:
    factors.render(cfg)
with cohorts_tab:
    cohorts.render(cfg)
with events_tab:
    events.render(cfg)
