"""Event-flag analytics: pairwise co-occurrence, firing rates over time,
firing rates per symbol.

Pure functions of the long-format sentiment frame from data.load_sentiment().
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from signal_terminal.style import EVENT_FLAGS


def flag_cooccurrence(df: pd.DataFrame) -> pd.DataFrame:
    """7×7 matrix.

    Diagonal: raw firing count per flag (number of rows where flag=1).
    Off-diagonal: |A ∩ B| / min(|A|, |B|) — a min-Jaccard score. We use min
    rather than union so a frequently-firing flag doesn't suppress its
    co-occurrence with a rarer flag.
    """
    cols = [c for c in EVENT_FLAGS if c in df.columns]
    if df.empty or not cols:
        return pd.DataFrame(0, index=list(EVENT_FLAGS), columns=list(EVENT_FLAGS), dtype=float)

    flags = df[cols].fillna(0).astype(int).clip(0, 1)
    arr = flags.values  # (n_rows, n_flags)
    counts = arr.sum(axis=0)                  # (n_flags,)
    inter = arr.T @ arr                       # (n_flags, n_flags) co-firing counts
    # avoid div-by-zero — if a flag never fires, its row/col stays 0
    min_pair = np.minimum.outer(counts, counts).astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        score = np.divide(inter, min_pair,
                          out=np.zeros_like(inter, dtype=float),
                          where=min_pair > 0)
    # put raw counts on the diagonal so users see absolute firing volume
    for i in range(len(cols)):
        score[i, i] = float(counts[i])
    return pd.DataFrame(score, index=cols, columns=cols)


def firing_rates_over_time(df: pd.DataFrame, *, freq: str = "ME") -> pd.DataFrame:
    """Share of rows in each period where each flag fires.

    `freq` is a pandas offset alias: 'D', 'W', 'ME' (month-end), etc. Defaults
    to month-end since the spec asks for monthly bins on Tab 3.
    """
    cols = [c for c in EVENT_FLAGS if c in df.columns]
    if df.empty or not cols or "window_start_dt" not in df.columns:
        return pd.DataFrame(columns=cols)
    flags = df[cols].fillna(0).astype(int).clip(0, 1)
    # to_period drops the tz; strip it explicitly first to silence pandas.
    naive_ws = df["window_start_dt"].dt.tz_convert("UTC").dt.tz_localize(None)
    flags = flags.assign(_period=naive_ws.dt.to_period(_period_code(freq)))
    g = flags.groupby("_period")[cols].mean()
    g.index = g.index.to_timestamp()
    g.index.name = "period"
    return g


def _period_code(freq: str) -> str:
    """Map a pandas offset alias to a Period frequency code.

    pandas-2.2 deprecates 'M' in offset aliases ('ME' is the replacement) but
    PeriodIndex still uses 'M'. Normalize here.
    """
    return {"ME": "M", "MS": "M", "QE": "Q", "QS": "Q", "YE": "Y", "YS": "Y"}.get(freq, freq)


def firing_rates_per_symbol(df: pd.DataFrame) -> pd.DataFrame:
    """One row per symbol: n_windows + firing rate per flag.

    Columns: symbol, n_windows, <flag>_rate for each flag in EVENT_FLAGS.
    """
    flag_cols = [c for c in EVENT_FLAGS if c in df.columns]
    out_cols = ["symbol", "n_windows", *[f"{f}_rate" for f in flag_cols]]
    if df.empty or not flag_cols:
        return pd.DataFrame(columns=out_cols)

    agg = {"n_windows": ("window_start", "count")}
    for f in flag_cols:
        agg[f"{f}_rate"] = (f, "mean")
    g = df.groupby("symbol", as_index=False).agg(**agg)
    return g[out_cols].sort_values("symbol").reset_index(drop=True)
