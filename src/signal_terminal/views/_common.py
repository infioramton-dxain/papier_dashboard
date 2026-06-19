"""Shared bits between Driver Detail and Driver Correlation tabs.

Both views use the same lookback (`driver_hours` in session_state) so a window
change on one is visible on the other. Each call site passes a `key_prefix` to
disambiguate Streamlit widget keys per tab.
"""
from collections.abc import Callable

import numpy as np
import pandas as pd
import streamlit as st

from signal_terminal.style import DIM, FAINT

WINDOW_CHOICES = [
    ("24H",  24),
    ("7D",   168),
    ("30D",  720),
    ("90D",  2160),
]

METRICS = [
    ("φ",       "phi"),
    ("JACCARD", "jaccard"),
]

MIN_SYMBOLS_MAX = 20


def hint(text: str) -> None:
    """One-line plain-English caption under a control. Quiet, non-shouty."""
    st.markdown(
        f"<div style='color:{FAINT}; font-size:11px; line-height:1.4; "
        f"letter-spacing:0; margin:-4px 0 8px; text-transform:none;'>"
        f"{text}</div>",
        unsafe_allow_html=True,
    )


def window_selector(key_prefix: str, on_change: Callable[[int], None] | None = None) -> int:
    """Render the 24H/7D/30D/90D button row backed by `driver_hours` state.

    `key_prefix` distinguishes Streamlit widget keys per tab.
    `on_change(new_hours)` is invoked when the user picks a new window — use
    it to clear tab-local state (selected_driver, paging, etc.) before rerun.
    """
    current = int(st.session_state.get("driver_hours", 168))
    cols = st.columns([1, 1, 1, 1, 6])
    for i, (label, hours) in enumerate(WINDOW_CHOICES):
        with cols[i]:
            if st.button(
                label,
                key=f"{key_prefix}_window_{label}",
                use_container_width=True,
                type=("primary" if current == hours else "secondary"),
            ):
                st.session_state["driver_hours"] = hours
                if on_change is not None:
                    on_change(hours)
                st.rerun()
    return current


def window_label(hours: int) -> str:
    for label, h in WINDOW_CHOICES:
        if h == hours:
            return label
    return f"{hours}H"


# ---------- correlation filter controls (shared by Driver Correlation + Symbol Detail) ----------
def _sync_widget(widget_key: str, canonical) -> None:
    """Push the canonical state into the widget slot when (and only when) the
    canonical has changed since we last pushed.

    Streamlit syncs `session_state[key]` ← user-input BEFORE the rerun, so by
    the time this runs the widget slot may already hold the user's just-clicked
    value. We must not overwrite it. We use a `_last_pushed_<widget_key>` slot
    to remember what we previously synced; if the canonical now differs, that
    means another tab (or a button handler) moved it, so we propagate.
    Otherwise we leave the widget alone — the user's input wins.
    """
    last_pushed_key = f"_last_pushed_{widget_key}"
    last_pushed = st.session_state.get(last_pushed_key)
    if widget_key not in st.session_state or canonical != last_pushed:
        st.session_state[widget_key] = canonical
        st.session_state[last_pushed_key] = canonical


def _confirm_widget_sync(widget_key: str, value) -> None:
    """Mark the widget's current value as 'in sync' so the NEXT render's
    `_sync_widget` doesn't see a phantom canonical change and clobber it.
    Call after the widget renders, once we've written its value back to the
    canonical state slot."""
    st.session_state[f"_last_pushed_{widget_key}"] = value


