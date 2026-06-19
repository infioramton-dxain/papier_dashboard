"""Filters dataclass + DB → DataFrame loaders for the analytics tabs.

All functions read PAPIER's sentiment table read-only (uri mode=ro). PIT
discipline: time anchors are `window_start` and `published_at_max`; `scored_at`
is audit-only and never enters a feature, filter, or aggregation key.

Flagged / null-sentiment rows are excluded upfront (status='ok' AND
sentiment IS NOT NULL) so downstream factor / clustering / event code never
sees them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from signal_terminal.db import connect_ro
from signal_terminal.sectors import sector_of
from signal_terminal.style import EVENT_FLAGS

Grain = Literal["hourly", "daily", "weekly"]


@dataclass(frozen=True)
class Filters:
    """Global filter set — used as the cache key by every analytics loader.

    Tuple (not list/set) so the dataclass stays hashable for @st.cache_data.
    `None` means "no filter on this axis" — e.g. symbols=None means full
    universe.
    """
    date_start: date | None = None
    date_end:   date | None = None
    symbols:    tuple[str, ...] | None = None
    sectors:    tuple[str, ...] | None = None
    min_article_count: int = 1
    grain: Grain = "daily"
    status: tuple[str, ...] = ("ok",)


# --------------------------------------------------------------------------- #
# core loader
# --------------------------------------------------------------------------- #
_SENTIMENT_COLUMNS = (
    "symbol", "window_start", "window_end", "published_at_max",
    "score_source",
    "article_count", "source_count", "truncated", "status",
    "sentiment", "sentiment_confidence", "materiality", "geo_risk",
    *EVENT_FLAGS,
)

def load_sentiment(db_path: str | Path, filters: Filters) -> pd.DataFrame:
    """Long-format sentiment frame, status/article/symbol/sector/date-filtered.

    Returns columns from `_SENTIMENT_COLUMNS` plus `sector` and a `window_start_dt`
    pandas Timestamp (UTC). `scored_at` is intentionally NOT exposed.
    """
    conn = connect_ro(db_path)
    cols = ", ".join(_SENTIMENT_COLUMNS)
    where = ["sentiment IS NOT NULL"]
    params: list = []
    if filters.status:
        where.append("status IN (" + ",".join("?" * len(filters.status)) + ")")
        params.extend(filters.status)
    if filters.min_article_count and filters.min_article_count > 1:
        where.append("article_count >= ?")
        params.append(int(filters.min_article_count))
    if filters.date_start is not None:
        where.append("window_start >= ?")
        params.append(filters.date_start.isoformat())
    if filters.date_end is not None:
        # inclusive — extend to end-of-day
        where.append("window_start < ?")
        params.append((pd.Timestamp(filters.date_end) + pd.Timedelta(days=1)).date().isoformat())
    if filters.symbols:
        where.append("symbol IN (" + ",".join("?" * len(filters.symbols)) + ")")
        params.extend(filters.symbols)
    sql = f"SELECT {cols} FROM sentiment WHERE " + " AND ".join(where)
    df = pd.read_sql_query(sql, conn, params=params)
    conn.close()
    if df.empty:
        return df
    df["sector"] = df["symbol"].map(sector_of)
    if filters.sectors:
        df = df[df["sector"].isin(filters.sectors)].copy()
    df["window_start_dt"] = pd.to_datetime(df["window_start"], utc=True)
    return df


# --------------------------------------------------------------------------- #
# pivot / resample
# --------------------------------------------------------------------------- #
def _grain_freq(grain: Grain) -> str:
    return {"hourly": "h", "daily": "D", "weekly": "W"}[grain]


def pivot_sentiment(db_path: str | Path, filters: Filters) -> pd.DataFrame:
    """Time × symbol matrix of mean sentiment at the requested grain.

    Daily grain rule (per spec §8): each cell is the article-count-weighted
    mean of all underlying windows. Empty cells stay NaN — never zero.
    """
    df = load_sentiment(db_path, filters)
    if df.empty:
        return pd.DataFrame()

    freq = _grain_freq(filters.grain)
    df = df.dropna(subset=["sentiment"]).copy()
    df["period"] = df["window_start_dt"].dt.floor(freq)
    # article-count-weighted mean per (period, symbol)
    df["w"] = df["article_count"].clip(lower=1).astype(float)
    df["sw"] = df["sentiment"] * df["w"]
    g = df.groupby(["period", "symbol"], as_index=False).agg(
        sw=("sw", "sum"), w=("w", "sum")
    )
    g["sentiment"] = g["sw"] / g["w"]
    pivot = g.pivot(index="period", columns="symbol", values="sentiment").sort_index()
    pivot.index.name = "period"
    pivot.columns.name = "symbol"
    return pivot


# --------------------------------------------------------------------------- #
# per-symbol features (input to NMF + k-means)
# --------------------------------------------------------------------------- #
def per_symbol_features(db_path: str | Path, filters: Filters) -> pd.DataFrame:
    """One row per symbol — mean/std sentiment, mean materiality / geo_risk,
    firing rate of each event flag, total article count + distinct source count.

    Columns:
      symbol, sector, n_windows, total_articles, distinct_sources,
      mean_sentiment, std_sentiment, abs_mean_sentiment,
      mean_materiality, mean_geo_risk,
      <flag>_rate for each flag in EVENT_FLAGS.
    """
    df = load_sentiment(db_path, filters)
    cols = [
        "symbol", "sector", "n_windows", "total_articles", "distinct_sources",
        "mean_sentiment", "std_sentiment", "abs_mean_sentiment",
        "mean_materiality", "mean_geo_risk",
        *[f"{f}_rate" for f in EVENT_FLAGS],
    ]
    if df.empty:
        return pd.DataFrame(columns=cols)
    agg_map = {
        "n_windows":         ("window_start", "count"),
        "total_articles":    ("article_count", "sum"),
        "distinct_sources":  ("source_count", "sum"),
        "mean_sentiment":    ("sentiment", "mean"),
        "std_sentiment":     ("sentiment", "std"),
        "mean_materiality":  ("materiality", "mean"),
        "mean_geo_risk":     ("geo_risk", "mean"),
    }
    for f in EVENT_FLAGS:
        agg_map[f"{f}_rate"] = (f, "mean")
    g = df.groupby("symbol", as_index=False).agg(**agg_map)
    g["abs_mean_sentiment"] = g["mean_sentiment"].abs()
    g["std_sentiment"] = g["std_sentiment"].fillna(0.0)
    g["sector"] = g["symbol"].map(sector_of)
    return g[cols]


# --------------------------------------------------------------------------- #
# correlation
# --------------------------------------------------------------------------- #
def correlation_matrix(
    db_path: str | Path, filters: Filters, *, min_joint_obs: int = 20
) -> pd.DataFrame:
    """Spearman correlation across symbols on the time × symbol pivot.

    Pairwise observations only. Symbol pairs with fewer than `min_joint_obs`
    overlapping non-NaN periods are masked to NaN — those correlations are
    statistically meaningless and would otherwise dominate the dendrogram.
    """
    pivot = pivot_sentiment(db_path, filters)
    if pivot.empty or pivot.shape[1] < 2:
        return pd.DataFrame()
    # joint counts: notnull mask co-presence
    mask = pivot.notna().astype(int)
    joint = mask.T @ mask  # symbols × symbols joint-obs matrix
    corr = pivot.corr(method="spearman", min_periods=min_joint_obs)
    # mask cells with too few joint obs (corr.corr already returns NaN for
    # those, but be explicit so downstream code is unsurprised)
    corr = corr.where(joint.reindex_like(corr) >= min_joint_obs)
    # Ensure the diagonal is exactly 1.0 (corr() returns NaN on all-NaN rows).
    arr = np.array(corr.values, dtype=float, copy=True)
    np.fill_diagonal(arr, 1.0)
    return pd.DataFrame(arr, index=corr.index, columns=corr.columns)


# --------------------------------------------------------------------------- #
# misc helpers used by views (kept here to share the cache key)
# --------------------------------------------------------------------------- #
def universe_symbols(db_path: str | Path) -> list[str]:
    """Sorted list of all symbols with at least one ok / non-null row."""
    conn = connect_ro(db_path)
    df = pd.read_sql_query(
        "SELECT DISTINCT symbol FROM sentiment "
        "WHERE status='ok' AND sentiment IS NOT NULL ORDER BY symbol",
        conn,
    )
    conn.close()
    return df["symbol"].tolist()


def coverage_bounds(db_path: str | Path) -> tuple[date | None, date | None]:
    """(min window_start, max window_start) as UTC dates — defaults for the
    date-range sidebar widget."""
    conn = connect_ro(db_path)
    row = conn.execute(
        "SELECT MIN(window_start), MAX(window_start) FROM sentiment "
        "WHERE status='ok' AND sentiment IS NOT NULL"
    ).fetchone()
    conn.close()
    if not row or row[0] is None:
        return None, None
    lo = pd.Timestamp(row[0]).date()
    hi = pd.Timestamp(row[1]).date()
    return lo, hi


def distinct_score_sources(db_path: str | Path, filters: Filters) -> list[str]:
    """Distinct `score_source` values present in the filtered window — used to
    raise the cross-model warning banner."""
    df = load_sentiment(db_path, filters)
    if df.empty or "score_source" not in df.columns:
        return []
    return sorted(s for s in df["score_source"].dropna().unique().tolist() if s)
