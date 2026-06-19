"""Deterministic mock data — used when PAPIER's papier.db is missing or empty.

Returns the SAME dataframes the real-query module returns. Stable across reloads
via a fixed RNG seed.
"""
import random
from datetime import datetime, timedelta, timezone

import pandas as pd

from signal_terminal.sectors import SECTOR_OF, all_sectors
from signal_terminal.style import EVENT_FLAGS, EVENT_LABEL

_RNG = random.Random(0)

# Reference "now" used by the mock — matches the prototype's NOW.
NOW = datetime(2026, 6, 18, 15, 0, 0, tzinfo=timezone.utc)


def _seeded_iter():
    return random.Random(0)


def universe_latest_mock() -> pd.DataFrame:
    rng = _seeded_iter()
    rows = []
    for sym, sec in sorted(SECTOR_OF.items()):
        sentiment = max(-1.0, min(1.0, (rng.random() - 0.5) * 1.6))
        materiality = rng.random() ** 1.8
        geo_risk = (rng.random() ** 2.5) if rng.random() < 0.5 else 0.0
        confidence = 0.45 + rng.random() * 0.45
        articles = max(1, int(rng.random() * 7))
        sources = max(1, int(rng.random() * 4))
        truncated = 1 if rng.random() < 0.02 else 0
        hours_ago = rng.random() * 30
        pub_at = NOW - timedelta(hours=hours_ago)
        win_end = NOW - timedelta(hours=int(hours_ago))
        win_start = win_end - timedelta(hours=1)
        flags = {f: 1 if rng.random() < 0.04 else 0 for f in EVENT_FLAGS}
        rows.append({
            "symbol": sym,
            "sector": sec,
            "window_start": win_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "window_end": win_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "published_at_max": pub_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "scored_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "score_source": "mock:0",
            "sentiment": round(sentiment, 3),
            "sentiment_confidence": round(confidence, 3),
            "materiality": round(materiality, 3),
            "geo_risk": round(geo_risk, 3),
            "article_count": articles,
            "source_count": sources,
            "truncated": truncated,
            "status": "ok",
            "hours_since_published": round(hours_ago, 2),
            "fresh": hours_ago < 1.0,
            **flags,
        })
    return pd.DataFrame(rows)


def universe_event_flag_counts_mock(hours: float = 24) -> pd.DataFrame:
    df = universe_latest_mock()
    out = []
    for f in EVENT_FLAGS:
        out.append({
            "flag": f,
            "label": EVENT_LABEL[f],
            "count": int(df[f].sum()),
            "fresh_count": int(df.loc[df["fresh"], f].sum()),
        })
    return pd.DataFrame(out)


def universe_movers_by_abs_mock(limit: int = 10) -> pd.DataFrame:
    df = universe_latest_mock().copy()
    df["abs_s"] = df["sentiment"].abs()
    df = df.sort_values("abs_s", ascending=False).head(limit)
    return df[["symbol", "sector", "sentiment", "materiality", "article_count", "fresh"]]


def universe_movers_by_delta_mock(limit: int = 10) -> pd.DataFrame:
    rng = _seeded_iter()
    df = universe_latest_mock().copy()
    df["sentiment_now"] = df["sentiment"]
    df["sentiment_prior"] = df["sentiment"].apply(
        lambda v: max(-1.0, min(1.0, v + (rng.random() - 0.5) * 1.2))
    )
    df["delta"] = df["sentiment_now"] - df["sentiment_prior"]
    df["abs_delta"] = df["delta"].abs()
    df = df.sort_values("abs_delta", ascending=False).head(limit)
    return df[["symbol", "sector", "sentiment_now", "sentiment_prior", "delta", "abs_delta", "fresh"]]


def universe_qa_mock() -> dict:
    return {"malformed_json": 2, "truncated": 5, "dropped_articles": 42}