def correlation_filter_controls(
    key_prefix: str,
) -> tuple[str, int, float, float]:
    """Render the METRIC toggle + MIN SYMBOLS slider + score-RANGE slider.

    Canonical state lives in `corr_metric`, `corr_min_symbols`, `corr_band` so
    a change on one tab is reflected on the next render of every other tab that
    calls this helper. `key_prefix` disambiguates Streamlit widget keys per tab.

    Returns (metric, min_symbols, low, high).
    """
    metric = str(st.session_state.get("corr_metric", "phi"))
    symbol = "J" if metric == "jaccard" else "φ"

    # --- Row 1: METRIC label + two toggle buttons -----------------------------
    row1 = st.columns([3, 1, 1, 1])
    with row1[0]:
        st.markdown(
            f"<div style='color:{DIM}; font-size:10px; letter-spacing:1.5px; "
            f"margin-top:4px;'>METRIC</div>",
            unsafe_allow_html=True,
        )
    for i, (label, key) in enumerate(METRICS):
        with row1[1 + i]:
            if st.button(
                label, key=f"{key_prefix}_metric_{key}",
                use_container_width=True,
                type=("primary" if metric == key else "secondary"),
            ):
                st.session_state["corr_metric"] = key
                # Reset band to that metric's full range; clear corr cell.
                st.session_state["corr_band"] = (
                    (0.0, 1.0) if key == "jaccard" else (-1.0, 1.0)
                )
                st.session_state["driver_corr_cell"] = None
                st.rerun()
    hint(
        "<b>φ (phi)</b> shows both kinds of structure: green = drivers that "
        "co-occur on the same stocks, red = drivers that avoid each other. "
        "<b>Jaccard</b> is plain overlap: 0 = never share a stock, 1 = always "
        "do. Jaccard is steadier when most drivers appear on only a handful of "
        "stocks."
    )

    # --- Row 2: MIN SYMBOLS slider (left), RANGE slider (right) ---------------
    row2 = st.columns([3, 5])
    with row2[0]:
        st.markdown(
            f"<div style='color:{DIM}; font-size:10px; letter-spacing:1.5px; "
            f"margin-top:4px;'>MIN SYMBOLS PER DRIVER</div>",
            unsafe_allow_html=True,
        )
        ms_widget = f"{key_prefix}_min_syms"
        _sync_widget(ms_widget, int(st.session_state.get("corr_min_symbols", 1)))
        min_symbols = st.slider(
            "min symbols", 1, MIN_SYMBOLS_MAX,
            step=1,
            label_visibility="collapsed",
            key=ms_widget,
        )
        st.session_state["corr_min_symbols"] = min_symbols
        _confirm_widget_sync(ms_widget, min_symbols)
        hint("skip any driver that shows up on fewer than this many stocks. "
             "raises the bar so single-stock drivers don't pin the matrix at "
             "extreme values just because they share their lone stock.")
    with row2[1]:
        st.markdown(
            f"<div style='color:{DIM}; font-size:10px; letter-spacing:1.5px; "
            f"margin-top:4px;'>{symbol} RANGE  ·  drag handles to filter</div>",
            unsafe_allow_html=True,
        )
        slider_min = 0.0 if metric == "jaccard" else -1.0
        slider_max = 1.0
        canonical = tuple(st.session_state.get("corr_band", (slider_min, slider_max)))
        # clamp into the current metric's range
        canonical = (max(slider_min, canonical[0]), min(slider_max, canonical[1]))
        band_widget = f"{key_prefix}_band_{metric}"
        _sync_widget(band_widget, canonical)
        band = st.slider(
            "score range", slider_min, slider_max,
            step=0.05,
            label_visibility="collapsed",
            key=band_widget,
        )
        st.session_state["corr_band"] = tuple(band)
        _confirm_widget_sync(band_widget, tuple(band))
        hint("drag the handles to hide pairs whose score falls outside this "
             "band. set to the right tail for strong co-movers; to the left "
             "for strong avoiders (φ only — jaccard is never negative).")

    low, high = float(band[0]), float(band[1])
    return metric, min_symbols, low, high


def apply_band(
    corr: pd.DataFrame, low: float, high: float
) -> tuple[pd.DataFrame, int, int]:
    """Mask cells whose score falls outside [low, high]. Drop drivers whose
    only in-band off-diagonal cell is missing.

    Returns (masked_matrix, hidden_drivers, hidden_cells_in_kept_subset).
    """
    if corr.empty:
        return corr, 0, 0
    n = len(corr)
    arr = corr.values
    in_band = (arr >= low) & (arr <= high)
    if in_band.all():
        return corr, 0, 0
    off_diag = in_band.copy()
    np.fill_diagonal(off_diag, False)
    keep = off_diag.any(axis=1)
    hidden_drivers = int(n - keep.sum())
    if keep.sum() < 2:
        return pd.DataFrame(), hidden_drivers, 0
    kept = corr.index[keep]
    sub = corr.loc[kept, kept]
    sub_in = (sub.values >= low) & (sub.values <= high)
    hidden_cells = int((~sub_in).sum())
    masked = sub.where((sub >= low) & (sub <= high))
    return masked, hidden_drivers, hidden_cells


def is_default_corr_filter(metric: str, min_symbols: int,
                            low: float, high: float) -> bool:
    """True iff metric/min_symbols/(low,high) all sit at no-op defaults — i.e.
    every driver in the window would survive. Used by Symbol Detail to skip
    the expensive global corr query when filters wouldn't drop anything."""
    slider_min = 0.0 if metric == "jaccard" else -1.0
    return (min_symbols == 1 and low <= slider_min and high >= 1.0)
