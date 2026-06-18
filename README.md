# Signal Terminal — Dashboard_Papier

Streamlit + Plotly dashboard over PAPIER's `papier.db`. Read-only consumer of the same dataset QARSA reads.

## Run

```bash
cd ~/Projects/Dashboard_Papier
uv sync --extra dev
uv run streamlit run app.py
```

Open the URL Streamlit prints (default `http://localhost:8501`).

## Config

`config.toml` controls the data source:

- `paper.db` — absolute path to PAPIER's `papier.db`. Opened with SQLite `mode=ro`.
- `data.live` — `true` reads PAPIER, `false` uses deterministic mock data.
- `data.fallback_to_mock` — if `live=true` but the DB is missing/empty, fall back to mock.

## Layout

Single Streamlit page, 4 tabs (per the design handoff):

1. **TODAY'S PULSE** — universe heatmap (treemap / dense grid / sector group), event-flag counter row, trending themes pills, |sentiment| & Δ24h movers, QA strip.
2. **SYMBOL DETAIL** — ticker header + metrics, sentiment timeseries with confidence band + event markers, drivers (term panel), raw windows table.
3. **SECTOR LENS** — 4 sector cards, trailing 180d timeseries per sector, latest comparison bars.
4. **PIPELINE HEALTH** — QA cards, malformed/truncated trend, dropped-by-reason stacked area, run history.

Design tokens are authoritative in `src/signal_terminal/style.py`. See `CLAUDE.md` and `Claude/design_handoff_signal_terminal/` for the full design system reference.

## Status

**v0.1 (today)**: scaffold + style + db + queries + loader + mock fallback. **TODAY'S PULSE is the fully-built screen**; SYMBOL DETAIL, SECTOR LENS, PIPELINE HEALTH are functional but render minimal layouts pending tomorrow's full build against the historical backfill.

## Out of scope

Mobile/responsive. Writes to PAPIER. Auth. Live websocket updates.
