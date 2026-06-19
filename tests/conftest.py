"""Test fixtures: build a tiny papier.db on disk for analytics loaders to read.

Analytics loaders open SQLite with file URI mode=ro, so the fixture writes to
a temp file and yields its path. Schema mirrors what production code reads
(sentiment + dropped_articles + runs) — only the columns we actually query.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from signal_terminal.style import EVENT_FLAGS

_SCHEMA = """
CREATE TABLE sentiment (
    symbol TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT,
    published_at_max TEXT,
    scored_at TEXT,
    score_source TEXT,
    article_count INTEGER DEFAULT 1,
    source_count INTEGER DEFAULT 1,
    truncated INTEGER DEFAULT 0,
    status TEXT DEFAULT 'ok',
    sentiment REAL,
    sentiment_confidence REAL,
    materiality REAL,
    geo_risk REAL,
    {flag_columns},
    PRIMARY KEY (symbol, window_start)
);
""".format(flag_columns=",\n    ".join(f"{f} INTEGER DEFAULT 0" for f in EVENT_FLAGS))


@pytest.fixture
def empty_db(tmp_path: Path) -> Path:
    """Fresh papier.db with the sentiment schema but no rows."""
    db = tmp_path / "papier.db"
    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()
    return db
