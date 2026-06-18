"""Read-only SQLite connection to PAPIER's papier.db.

Opens with `mode=ro` URI flag so any accidental write attempt is a hard error.
"""
import sqlite3
from pathlib import Path


def connect_ro(db_path: str | Path) -> sqlite3.Connection:
    p = Path(db_path)
    if not p.exists():
        raise FileNotFoundError(f"papier.db not found at {p}")
    # uri=True is required to honor mode=ro
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def db_has_data(db_path: str | Path) -> bool:
    """True if papier.db exists and has at least one sentiment row."""
    p = Path(db_path)
    if not p.exists():
        return False
    try:
        c = connect_ro(p)
        n = c.execute("SELECT COUNT(*) FROM sentiment").fetchone()[0]
        c.close()
        return n > 0
    except sqlite3.OperationalError:
        return False
