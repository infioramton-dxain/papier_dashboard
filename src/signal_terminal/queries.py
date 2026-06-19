"""PIT-gated queries against PAPIER's sentiment + term tables.

Every public function returns a `pandas.DataFrame` with documented columns so
views can render without re-shaping. Cached via `@st.cache_data` at the view
layer; this module is pure (takes a Path, returns a DataFrame).
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from signal_terminal.db import connect_ro
from signal_terminal.sectors import sector_of
from signal_terminal.style import EVENT_FLAGS


# ---------- term canonicalization ----------
# Thin alias layer to dedupe known variants until PAPIER itself stores
# canonical_term. Hand-extendable — see CLAUDE.md.
_TERM_ALIASES = {
    "price-target-change": "price-target",
    "price-target-raise":  "price-target-raise",
    "price-target-cut":    "price-target-cut",
    "buy-rating-maintenance": "buy-rating",
    "reiteration":         "buy-rating",
    "contract-win":        "contract-award",
    "regulation":          "regulatory",   # too vague → collapse
}


def _canonicalize_term(raw: str) -> str:
    s = raw.strip().lower()
    return _TERM_ALIASES.get(s, s)


# ---------- helpers ----------
def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hours_ago_iso(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s: str) -> datetime:
    """Parse '2026-06-17T23:15:41Z' or any ISO-with-offset string into aware UTC."""
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def _shift_iso(anchor_iso: str, hours: float) -> str:
    """`anchor - hours` formatted as '...Z'."""
    return (_parse_iso(anchor_iso) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _max_published_iso(conn) -> str:
    """Anchor for PIT rolling windows: latest `published_at_max` (status='ok').

    All rolling queries must gate on this anchor instead of wall-clock now so the
    dashboard shows the freshest 24h of *data*, not a void when PAPIER is between
    batches. Mirrors PAPIER's PIT rule (CLAUDE.md). Falls back to wall-clock now
    when the table is empty.
    """
    row = conn.execute(
        "SELECT MAX(published_at_max) FROM sentiment WHERE status='ok'"
    ).fetchone()
    return row[0] if row and row[0] else _now_utc_iso()


def _max_scored_iso(conn) -> str:
    """Anchor for queries gated on `scored_at` (QA + pipeline)."""
    row = conn.execute("SELECT MAX(scored_at) FROM sentiment").fetchone()
    return row[0] if row and row[0] else _now_utc_iso()


def _max_dropped_iso(conn) -> str:
    """Anchor for queries gated on `dropped_articles.seen_at`."""
    row = conn.execute("SELECT MAX(seen_at) FROM dropped_articles").fetchone()
    return row[0] if row and row[0] else _now_utc_iso()


def _add_canonical(df: pd.DataFrame, term_col: str = "term") -> pd.DataFrame:
    df["canonical_term"] = df[term_col].map(_canonicalize_term)
    return df


# ---------- universe / pulse ----------
def universe_latest(db_path: Path, as_of_iso: str | None = None) -> pd.DataFrame:
    """One row per symbol with the latest sentiment row (PIT-gated by as_of).

    Columns: symbol, sector, window_start, window_end, published_at_max, sentiment,
             sentiment_confidence, materiality, geo_risk, article_count, source_count,
             truncated, status, hours_since_published, fresh (bool, < 1h)
             + each event-flag column as int.
    """
    conn = connect_ro(db_path)
    as_of = as_of_iso or _max_published_iso(conn)
    sql = (
        "SELECT s.* FROM sentiment s "
        "JOIN (SELECT symbol, MAX(window_start) ws FROM sentiment "
        "      WHERE published_at_max <= ? GROUP BY symbol) latest "
        "  ON s.symbol = latest.symbol AND s.window_start = latest.ws"
    )
    df = pd.read_sql_query(sql, conn, params=(as_of,))
    conn.close()
    if df.empty:
        return df
    df["sector"] = df["symbol"].map(sector_of)
    pub = pd.to_datetime(df["published_at_max"], utc=True)
    anchor = _parse_iso(as_of)
    df["hours_since_published"] = (anchor - pub).dt.total_seconds() / 3600.0
    df["fresh"] = df["hours_since_published"] < 1.0
    return df


def universe_event_flag_counts(db_path: Path, hours: float = 24.0) -> pd.DataFrame:
    """For each event flag: total fires in last N hours + 'fresh' (< 1h) count.

    Columns: flag, label, count, fresh_count
    """
    from signal_terminal.style import EVENT_LABEL
    conn = connect_ro(db_path)
    anchor = _max_published_iso(conn)
    since = _shift_iso(anchor, hours)
    fresh_since = _shift_iso(anchor, 1.0)
    out_rows = []
    for f in EVENT_FLAGS:
        n = conn.execute(
            f"SELECT COALESCE(SUM({f}), 0) FROM sentiment "
            f"WHERE status='ok' AND published_at_max >= ?",
            (since,),
        ).fetchone()[0]
        n_fresh = conn.execute(
            f"SELECT COALESCE(SUM({f}), 0) FROM sentiment "
            f"WHERE status='ok' AND published_at_max >= ?",
            (fresh_since,),
        ).fetchone()[0]
        out_rows.append({"flag": f, "label": EVENT_LABEL[f], "count": int(n), "fresh_count": int(n_fresh)})
    conn.close()
    return pd.DataFrame(out_rows)


def universe_movers_by_abs(db_path: Path, hours: float = 24.0, limit: int = 10) -> pd.DataFrame:
    """Top |sentiment| in last N hours.

    Columns: symbol, sector, sentiment, materiality, article_count, fresh
    """
    conn = connect_ro(db_path)
    anchor = _max_published_iso(conn)
    since = _shift_iso(anchor, hours)
    sql = (
        "SELECT s.* FROM sentiment s "
        "JOIN (SELECT symbol, MAX(window_start) ws FROM sentiment "
        "      WHERE status='ok' AND published_at_max >= ? GROUP BY symbol) latest "
        "  ON s.symbol = latest.symbol AND s.window_start = latest.ws "
        "ORDER BY ABS(s.sentiment) DESC LIMIT ?"
    )
    df = pd.read_sql_query(sql, conn, params=(since, limit))
    conn.close()
    if df.empty:
        return df
    df["sector"] = df["symbol"].map(sector_of)
    pub = pd.to_datetime(df["published_at_max"], utc=True)
    df["fresh"] = (_parse_iso(anchor) - pub).dt.total_seconds() < 3600
    return df[["symbol", "sector", "sentiment", "materiality", "article_count", "fresh"]]


def universe_movers_by_delta(db_path: Path, hours: float = 24.0, limit: int = 10) -> pd.DataFrame:
    """Top |Δsentiment| comparing latest vs the row from ~24h prior.

    Columns: symbol, sector, sentiment_now, sentiment_prior, delta, abs_delta, fresh
    """
    conn = connect_ro(db_path)
    anchor = _max_published_iso(conn)
    since = _shift_iso(anchor, hours)
    sql_latest = (
        "SELECT s.symbol, s.sentiment AS sentiment_now, s.published_at_max "
        "FROM sentiment s "
        "JOIN (SELECT symbol, MAX(window_start) ws FROM sentiment "
        "      WHERE status='ok' AND published_at_max >= ? GROUP BY symbol) latest "
        "  ON s.symbol = latest.symbol AND s.window_start = latest.ws"
    )
    sql_prior = (
        "SELECT symbol, sentiment AS sentiment_prior FROM sentiment s "
        "WHERE status='ok' AND window_start = ("
        "  SELECT MAX(window_start) FROM sentiment "
        "  WHERE symbol = s.symbol AND status='ok' AND published_at_max < ?)"
    )
    df_now = pd.read_sql_query(sql_latest, conn, params=(since,))
    df_prior = pd.read_sql_query(sql_prior, conn, params=(since,))
    conn.close()
    if df_now.empty:
        return df_now
    df = df_now.merge(df_prior, on="symbol", how="left")
    df["sentiment_prior"] = df["sentiment_prior"].fillna(0.0)
    df["delta"] = df["sentiment_now"] - df["sentiment_prior"]
    df["abs_delta"] = df["delta"].abs()
    df["sector"] = df["symbol"].map(sector_of)
    pub = pd.to_datetime(df["published_at_max"], utc=True)
    df["fresh"] = (_parse_iso(anchor) - pub).dt.total_seconds() < 3600
    df = df.sort_values("abs_delta", ascending=False).head(limit)
    return df[["symbol", "sector", "sentiment_now", "sentiment_prior", "delta", "abs_delta", "fresh"]]


def universe_qa(db_path: Path, hours: float = 24.0) -> dict:
    """QA snapshot for the last N hours.

    Returns: {malformed_json: int, truncated: int, dropped_articles: int}
    """
    conn = connect_ro(db_path)
    scored_anchor = _max_scored_iso(conn)
    dropped_anchor = _max_dropped_iso(conn)
    scored_since = _shift_iso(scored_anchor, hours)
    dropped_since = _shift_iso(dropped_anchor, hours)
    mal = conn.execute(
        "SELECT COUNT(*) FROM sentiment WHERE status='malformed_json' AND scored_at >= ?",
        (scored_since,),
    ).fetchone()[0]
    trunc = conn.execute(
        "SELECT COUNT(*) FROM sentiment WHERE truncated=1 AND scored_at >= ?",
        (scored_since,),
    ).fetchone()[0]
    drop = conn.execute(
        "SELECT COUNT(*) FROM dropped_articles WHERE seen_at >= ?",
        (dropped_since,),
    ).fetchone()[0]
    conn.close()
    return {"malformed_json": int(mal), "truncated": int(trunc), "dropped_articles": int(drop)}


def trending_themes(db_path: Path, hours: float = 24.0, limit: int = 20) -> pd.DataFrame:
    """Theme pills: rank canonical_term by volume × |mean term_sentiment|.

    Columns: canonical_term, n_symbols, n_windows, mean_weight, mean_term_sentiment,
             influence, fresh_count
    """
    conn = connect_ro(db_path)
    anchor = _max_published_iso(conn)
    since = _shift_iso(anchor, hours)
    # Pull (symbol, window_start, term, weight, term_sentiment, published_at_max).
    sql = (
        "SELECT t.symbol, t.window_start, t.term, t.weight, t.term_sentiment, "
        "       s.published_at_max "
        "FROM term t JOIN sentiment s "
        "  ON t.symbol = s.symbol AND t.window_start = s.window_start "
        "WHERE s.status='ok' AND s.published_at_max >= ?"
    )
    df = pd.read_sql_query(sql, conn, params=(since,))
    conn.close()
    if df.empty:
        return pd.DataFrame(
            columns=["canonical_term", "n_symbols", "n_windows", "mean_weight",
                     "mean_term_sentiment", "influence", "fresh_count"]
        )
    df = _add_canonical(df)
    pub = pd.to_datetime(df["published_at_max"], utc=True)
    df["fresh"] = (_parse_iso(anchor) - pub).dt.total_seconds() < 3600
    g = df.groupby("canonical_term").agg(
        n_symbols=("symbol", "nunique"),
        n_windows=("window_start", "count"),
        mean_weight=("weight", "mean"),
        mean_term_sentiment=("term_sentiment", "mean"),
        fresh_count=("fresh", "sum"),
    ).reset_index()
    g["influence"] = g["n_windows"] * g["mean_term_sentiment"].abs() * g["mean_weight"]
    g = g.sort_values("influence", ascending=False).head(limit)
    return g


def driver_symbols(db_path: Path, canonical_term: str, hours: float = 24.0) -> pd.DataFrame:
    """Symbols affected by `canonical_term` in the last N hours, with relevance + context.

    One row per symbol. Columns:
      symbol, sector, weight (max across windows), term_sentiment (mean),
      n_windows_with_term, latest_sentiment, latest_materiality, latest_geo_risk,
      latest_article_count, hours_since_published, fresh
    """
    conn = connect_ro(db_path)
    anchor = _max_published_iso(conn)
    since = _shift_iso(anchor, hours)
    sql = (
        "SELECT t.symbol, t.window_start, t.term, t.weight, t.term_sentiment, "
        "       s.sentiment, s.materiality, s.geo_risk, s.sentiment_confidence, "
        "       s.article_count, s.source_count, s.published_at_max "
        "FROM term t JOIN sentiment s "
        "  ON t.symbol = s.symbol AND t.window_start = s.window_start "
        "WHERE s.status='ok' AND s.published_at_max >= ?"
    )
    df = pd.read_sql_query(sql, conn, params=(since,))
    conn.close()
    cols = [
        "symbol", "sector", "weight", "term_sentiment", "n_windows_with_term",
        "latest_sentiment", "latest_materiality", "latest_geo_risk",
        "latest_article_count", "hours_since_published", "fresh",
    ]
    if df.empty:
        return pd.DataFrame(columns=cols)
    df = _add_canonical(df)
    df = df[df["canonical_term"] == canonical_term].copy()
    if df.empty:
        return pd.DataFrame(columns=cols)
    pub = pd.to_datetime(df["published_at_max"], utc=True)
    df["hours_since_published"] = (_parse_iso(anchor) - pub).dt.total_seconds() / 3600.0
    df = df.sort_values(["symbol", "window_start"])
    g = df.groupby("symbol", as_index=False).agg(
        weight=("weight", "max"),
        term_sentiment=("term_sentiment", "mean"),
        n_windows_with_term=("window_start", "nunique"),
        latest_sentiment=("sentiment", "last"),
        latest_materiality=("materiality", "last"),
        latest_geo_risk=("geo_risk", "last"),
        latest_article_count=("article_count", "last"),
        hours_since_published=("hours_since_published", "min"),
    )
    g["sector"] = g["symbol"].map(sector_of)
    g["fresh"] = g["hours_since_published"] < 1.0
    return g[cols]


def symbols_carrying_drivers(
    db_path: Path, hours: float = 24.0, canonical_terms: list[str] | None = None
) -> pd.DataFrame:
    """Per-symbol summary across a SET of drivers (e.g. the surviving drivers
    after the correlation filters narrow the heatmap).

    Columns:
      symbol, sector, n_drivers, top_drivers, mean_weight, mean_term_sentiment,
      latest_sentiment, latest_materiality, latest_geo_risk,
      latest_article_count, hours_since_published, fresh
    """
    cols = [
        "symbol", "sector", "n_drivers", "top_drivers",
        "mean_weight", "mean_term_sentiment",
        "latest_sentiment", "latest_materiality", "latest_geo_risk",
        "latest_article_count", "hours_since_published", "fresh",
    ]
    if not canonical_terms:
        return pd.DataFrame(columns=cols)
    conn = connect_ro(db_path)
    anchor = _max_published_iso(conn)
    since = _shift_iso(anchor, hours)
    sql = (
        "SELECT t.symbol, t.window_start, t.term, t.weight, t.term_sentiment, "
        "       s.sentiment, s.materiality, s.geo_risk, "
        "       s.article_count, s.published_at_max "
        "FROM term t JOIN sentiment s "
        "  ON t.symbol = s.symbol AND t.window_start = s.window_start "
        "WHERE s.status='ok' AND s.published_at_max >= ?"
    )
    df = pd.read_sql_query(sql, conn, params=(since,))
    conn.close()
    if df.empty:
        return pd.DataFrame(columns=cols)
    df = _add_canonical(df)
    term_set = set(canonical_terms)
    df = df[df["canonical_term"].isin(term_set)].copy()
    if df.empty:
        return pd.DataFrame(columns=cols)
    pub = pd.to_datetime(df["published_at_max"], utc=True)
    df["hours_since_published"] = (
        _parse_iso(anchor) - pub
    ).dt.total_seconds() / 3600.0
    df = df.sort_values(["symbol", "window_start"])

    def _top3(g: pd.DataFrame) -> str:
        # Top 3 canonical_terms for this symbol by their max weight.
        top = (g.groupby("canonical_term")["weight"].max()
                 .sort_values(ascending=False).head(3).index.tolist())
        return ", ".join(top)

    agg = df.groupby("symbol", as_index=False).agg(
        n_drivers=("canonical_term", "nunique"),
        mean_weight=("weight", "mean"),
        mean_term_sentiment=("term_sentiment", "mean"),
        latest_sentiment=("sentiment", "last"),
        latest_materiality=("materiality", "last"),
        latest_geo_risk=("geo_risk", "last"),
        latest_article_count=("article_count", "last"),
        hours_since_published=("hours_since_published", "min"),
    )
    top_df = (df.groupby("symbol")
                .apply(_top3, include_groups=False)
                .reset_index(name="top_drivers"))
    agg = agg.merge(top_df, on="symbol")
    agg["sector"] = agg["symbol"].map(sector_of)
    agg["fresh"] = agg["hours_since_published"] < 1.0
    return (agg[cols]
            .sort_values(["n_drivers", "mean_weight"], ascending=[False, False])
            .reset_index(drop=True))


def driver_correlation_matrix(db_path: Path, hours: float = 24.0, limit: int = 12,
                               metric: str = "phi", min_symbols: int = 1) -> pd.DataFrame:
    """Pairwise driver association across symbol presence.

    metric:
      - "phi"     → Pearson on binary indicator, range [-1, +1]. Picks up both
                    positive (co-occur) and negative (anti-occur) structure.
      - "jaccard" → |A ∩ B| / |A ∪ B|, range [0, 1]. Pure overlap; ignores the
                    "both absent" cell that drives φ→1 for sparse drivers.

    min_symbols: drop any driver that appears on fewer than this many symbols
    before building the matrix. Useful for cleaning trivial φ=1 noise from
    single-symbol drivers that happen to share their lone carrier.

    Returns a square DataFrame indexed + columned by `canonical_term`, capped
    at `limit` drivers, ordered by symbol-count desc. Diagonal is 1.0.
    """
    import numpy as np

    conn = connect_ro(db_path)
    anchor = _max_published_iso(conn)
    since = _shift_iso(anchor, hours)
    sql = (
        "SELECT DISTINCT t.symbol, t.term FROM term t "
        "JOIN sentiment s ON t.symbol = s.symbol AND t.window_start = s.window_start "
        "WHERE s.status='ok' AND s.published_at_max >= ?"
    )
    df = pd.read_sql_query(sql, conn, params=(since,))
    conn.close()
    if df.empty:
        return pd.DataFrame()
    df = _add_canonical(df)
    pivot = (
        df.drop_duplicates(["symbol", "canonical_term"])
          .assign(present=1)
          .pivot_table(index="symbol", columns="canonical_term",
                       values="present", fill_value=0)
    )
    if pivot.empty:
        return pd.DataFrame()

    # Apply min_symbols before ranking & limiting.
    col_counts = pivot.sum(axis=0)
    keep = col_counts[col_counts >= int(min_symbols)].index
    pivot = pivot[keep]
    if pivot.shape[1] < 2:
        return pd.DataFrame()

    rank = pivot.sum(axis=0).sort_values(ascending=False).head(limit).index
    sub = pivot[rank].astype(float)

    if metric == "jaccard":
        arr = sub.values
        inter = arr.T @ arr
        col_sums = arr.sum(axis=0)
        union = col_sums[:, None] + col_sums[None, :] - inter
        with np.errstate(divide="ignore", invalid="ignore"):
            jacc = np.divide(inter, union,
                              out=np.zeros_like(inter, dtype=float),
                              where=union > 0)
        return pd.DataFrame(jacc, index=rank, columns=rank)

    # default — phi (Pearson on binary)
    return sub.corr().fillna(0.0).loc[rank, rank]


def symbols_for_theme(db_path: Path, canonical_term: str, hours: float = 24.0) -> list[str]:
    """Symbols whose latest window carries a term mapping to canonical_term."""
    conn = connect_ro(db_path)
    anchor = _max_published_iso(conn)
    since = _shift_iso(anchor, hours)
    sql = (
        "SELECT DISTINCT t.symbol, t.term FROM term t "
        "JOIN sentiment s ON t.symbol = s.symbol AND t.window_start = s.window_start "
        "WHERE s.status='ok' AND s.published_at_max >= ?"
    )
    df = pd.read_sql_query(sql, conn, params=(since,))
    conn.close()
    if df.empty:
        return []
    df = _add_canonical(df)
    return sorted(df.loc[df["canonical_term"] == canonical_term, "symbol"].unique().tolist())


# ---------- symbol detail ----------
def symbol_history(db_path: Path, symbol: str, days: int = 180) -> pd.DataFrame:
    """Time series for a symbol over trailing N days.

    Columns: all sentiment columns + flag columns + window_start (datetime).
    """
    conn = connect_ro(db_path)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    df = pd.read_sql_query(
        "SELECT * FROM sentiment WHERE symbol=? AND published_at_max >= ? "
        "ORDER BY window_start ASC",
        conn, params=(symbol, since),
    )
    conn.close()
    if df.empty:
        return df
    df["window_start_dt"] = pd.to_datetime(df["window_start"], utc=True)
    return df


def symbol_drivers_window(db_path: Path, symbol: str, hours: float = 24.0) -> pd.DataFrame:
    """Drivers carried by `symbol` across the last `hours` of data, aggregated
    one row per canonical_term.

    Matches the time horizon used by Driver Detail / Driver Correlation so the
    cross-tab story stays consistent. Mirrors PAPIER's PIT rule via the
    `published_at_max` anchor.

    Columns:
      canonical_term, n_windows, max_weight, mean_weight, mean_term_sentiment,
      first_window_start, last_window_start, hours_since_last_window
    """
    cols = [
        "canonical_term", "n_windows", "max_weight", "mean_weight",
        "mean_term_sentiment",
        "first_window_start", "last_window_start", "hours_since_last_window",
    ]
    conn = connect_ro(db_path)
    anchor = _max_published_iso(conn)
    since = _shift_iso(anchor, hours)
    sql = (
        "SELECT t.symbol, t.window_start, t.term, t.weight, t.term_sentiment "
        "FROM term t JOIN sentiment s "
        "  ON t.symbol = s.symbol AND t.window_start = s.window_start "
        "WHERE t.symbol = ? AND s.status='ok' AND s.published_at_max >= ?"
    )
    df = pd.read_sql_query(sql, conn, params=(symbol, since))
    conn.close()
    if df.empty:
        return pd.DataFrame(columns=cols)
    df = _add_canonical(df)
    g = df.groupby("canonical_term", as_index=False).agg(
        n_windows=("window_start", "nunique"),
        max_weight=("weight", "max"),
        mean_weight=("weight", "mean"),
        mean_term_sentiment=("term_sentiment", "mean"),
        first_window_start=("window_start", "min"),
        last_window_start=("window_start", "max"),
    )
    anchor_dt = _parse_iso(anchor)
    last = pd.to_datetime(g["last_window_start"], utc=True)
    g["hours_since_last_window"] = (anchor_dt - last).dt.total_seconds() / 3600.0
    return (g[cols]
            .sort_values(["max_weight", "n_windows"], ascending=[False, False])
            .reset_index(drop=True))


def symbol_drivers(db_path: Path, symbol: str, window_start: str) -> pd.DataFrame:
    """Terms for the (symbol, window_start). Columns: canonical_term, term, weight, term_sentiment."""
    conn = connect_ro(db_path)
    df = pd.read_sql_query(
        "SELECT term, weight, term_sentiment FROM term "
        "WHERE symbol=? AND window_start=? ORDER BY weight DESC",
        conn, params=(symbol, window_start),
    )
    conn.close()
    if df.empty:
        return df
    df = _add_canonical(df)
    return df


# ---------- sector lens ----------
def sector_aggregates(db_path: Path, hours: float = 24.0) -> pd.DataFrame:
    """Aggregate per sector for the last N hours.

    Columns: sector, n_symbols, mean_sentiment, mean_materiality, mean_geo_risk
    """
    df = universe_latest(db_path)
    if df.empty:
        return pd.DataFrame(
            columns=["sector", "n_symbols", "mean_sentiment", "mean_materiality", "mean_geo_risk"]
        )
    g = df.groupby("sector").agg(
        n_symbols=("symbol", "nunique"),
        mean_sentiment=("sentiment", "mean"),
        mean_materiality=("materiality", "mean"),
        mean_geo_risk=("geo_risk", "mean"),
    ).reset_index()
    return g


def sector_history(db_path: Path, metric: str = "sentiment", days: int = 180) -> pd.DataFrame:
    """Per-sector mean of a metric per UTC day for trailing N days.

    Columns: day (datetime), sector, value
    """
    if metric not in ("sentiment", "materiality", "geo_risk"):
        raise ValueError(f"unknown metric: {metric}")
    conn = connect_ro(db_path)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    df = pd.read_sql_query(
        f"SELECT symbol, window_start, {metric} AS value FROM sentiment "
        "WHERE status='ok' AND published_at_max >= ?",
        conn, params=(since,),
    )
    conn.close()
    if df.empty:
        return pd.DataFrame(columns=["day", "sector", "value"])
    df["sector"] = df["symbol"].map(sector_of)
    df["day"] = pd.to_datetime(df["window_start"], utc=True).dt.floor("D")
    g = df.groupby(["day", "sector"]).agg(value=("value", "mean")).reset_index()
    return g


# ---------- pipeline health ----------
def pipeline_runs(db_path: Path, limit: int = 30) -> pd.DataFrame:
    """Most recent N runs. Columns: run_id, command, started_at, ended_at, rows_written, errors, notes."""
    conn = connect_ro(db_path)
    df = pd.read_sql_query(
        "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", conn, params=(limit,),
    )
    conn.close()
    if not df.empty:
        df["started_dt"] = pd.to_datetime(df["started_at"], utc=True)
        ended = pd.to_datetime(df["ended_at"], utc=True, errors="coerce")
        df["duration_min"] = ((ended - df["started_dt"]).dt.total_seconds() / 60.0).round(1)
        df["status"] = df.apply(
            lambda r: "failed" if r["errors"] and r["errors"] > (r["rows_written"] or 0) * 0.1
            else ("degraded" if r["errors"] else "ok"),
            axis=1,
        )
    return df


def pipeline_dropped_by_reason_trend(db_path: Path, days: int = 60) -> pd.DataFrame:
    """Daily count of dropped_articles by reason for trailing N days.

    Columns: day (datetime), reason, count
    """
    conn = connect_ro(db_path)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    df = pd.read_sql_query(
        "SELECT seen_at, reason FROM dropped_articles WHERE seen_at >= ?",
        conn, params=(since,),
    )
    conn.close()
    if df.empty:
        return pd.DataFrame(columns=["day", "reason", "count"])
    df["day"] = pd.to_datetime(df["seen_at"], utc=True).dt.floor("D")
    g = df.groupby(["day", "reason"]).size().reset_index(name="count")
    return g


def pipeline_trend_lines(db_path: Path, days: int = 60) -> pd.DataFrame:
    """Daily count of malformed_json + truncated rows.

    Columns: day, malformed_json, truncated
    """
    conn = connect_ro(db_path)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    df = pd.read_sql_query(
        "SELECT scored_at, status, truncated FROM sentiment WHERE scored_at >= ?",
        conn, params=(since,),
    )
    conn.close()
    if df.empty:
        return pd.DataFrame(columns=["day", "malformed_json", "truncated"])
    df["day"] = pd.to_datetime(df["scored_at"], utc=True).dt.floor("D")
    g = df.groupby("day").agg(
        malformed_json=("status", lambda s: (s == "malformed_json").sum()),
        truncated=("truncated", "sum"),
    ).reset_index()
    return g
