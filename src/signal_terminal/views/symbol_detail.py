"""Symbol Detail — stub (full build tomorrow vs. live data).

Picker is rendered first so its value drives the rest of the page. The empty
state only renders in the data area when no symbol is picked AND no
cross-filter set `selected_symbol` from elsewhere (Pulse heatmap, movers row,
drivers row).
"""
import streamlit as st

from signal_terminal import loader
from signal_terminal.config import Config
from signal_terminal.style import DIM, FAINT
from signal_terminal.views._common import (apply_band, correlation_filter_controls,
                                            hint, is_default_corr_filter,
                                            window_label, window_selector)


def render(cfg: Config) -> None:
    df_uni = loader.universe_latest(cfg)
    symbols = sorted(df_uni["symbol"].unique().tolist()) if not df_uni.empty else []

    if not symbols:
        st.markdown(
            f"<div style='color:{DIM}'>no symbols available — papier.db is empty</div>",
            unsafe_allow_html=True,
        )
        return

    # Picker first. The cross-page `selected_symbol` flows into the picker only
    # when it changes from the outside (Pulse heatmap, movers row, etc.); after
    # that the picker is the source of truth, so the user's own clicks aren't
    # overwritten by the still-set cross-filter value.
    PICKER_KEY = "symbol_detail_picker"
    LAST_PUSHED_KEY = "_symbol_detail_last_pushed"
    external = st.session_state.get("selected_symbol")
    last_pushed = st.session_state.get(LAST_PUSHED_KEY)

    if external and external in symbols and external != last_pushed:
        st.session_state[PICKER_KEY] = external
        st.session_state[LAST_PUSHED_KEY] = external

    cols = st.columns([1, 6])
    with cols[0]:
        picked = st.selectbox(
            "SYMBOL",
            symbols,
            placeholder="pick a symbol",
            label_visibility="collapsed",
            key=PICKER_KEY,
        )

    # Sync selected_symbol when the picker drives the change locally. Also push
    # the sentinel so the cross-filter block above doesn't bounce us next run.
    if picked and picked != external:
        st.session_state["selected_symbol"] = picked
        st.session_state[LAST_PUSHED_KEY] = picked

    sym = picked or external

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

    # Lookback shared with Driver Detail / Driver Correlation, so the drivers
    # panel below reads on the SAME horizon those tabs do — keeps the cross-tab
    # story consistent (e.g. GOOG's drivers here ⊇ GOOG's row in the corr tab).
    hours = window_selector("symbol")
    hint("how far back to read drivers for this symbol. matches the lookback on "
         "the Driver Detail and Driver Correlation tabs.")

    hist = loader.symbol_history(cfg, sym, days=180)
    st.write(f"{len(hist)} window rows in history (180 days)")
    if not hist.empty:
        st.dataframe(
            hist[["window_start", "sentiment", "sentiment_confidence",
                  "materiality", "geo_risk", "article_count", "source_count", "status"]],
            use_container_width=True, hide_index=True,
        )

    drivers = loader.symbol_drivers_window(cfg, sym, hours=hours)
    st.markdown(
        f"<div class='panel-title'>DRIVERS — {window_label(hours)} ROLLUP</div>",
        unsafe_allow_html=True,
    )
    hint("every driver PAPIER tagged for this symbol in the lookback, "
         "aggregated across all windows. one row per canonical driver. "
         "use the filters below to narrow this list using the same knobs as "
         "the Driver Correlation tab — settings stay in sync across tabs.")

    # Same metric / min-symbols / range controls as Driver Correlation. State
    # lives in canonical session_state keys so changes here are reflected on
    # the corr tab and vice versa. At default settings the controls are no-ops
    # and the full driver list shows.
    metric, min_symbols, low, high = correlation_filter_controls("symtab")

    full_n = len(drivers)
    filter_note = ""
    if not drivers.empty and not is_default_corr_filter(metric, min_symbols, low, high):
        # Apply the same cluster filter as the corr tab, then intersect.
        corr = loader.driver_correlation_matrix(
            cfg, hours=hours, limit=10_000,
            metric=metric, min_symbols=min_symbols,
        )
        masked, _, _ = apply_band(corr, low, high)
        surviving = set(masked.columns) if not masked.empty else set()
        drivers = drivers[drivers["canonical_term"].isin(surviving)].reset_index(drop=True)
        dropped = full_n - len(drivers)
        filter_note = (
            f"<div style='color:{FAINT}; font-size:11px; margin:-2px 0 8px;'>"
            f"showing {len(drivers)} of {full_n} drivers · "
            f"{dropped} dropped by cluster filters above."
            f"</div>"
        )
    if filter_note:
        st.markdown(filter_note, unsafe_allow_html=True)

    if drivers.empty:
        st.markdown(
            f"<div class='panel' style='color:{FAINT}'>no drivers tagged for "
            f"<b>{sym}</b> in the last {window_label(hours)}.</div>",
            unsafe_allow_html=True,
        )
    else:
        show = drivers.rename(columns={
            "canonical_term":          "driver",
            "n_windows":               "windows",
            "max_weight":              "max_weight",
            "mean_weight":             "avg_weight",
            "mean_term_sentiment":     "avg_sent",
            "hours_since_last_window": "last_seen_hrs_ago",
        })[[
            "driver", "windows", "max_weight", "avg_weight", "avg_sent",
            "last_seen_hrs_ago",
        ]]
        st.dataframe(
            show,
            hide_index=True,
            use_container_width=True,
            column_config={
                "driver":            st.column_config.TextColumn("DRIVER"),
                "windows":           st.column_config.NumberColumn(
                    "WIN", help="# of windows this driver appeared in",
                    format="%d",
                ),
                "max_weight":        st.column_config.ProgressColumn(
                    "MAX WEIGHT", help="strongest weight observed in any window",
                    min_value=0.0, max_value=1.0, format="%.2f",
                ),
                "avg_weight":        st.column_config.ProgressColumn(
                    "AVG WEIGHT", min_value=0.0, max_value=1.0, format="%.2f",
                ),
                "avg_sent":          st.column_config.NumberColumn(
                    "AVG SENT", help="mean term_sentiment across windows (-1..+1)",
                    format="%+.2f",
                ),
                "last_seen_hrs_ago": st.column_config.NumberColumn(
                    "LAST SEEN", help="hours since the most recent window with this driver",
                    format="%.1f",
                ),
            },
        )