def trending_themes_mock(limit: int = 12) -> pd.DataFrame:
    sample = [
        ("export-control",     7, 23, 0.78, -0.91, 2),
        ("price-target-raise", 9, 19, 0.81,  0.94, 1),
        ("contract-award",     5, 14, 0.88,  0.93, 3),
        ("china-ban",          4, 11, 0.79, -0.97, 0),
        ("ai-infrastructure",  6, 10, 0.85,  0.55, 0),
        ("bitcoin-price",      3,  9, 0.83, -0.31, 0),
        ("fda-approval",       2,  6, 0.95,  0.88, 1),
        ("iran-sanctions",     2,  5, 0.99, -0.99, 0),
        ("analyst-downgrade",  4,  5, 0.69, -0.95, 0),
        ("commodity-move",     5,  5, 0.62, -0.10, 0),
    ]
    rows = [{
        "canonical_term": t,
        "n_symbols": ns, "n_windows": nw,
        "mean_weight": mw, "mean_term_sentiment": ms,
        "fresh_count": fc,
        "influence": nw * abs(ms) * mw,
    } for (t, ns, nw, mw, ms, fc) in sample][:limit]
    return pd.DataFrame(rows).sort_values("influence", ascending=False)


def symbol_history_mock(symbol: str, days: int = 180) -> pd.DataFrame:
    rng = random.Random(hash(symbol) & 0xFFFFFFFF)
    rows = []
    start = NOW - timedelta(days=days)
    t = start
    s = 0.0
    while t <= NOW:
        s = max(-1.0, min(1.0, s * 0.9 + (rng.random() - 0.5) * 0.3))
        m = rng.random() ** 1.6
        g = rng.random() ** 2.5 if rng.random() < 0.5 else 0.0
        c = 0.4 + rng.random() * 0.5
        ac = max(1, int(rng.random() * 5))
        flags = {f: 1 if rng.random() < 0.03 else 0 for f in EVENT_FLAGS}
        rows.append({
            "symbol": symbol,
            "window_start": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "window_end": (t + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "published_at_max": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "scored_at": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "score_source": "mock:0",
            "sentiment": round(s, 3),
            "sentiment_confidence": round(c, 3),
            "materiality": round(m, 3),
            "geo_risk": round(g, 3),
            "article_count": ac,
            "source_count": max(1, int(ac * 0.6)),
            "truncated": 0,
            "status": "ok",
            **flags,
        })
        t += timedelta(hours=6)
    df = pd.DataFrame(rows)
    df["window_start_dt"] = pd.to_datetime(df["window_start"], utc=True)
    return df


def symbol_drivers_window_mock(symbol: str, hours: float = 24.0) -> pd.DataFrame:
    """Aggregated drivers for one symbol across a lookback window — mock."""
    rng = random.Random(hash((symbol, int(hours))) & 0xFFFFFFFF)
    pool = [
        ("export-control", -0.9), ("ipo", 0.6), ("analyst-downgrade", -0.85),
        ("contract-award", 0.92), ("ai-boom", 0.55), ("cloud-deal", 0.5),
        ("price-target-raise", 0.9), ("partnership", 0.4), ("china-ban", -0.9),
        ("fda-approval", 0.85), ("guidance-cut", -0.8),
    ]
    k = max(2, int(rng.random() * 6) + 2)
    chosen = rng.sample(pool, min(k, len(pool)))
    rows = []
    for term, base_sent in chosen:
        n_win = max(1, int(rng.random() * 4) + 1)
        last_hrs_ago = round(rng.random() * float(hours), 2)
        rows.append({
            "canonical_term":           term,
            "n_windows":                n_win,
            "max_weight":               round(0.45 + rng.random() * 0.55, 2),
            "mean_weight":              round(0.35 + rng.random() * 0.5, 2),
            "mean_term_sentiment":      round(max(-1.0, min(1.0,
                                                base_sent + (rng.random() - 0.5) * 0.3)), 2),
            "first_window_start":       "2026-06-12T00:00:00Z",
            "last_window_start":        "2026-06-17T00:00:00Z",
            "hours_since_last_window":  last_hrs_ago,
        })
    return (pd.DataFrame(rows)
              .sort_values(["max_weight", "n_windows"], ascending=[False, False])
              .reset_index(drop=True))


def symbol_drivers_mock(symbol: str, window_start: str) -> pd.DataFrame:
    rng = random.Random(hash((symbol, window_start)) & 0xFFFFFFFF)
    pool = [
        ("export-control", -0.9), ("price-target-raise", 0.94), ("contract-award", 0.92),
        ("china-ban", -0.95), ("ai-infrastructure", 0.5), ("guidance-cut", -0.9),
        ("fda-approval", 0.88), ("iran-sanctions", -0.99), ("commodity-move", 0.0),
        ("analyst-downgrade", -0.9), ("partnership", 0.4),
    ]
    k = max(1, int(rng.random() * 4) + 1)
    chosen = rng.sample(pool, k)
    rows = [{
        "term": term,
        "canonical_term": term,
        "weight": round(0.4 + rng.random() * 0.6, 2),
        "term_sentiment": ts,
    } for (term, ts) in chosen]
    df = pd.DataFrame(rows).sort_values("weight", ascending=False)
    return df


def driver_symbols_mock(canonical_term: str, hours: float = 24.0) -> pd.DataFrame:
    """Deterministic affected-symbols rollup for one driver. Seeded by the term."""
    seed = hash(canonical_term) & 0xFFFFFFFF
    rng = random.Random(seed)
    base = universe_latest_mock()
    n = min(len(base), max(8, int(rng.random() * 18) + 8))
    picked = base.sample(n=n, random_state=seed).reset_index(drop=True)
    rows = []
    for _, r in picked.iterrows():
        weight = round(0.35 + rng.random() * 0.6, 3)
        term_sent = round(max(-1.0, min(1.0, r["sentiment"] * 0.6
                                         + (rng.random() - 0.5) * 0.7)), 3)
        nw = max(1, int(rng.random() * 4) + 1)
        rows.append({
            "symbol": r["symbol"],
            "sector": r["sector"],
            "weight": weight,
            "term_sentiment": term_sent,
            "n_windows_with_term": nw,
            "latest_sentiment": r["sentiment"],
            "latest_materiality": r["materiality"],
            "latest_geo_risk": r["geo_risk"],
            "latest_article_count": int(r["article_count"]),
            "hours_since_published": r["hours_since_published"],
            "fresh": bool(r["fresh"]),
        })
    df = pd.DataFrame(rows).sort_values("weight", ascending=False).reset_index(drop=True)
    return df


def symbols_carrying_drivers_mock(hours: float = 24.0,
                                    canonical_terms: list[str] | None = None) -> pd.DataFrame:
    """Per-symbol summary across a set of drivers — deterministic mock."""
    cols = [
        "symbol", "sector", "n_drivers", "top_drivers",
        "mean_weight", "mean_term_sentiment",
        "latest_sentiment", "latest_materiality", "latest_geo_risk",
        "latest_article_count", "hours_since_published", "fresh",
    ]
    if not canonical_terms:
        return pd.DataFrame(columns=cols)
    base = universe_latest_mock()
    rng = random.Random(hash(tuple(sorted(canonical_terms))) & 0xFFFFFFFF)
    n = min(len(base), max(10, int(rng.random() * 18) + 10))
    picked = base.sample(n=n, random_state=rng.randint(0, 1 << 30)).reset_index(drop=True)
    out = []
    for _, r in picked.iterrows():
        n_drv = max(1, int(rng.random() * min(5, len(canonical_terms))) + 1)
        chosen = rng.sample(canonical_terms, min(n_drv, len(canonical_terms)))
        out.append({
            "symbol": r["symbol"],
            "sector": r["sector"],
            "n_drivers": len(chosen),
            "top_drivers": ", ".join(chosen[:3]),
            "mean_weight": round(0.3 + rng.random() * 0.65, 3),
            "mean_term_sentiment": round((rng.random() - 0.5) * 1.6, 3),
            "latest_sentiment": r["sentiment"],
            "latest_materiality": r["materiality"],
            "latest_geo_risk": r["geo_risk"],
            "latest_article_count": int(r["article_count"]),
            "hours_since_published": r["hours_since_published"],
            "fresh": bool(r["fresh"]),
        })
    return (pd.DataFrame(out)[cols]
              .sort_values(["n_drivers", "mean_weight"], ascending=[False, False])
              .reset_index(drop=True))


def driver_correlation_matrix_mock(hours: float = 24.0, limit: int = 12,
                                    metric: str = "phi", min_symbols: int = 1) -> pd.DataFrame:
    """Symmetric mock association matrix. `metric` switches range; `min_symbols`
    is a no-op in mock (deterministic terms are kept regardless)."""
    terms = trending_themes_mock()["canonical_term"].head(limit).tolist()
    rng = random.Random(42 if metric == "phi" else 43)
    n = len(terms)
    data = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i, n):
            if i == j:
                data[i][j] = 1.0
            else:
                if metric == "jaccard":
                    v = round(rng.random() ** 2, 3)        # skewed low, in [0,1]
                else:
                    v = round((rng.random() - 0.45) * 0.9, 3)  # ~[-0.4, +0.5]
                data[i][j] = v
                data[j][i] = v
    return pd.DataFrame(data, index=terms, columns=terms)


