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
    as_of = as_of_iso or _now_utc_iso()
    conn = connect_ro(db_path)
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
    now = datetime.now(timezone.utc)
    df["hours_since_published"] = (now - pub).dt.total_seconds() / 3600.0
    df["fresh"] = df["hours_since_published"] < 1.0
    return df


def universe_event_flag_counts(db_path: Path, hours: float = 24.0) -> pd.DataFrame:
    """For each event flag: total fires in last N hours + 'fresh' (< 1h) count.

    Columns: flag, label, count, fresh_count
    """
    from signal_terminal.style import EVENT_LABEL
    conn = connect_ro(db_path)
    since = _hours_ago_iso(hours)
    fresh_since = _hours_ago_iso(1.0)
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
    since = _hours_ago_iso(hours)
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
    df["fresh"] = (datetime.now(timezone.utc) - pub).dt.total_seconds() < 3600
    return df[["symbol", "sector", "sentiment", "materiality", "article_count", "fresh"]]


def universe_movers_by_delta(db_path: Path, hours: float = 24.0, limit: int = 10) -> pd.DataFrame:
    """Top |Δsentiment| comparing latest vs the row from ~24h prior.

    Columns: symbol, sector, sentiment_now, sentiment_prior, delta, abs_delta, fresh
    """
    conn = connect_ro(db_path)
    since = _hours_ago_iso(hours)
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
    cur_since = _hours_ago_iso(hours)
    df_now = pd.read_sql_query(sql_latest, conn, params=(since,))
    df_prior = pd.read_sql_query(sql_prior, conn, params=(cur_since,))
    conn.close()
    if df_now.empty:
        return df_now
    df = df_now.merge(df_prior, on="symbol", how="left")
    df["sentiment_prior"] = df["sentiment_prior"].fillna(0.0)
    df["delta"] = df["sentiment_now"] - df["sentiment_prior"]
    df["abs_delta"] = df["delta"].abs()
    df["sector"] = df["symbol"].map(sector_of)
    pub = pd.to_datetime(df["published_at_max"], utc=True)
    df["fresh"] = (datetime.now(timezone.utc) - pub).dt.total_seconds() < 3600
    df = df.sort_values("abs_delta", ascending=False).head(limit)
    return df[["symbol", "sector", "sentiment_now", "sentiment_prior", "delta", "abs_delta", "fresh"]]


def universe_qa(db_path: Path, hours: float = 24.0) -> dict:
    """QA snapshot for the last N hours.

    Returns: {malformed_json: int, truncated: int, dropped_articles: int}
    """
    conn = connect_ro(db_path)
    since = _hours_ago_iso(hours)
    mal = conn.execute(
        "SELECT COUNT(*) FROM sentiment WHERE status='malformed_json' AND scored_at >= ?",
        (since,),
    ).fetchone()[0]
    trunc = conn.execute(
        "SELECT COUNT(*) FROM sentiment WHERE truncated=1 AND scored_at >= ?",
        (since,),
    ).fetchone()[0]
    drop = conn.execute(
        "SELECT COUNT(*) FROM dropped_articles WHERE seen_at >= ?",
        (since,),
    ).fetchone()[0]
    conn.close()
    return {"malformed_json": int(mal), "truncated": int(trunc), "dropped_articles": int(drop)}


def trending_themes(db_path: Path, hours: float = 24.0, limit: int = 20) -> pd.DataFrame:
    """Theme pills: rank canonical_term by volume × |mean term_sentiment|.

    Columns: canonical_term, n_symbols, n_windows, mean_weight, mean_term_sentiment,
             influence, fresh_count
    """
    conn = connect_ro(db_path)
    since = _hours_ago_iso(hours)
    fresh_since = _hours_ago_iso(1.0)
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
    df["fresh"] = (datetime.now(timezone.utc) - pub).dt.total_seconds() < 3600
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


def symbols_for_theme(db_path: Path, canonical_term: str, hours: float = 24.0) -> list[str]:
    """Symbols whose latest window carries a term mapping to canonical_term."""
    conn = connect_ro(db_path)
    since = _hours_ago_iso(hours)
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
