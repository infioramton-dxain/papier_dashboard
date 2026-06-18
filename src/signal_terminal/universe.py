"""Load the symbol universe + per-symbol sector classification."""
import csv
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from signal_terminal.sectors import sector_of


@dataclass(frozen=True)
class SymbolMeta:
    symbol: str
    sector: str


def _from_csv(path: Path) -> list[SymbolMeta]:
    out: list[SymbolMeta] = []
    seen = set()
    with path.open() as f:
        for row in csv.reader(f):
            if not row:
                continue
            s = row[0].strip().upper()
            if s in ("SYMBOL", "TICKER", ""):
                continue
            if s in seen:
                continue
            seen.add(s)
            out.append(SymbolMeta(symbol=s, sector=sector_of(s)))
    return out


def _from_db(conn: sqlite3.Connection) -> list[SymbolMeta]:
    rows = conn.execute("SELECT DISTINCT symbol FROM sentiment ORDER BY symbol").fetchall()
    return [SymbolMeta(symbol=r[0].upper(), sector=sector_of(r[0])) for r in rows]


def load_universe(
    db_conn: sqlite3.Connection | None,
    symbols_csv: Path | None,
) -> list[SymbolMeta]:
    """Universe sources, in priority order:
    1. symbols_csv if configured and exists
    2. distinct symbols from PAPIER's sentiment table
    3. empty list (caller should fall back to mock)
    """
    if symbols_csv and symbols_csv.exists():
        return _from_csv(symbols_csv)
    if db_conn is not None:
        return _from_db(db_conn)
    return []
