"""Switches between live PAPIER queries and deterministic mock.

Views import from here; they never touch queries.py or mockdata.py directly.
"""
from pathlib import Path

import pandas as pd
import streamlit as st

from signal_terminal import queries, mockdata
from signal_terminal.config import Config
from signal_terminal.db import db_has_data


def _use_live(cfg: Config) -> bool:
    if not cfg.live:
        return False
    if db_has_data(cfg.db_path):
        return True
    if cfg.fallback_to_mock:
        return False
    raise FileNotFoundError(
        f"papier.db missing/empty at {cfg.db_path}; set data.fallback_to_mock=true to use mock"
    )


def universe_latest(cfg: Config) -> pd.DataFrame:
    if _use_live(cfg):
        return queries.universe_latest(cfg.db_path)
    return mockdata.universe_latest_mock()


def universe_event_flag_counts(cfg: Config) -> pd.DataFrame:
    if _use_live(cfg):
        return queries.universe_event_flag_counts(cfg.db_path)
    return mockdata.universe_event_flag_counts_mock()


def universe_movers_by_abs(cfg: Config) -> pd.DataFrame:
    if _use_live(cfg):
        return queries.universe_movers_by_abs(cfg.db_path)
    return mockdata.universe_movers_by_abs_mock()


def universe_movers_by_delta(cfg: Config) -> pd.DataFrame:
    if _use_live(cfg):
        return queries.universe_movers_by_delta(cfg.db_path)
    return mockdata.universe_movers_by_delta_mock()


def universe_qa(cfg: Config) -> dict:
    if _use_live(cfg):
        return queries.universe_qa(cfg.db_path)
    return mockdata.universe_qa_mock()


def trending_themes(cfg: Config) -> pd.DataFrame:
    if _use_live(cfg):
        return queries.trending_themes(cfg.db_path)
    return mockdata.trending_themes_mock()


def symbols_for_theme(cfg: Config, canonical_term: str) -> list[str]:
    if _use_live(cfg):
        return queries.symbols_for_theme(cfg.db_path, canonical_term)
    df = mockdata.universe_latest_mock()
    return df["symbol"].sample(min(20, len(df)), random_state=hash(canonical_term) & 0xFFFFFFFF).tolist()


def symbol_history(cfg: Config, symbol: str, days: int = 180) -> pd.DataFrame:
    if _use_live(cfg):
        return queries.symbol_history(cfg.db_path, symbol, days)
    return mockdata.symbol_history_mock(symbol, days)


def symbol_drivers(cfg: Config, symbol: str, window_start: str) -> pd.DataFrame:
    if _use_live(cfg):
        return queries.symbol_drivers(cfg.db_path, symbol, window_start)
    return mockdata.symbol_drivers_mock(symbol, window_start)


def sector_aggregates(cfg: Config) -> pd.DataFrame:
    if _use_live(cfg):
        return queries.sector_aggregates(cfg.db_path)
    return mockdata.sector_aggregates_mock()


def sector_history(cfg: Config, metric: str = "sentiment", days: int = 180) -> pd.DataFrame:
    if _use_live(cfg):
        return queries.sector_history(cfg.db_path, metric, days)
    return mockdata.sector_history_mock(metric, days)


def pipeline_runs(cfg: Config) -> pd.DataFrame:
    if _use_live(cfg):
        return queries.pipeline_runs(cfg.db_path)
    return mockdata.pipeline_runs_mock()


def pipeline_dropped_by_reason_trend(cfg: Config) -> pd.DataFrame:
    if _use_live(cfg):
        return queries.pipeline_dropped_by_reason_trend(cfg.db_path)
    return mockdata.pipeline_dropped_by_reason_trend_mock()


def pipeline_trend_lines(cfg: Config) -> pd.DataFrame:
    if _use_live(cfg):
        return queries.pipeline_trend_lines(cfg.db_path)
    return mockdata.pipeline_trend_lines_mock()