def sector_aggregates_mock() -> pd.DataFrame:
    df = universe_latest_mock()
    g = df.groupby("sector").agg(
        n_symbols=("symbol", "nunique"),
        mean_sentiment=("sentiment", "mean"),
        mean_materiality=("materiality", "mean"),
        mean_geo_risk=("geo_risk", "mean"),
    ).reset_index()
    return g


def sector_history_mock(metric: str = "sentiment", days: int = 180) -> pd.DataFrame:
    rng = random.Random(metric)
    rows = []
    for sector in all_sectors():
        v = 0.0
        d = NOW - timedelta(days=days)
        while d <= NOW:
            v = max(-1.0, min(1.0, v * 0.85 + (rng.random() - 0.5) * 0.2)) if metric == "sentiment" \
                else max(0.0, min(1.0, 0.3 + (rng.random() - 0.5) * 0.4))
            rows.append({"day": d, "sector": sector, "value": round(v, 3)})
            d += timedelta(days=1)
    return pd.DataFrame(rows)


def pipeline_runs_mock(limit: int = 20) -> pd.DataFrame:
    rng = random.Random(0)
    rows = []
    for i in range(limit):
        started = NOW - timedelta(hours=i * 1.5)
        duration = 25 + rng.random() * 40
        ended = started + timedelta(minutes=duration)
        errors = 0 if rng.random() < 0.9 else rng.randint(1, 6)
        rows_written = 30 + int(rng.random() * 60)
        status = "ok" if errors == 0 else ("degraded" if errors < 3 else "failed")
        rows.append({
            "run_id": f"mock-{i:03d}",
            "command": "run-once" if i > 0 else "backfill",
            "started_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ended_at": ended.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "rows_written": rows_written,
            "errors": errors,
            "notes": None,
            "started_dt": started,
            "duration_min": round(duration, 1),
            "status": status,
        })
    return pd.DataFrame(rows)


def pipeline_dropped_by_reason_trend_mock(days: int = 60) -> pd.DataFrame:
    rng = random.Random(1)
    reasons = ("dup_title", "over_cap", "late", "rate_limit", "parse_error")
    rows = []
    d = NOW - timedelta(days=days)
    while d <= NOW:
        for r in reasons:
            rows.append({"day": d, "reason": r, "count": int(rng.random() * 8)})
        d += timedelta(days=1)
    return pd.DataFrame(rows)


def pipeline_trend_lines_mock(days: int = 60) -> pd.DataFrame:
    rng = random.Random(2)
    rows = []
    d = NOW - timedelta(days=days)
    while d <= NOW:
        rows.append({
            "day": d,
            "malformed_json": int(rng.random() * 3),
            "truncated": int(rng.random() * 5),
        })
        d += timedelta(days=1)
    return pd.DataFrame(rows)
