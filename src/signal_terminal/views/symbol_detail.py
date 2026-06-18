"""Symbol Detail — stub (full build tomorrow vs. live data).

Picker is rendered first so its value drives the rest of the page. The empty
state only renders in the data area when no symbol is picked AND no
cross-filter set `selected_symbol` from elsewhere (Pulse heatmap, movers row,
drivers row).
"""
import streamlit as st

from signal_terminal import loader
from signal_terminal.config import Config
from signal_terminal.style import DIM


def render(cfg: Config) -> None:
    df_uni = loader.universe_latest(cfg)
    symbols = sorted(df_uni["symbol"].unique().tolist()) if not df_uni.empty else []

    if not symbols:
        st.markdown(
            f"<div style='color:{DIM}'>no symbols available — papier.db is empty</div>",
            unsafe_allow_html=True,
        )
        return

    # Picker first. Defaults to whatever's in `selected_symbol` (e.g. set by a
    # Pulse cross-filter), otherwise nothing.
    #
    # Streamlit gotcha: once a widget with a `key` has been rendered, its
    # session_state value sticks and `index=` is ignored on later runs. So we
    # pre-write the widget state ourselves when cross-page selection differs.
    current = st.session_state.get("selected_symbol")
    PICKER_KEY = "symbol_detail_picker"
    if current and current in symbols and st.session_state.get(PICKER_KEY) != current:
        st.session_state[PICKER_KEY] = current

    cols = st.columns([1, 6])
    with cols[0]:
        picked = st.selectbox(
            "SYMBOL",
            symbols,
            placeholder="pick a symbol",
            label_visibility="collapsed",
            key=PICKER_KEY,
        )

    # Sync selected_symbol when the picker drives the change locally.
    if picked and picked != current:
        st.session_state["selected_symbol"] = picked

    sym = picked or current

    if not sym:
        st.markdown(
            f"""
            <div style='color:{DIM}; padding:24px 0 12px;'>
              <div style='font-size:12px; letter-spacing:1.5px; font-weight:600;'>NO SYMBOL SELECTED</div>
              <div style='font-size:11px; margin-top:4px;'>
                Pick one in the dropdown above, or click a tile / mover row on Today's Pulse.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    st.markdown(f"<div class='panel-title'>SYMBOL DETAIL · {sym}</div>", unsafe_allow_html=True)
    hist = loader.symbol_history(cfg, sym, days=180)
    st.write(f"{len(hist)} window rows in history (180 days)")
    if not hist.empty:
        st.dataframe(
            hist[["window_start", "sentiment", "sentiment_confidence",
                  "materiality", "geo_risk", "article_count", "source_count", "status"]],
            use_container_width=True, hide_index=True,
        )
        drivers = loader.symbol_drivers(cfg, sym, hist["window_start"].iloc[-1])
        if not drivers.empty:
            st.markdown("<div class='panel-title'>DRIVERS — LATEST WINDOW</div>", unsafe_allow_html=True)
            st.dataframe(drivers, use_container_width=True, hide_index=True)
