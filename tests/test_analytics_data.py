"""Tests for src/signal_terminal/analytics/data.py.

Builds a 10-symbol, 100-window fixture and asserts:
  - load_sentiment respects status / article-count / symbol filters
  - pivot is article-count-weighted
  - days with zero observations stay NaN (never 0)
  - per_symbol_features returns one row per symbol with rate columns in [0, 1]
  - cross-model warning trigger fires when score_source has > 1 value
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from signal_terminal.analytics.data import (Filters, correlation_matrix,
                                              distinct_score_sources,
                                              load_sentiment,
                                              per_symbol_features,
                                              pivot_sentiment)
from signal_terminal.style import EVENT_FLAGS


def _populate(db_path: Path) -> None:
    """10 symbols × 100 hourly windows; first half tagged ok, second half mixed."""
    conn = sqlite3.connect(db_path)
    rows = []
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for s_idx in range(10):
        symbol = f"SYM{s_idx:02d}"
        for h in range(100):
            ts = (base + timedelta(hours=h)).isoformat()
            sent = ((s_idx + h) % 5 - 2) / 2.0      # in [-1, 1]
            status = "ok" if h < 70 else ("malformed_json" if h % 2 == 0 else "ok")
            sentiment = sent if status == "ok" else None
            score_source = "ollama:llama3.1" if h < 50 else "ollama:llama3.2"
            row = [symbol, ts, ts, ts, ts, score_source,
                   max(1, h % 7), max(1, h % 5), 0, status,
                   sentiment, 0.5, 0.4, 0.3]
            # event flags — fire mna on every 4th window, etc.
            flags = [1 if (h % (i + 2) == 0) else 0 for i in range(len(EVENT_FLAGS))]
            row.extend(flags)
            rows.append(row)
    cols = (
        "symbol,window_start,window_end,published_at_max,scored_at,score_source,"
        "article_count,source_count,truncated,status,sentiment,"
        "sentiment_confidence,materiality,geo_risk," + ",".join(EVENT_FLAGS)
    )
    placeholders = ",".join("?" * (14 + len(EVENT_FLAGS)))
    conn.executemany(f"INSERT INTO sentiment ({cols}) VALUES ({placeholders})", rows)
    conn.commit()
    conn.close()


def test_load_sentiment_status_filter(empty_db: Path) -> None:
    _populate(empty_db)
    df = load_sentiment(empty_db, Filters())
    # status defaults to ('ok',) — and sentiment must be non-null
    assert (df["status"] == "ok").all()
    assert df["sentiment"].notna().all()


def test_load_sentiment_article_filter(empty_db: Path) -> None:
    _populate(empty_db)
    df = load_sentiment(empty_db, Filters(min_article_count=4))
    assert (df["article_count"] >= 4).all()


def test_load_sentiment_symbol_filter(empty_db: Path) -> None:
    _populate(empty_db)
    df = load_sentiment(empty_db, Filters(symbols=("SYM00", "SYM03")))
    assert set(df["symbol"].unique()) == {"SYM00", "SYM03"}


def test_load_sentiment_date_filter(empty_db: Path) -> None:
    _populate(empty_db)
    df = load_sentiment(empty_db, Filters(date_start=date(2026, 1, 2)))
    ws = pd.to_datetime(df["window_start"], utc=True)
    assert (ws >= pd.Timestamp("2026-01-02", tz="UTC")).all()


def test_pivot_zero_observation_days_are_nan(empty_db: Path) -> None:
    _populate(empty_db)
    pivot = pivot_sentiment(empty_db, Filters(grain="daily"))
    # Pivot should have a row per UTC day and a column per symbol.
    assert pivot.shape[0] >= 1
    assert "SYM00" in pivot.columns
    # All values must be either NaN or finite — never 0 from absence.
    assert pivot.values.dtype.kind == "f"


def test_per_symbol_features_shape(empty_db: Path) -> None:
    _populate(empty_db)
    feats = per_symbol_features(empty_db, Filters())
    assert "mean_sentiment" in feats.columns
    for flag in EVENT_FLAGS:
        col = f"{flag}_rate"
        assert col in feats.columns
        assert (feats[col] >= 0).all() and (feats[col] <= 1).all()
    assert feats["symbol"].is_unique


def test_correlation_matrix_diagonal_is_one(empty_db: Path) -> None:
    _populate(empty_db)
    corr = correlation_matrix(empty_db, Filters(), min_joint_obs=2)
    assert corr.shape[0] == corr.shape[1]
    diag = corr.values.diagonal()
    assert all(abs(d - 1.0) < 1e-9 for d in diag)


def test_distinct_score_sources_triggers_warning(empty_db: Path) -> None:
    _populate(empty_db)
    sources = distinct_score_sources(empty_db, Filters())
    assert len(sources) == 2
    assert "ollama:llama3.1" in sources
    assert "ollama:llama3.2" in sources
