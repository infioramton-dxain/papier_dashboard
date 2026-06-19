"""Tests for src/signal_terminal/analytics/events.py.

Synthetic flag matrix with known co-firings; verify diagonal counts, min-Jaccard
off-diagonals, monthly firing-rate shape, and per-symbol breakdown.
"""
from __future__ import annotations

import pandas as pd

from signal_terminal.analytics.events import (firing_rates_over_time,
                                                 firing_rates_per_symbol,
                                                 flag_cooccurrence)
from signal_terminal.style import EVENT_FLAGS


def _df(rows: list[dict]) -> pd.DataFrame:
    """Build the long-format frame analytics.data.load_sentiment would return."""
    df = pd.DataFrame(rows)
    for f in EVENT_FLAGS:
        if f not in df.columns:
            df[f] = 0
    df["window_start_dt"] = pd.to_datetime(df["window_start"], utc=True)
    return df


def test_cooccurrence_diagonal_counts_and_min_jaccard() -> None:
    rows = [
        {"symbol": "A", "window_start": "2026-01-01T00:00:00Z",
         "mna": 1, "regulatory_export": 1, "litigation": 0},
        {"symbol": "A", "window_start": "2026-01-01T01:00:00Z",
         "mna": 1, "regulatory_export": 0, "litigation": 0},
        {"symbol": "B", "window_start": "2026-01-01T02:00:00Z",
         "mna": 1, "regulatory_export": 1, "litigation": 0},
        {"symbol": "B", "window_start": "2026-01-01T03:00:00Z",
         "mna": 0, "regulatory_export": 0, "litigation": 1},
    ]
    cooc = _build_cooc(rows)
    # mna fires 3 times, regulatory_export 2, litigation 1
    assert cooc.loc["mna", "mna"] == 3.0
    assert cooc.loc["regulatory_export", "regulatory_export"] == 2.0
    assert cooc.loc["litigation", "litigation"] == 1.0
    # mna ∩ regulatory_export = 2, min(3, 2) = 2 → 2/2 = 1.0
    assert abs(cooc.loc["mna", "regulatory_export"] - 1.0) < 1e-9
    # mna ∩ litigation = 0
    assert cooc.loc["mna", "litigation"] == 0.0


def _build_cooc(rows: list[dict]) -> pd.DataFrame:
    return flag_cooccurrence(_df(rows))


def test_firing_rates_over_time_monthly_bins() -> None:
    rows = []
    # Jan: 4 windows, mna fires in 2 → rate 0.5
    for i in range(4):
        rows.append({"symbol": "A", "window_start": f"2026-01-{i+1:02d}T00:00:00Z",
                     "mna": 1 if i < 2 else 0})
    # Feb: 4 windows, mna fires in 1 → rate 0.25
    for i in range(4):
        rows.append({"symbol": "A", "window_start": f"2026-02-{i+1:02d}T00:00:00Z",
                     "mna": 1 if i == 0 else 0})
    over = firing_rates_over_time(_df(rows), freq="ME")
    assert "mna" in over.columns
    jan = over[over.index.month == 1]["mna"].iloc[0]
    feb = over[over.index.month == 2]["mna"].iloc[0]
    assert abs(jan - 0.5) < 1e-9
    assert abs(feb - 0.25) < 1e-9


def test_firing_rates_per_symbol_one_row_each() -> None:
    rows = [
        {"symbol": "A", "window_start": "2026-01-01T00:00:00Z", "mna": 1},
        {"symbol": "A", "window_start": "2026-01-01T01:00:00Z", "mna": 0},
        {"symbol": "B", "window_start": "2026-01-01T02:00:00Z", "mna": 1},
    ]
    per = firing_rates_per_symbol(_df(rows))
    assert set(per["symbol"]) == {"A", "B"}
    assert per.loc[per["symbol"] == "A", "mna_rate"].iloc[0] == 0.5
    assert per.loc[per["symbol"] == "B", "mna_rate"].iloc[0] == 1.0


def test_cooccurrence_empty_input_returns_zero_matrix() -> None:
    cooc = flag_cooccurrence(pd.DataFrame())
    assert cooc.shape[0] == len(EVENT_FLAGS)
    assert cooc.values.sum() == 0.0
