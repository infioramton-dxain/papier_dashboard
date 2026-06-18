# Signal Terminal — Dashboard_Papier

Read-only Streamlit + Plotly dashboard over PAPIER's `papier.db`. A second consumer of the same dataset that QARSA reads. **This project never writes to PAPIER's database. Never.**

## Hard rules

1. **Read-only on PAPIER's DB.** `sqlite3.connect("file:.../papier.db?mode=ro", uri=True)`. No `INSERT`/`UPDATE`/`DELETE` ever runs from this project against `papier.db`.
2. **Point-in-time discipline.** Every read query uses `published_at_max` as the "as of" gate. Never `scored_at`. Never `window_start` alone. Mirrors the rules in PAPIER's CLAUDE.md.
3. **No mockup-only behavior in prod queries.** Mock data is a *fallback* (`config.data.live = false`), not a parallel reality. Real and mock paths return the same dataframe shapes.
4. **Fixed 1920×1080 desktop only.** No responsive layout. Information density wins over whitespace. Streamlit's default chrome is too airy — inject CSS where needed.
5. **Recency cyan (`#00e5ff`) is reserved for "just happened" (< 1h).** Never use it for navigation, never for category, never for emphasis on stale rows.

## Project layout (canonical)

```
Dashboard_Papier/
├── app.py                          # Streamlit entry, tab router
├── config.toml                     # paths, mode (live/mock), UI config
├── .streamlit/config.toml          # dark theme override
├── src/signal_terminal/
│   ├── config.py                   # load config.toml
│   ├── db.py                       # read-only sqlite connection
│   ├── queries.py                  # PIT-gated queries (PAPIER + mock)
│   ├── style.py                    # tokens, LAYOUT, sentiment ramp
│   ├── sectors.py                  # symbol → sector classification (hand-edited)
│   ├── universe.py                 # symbol+sector loader
│   ├── mockdata.py                 # deterministic mock (Python port of signal-data.js)
│   ├── state.py                    # session_state keys & helpers
│   ├── components/                 # KPI tile, heatmap, mover row, theme pill, ...
│   └── views/                      # pulse | symbol_detail | sector_lens | pipeline_health
└── Claude/                         # private: design handoff, scratch
```

## Design tokens (authoritative)

These are mirrored in `style.py` and must match. See `Claude/design_handoff_signal_terminal/Signal Terminal - Design System.dc.html` for the full token spec.

| token | hex | role |
|---|---|---|
| `BG` | `#0d1117` | app background |
| `SURFACE` | `#0a0e13` | panel fill, plot bg |
| `BORDER` | `#1f2630` | frame |
| `TEXT_HI` | `#e6edf3` | tickers, hero values |
| `DIM` | `#8b949e` | secondary |
| `POS` | `#30a46c` | bullish |
| `NEG` | `#e5484d` | bearish / errors |
| `NEUTRAL` | `#2b323c` | sentiment = 0 |
| `WARN` | `#d29922` | truncated / elevated geo_risk |
| **`FRESH`** | **`#00e5ff`** | **< 1h only** |

Sector identity (categorical, never implies value):
Defense `#6ea8fe` · Mining `#e0a458` · Tech `#bb9af7` · Materials `#7ec9c9`

Sentiment ramp (the one scale for all sentiment encoding):
- Plotly colorscale: `[[0,'#e5484d'],[0.5,'#2b323c'],[1,'#30a46c']]` (sentiment normalized -1..1 → 0..1).
- Sqrt easing in code for tile fills so small signals stay visible.

Typography: **JetBrains Mono** only. Uppercase + 1–2px tracking on all labels. Tabular figures on every metric.

## State management

Streamlit `st.session_state` keys (mirror the prototype exactly):
- `active_tab` — `pulse | symbol | sector | pipeline`
- `mode` — `treemap | grid | sector` (Pulse heatmap encoding)
- `sec_metric` — `sentiment | materiality | geo_risk` (Sector Lens)
- `selected_symbol` — current ticker for Symbol Detail
- `theme_filter` — active canonical_term or None

Cross-filter rules:
- Click heatmap tile / mover row / driver row → set `selected_symbol`, switch `active_tab` to `symbol`.
- Click theme pill (Pulse) or driver row (Symbol) → set `theme_filter`, switch to `pulse`, filter heatmap to peer symbols carrying that term.

## Data shape PAPIER provides today

PAPIER's `sentiment` table (one row per `(symbol, hour-aligned window)`):
- `symbol`, `window_start`, `window_end`, `published_at_max` (the PIT cursor), `scored_at` (audit), `score_source`
- `article_count`, `source_count`, `truncated` (0/1), `status` (`'ok'|'malformed_json'`)
- `sentiment` (-1..1), `sentiment_confidence` (0..1), `materiality` (0..1), `geo_risk` (0..1)
- event-flag columns (each 0/1): `contract_award`, `guidance`, `mna`, `regulatory_export`, `litigation`, `analyst_action`, `commodity_move`

PAPIER's `term` table (added in v3):
- `symbol`, `window_start`, `term` (kebab-case), `weight` (0..1), `term_sentiment` (-1..1)
- Note the handoff proposes a richer `keyword` schema with `canonical_term`, `term_type`, `article_count`, `first_seen`, `extraction_model`, `prompt_version`. The dashboard works around the gap today by canonicalizing in the query layer (`queries._canonicalize_term`).

PAPIER's `runs`, `dropped_articles` tables feed Pipeline Health.

## Behavior rules

- **All queries cached** via `@st.cache_data(ttl=3600)`. Cache invalidation on a manual "↻ refresh" button only.
- **Plotly:** import the shared `LAYOUT` dict from `style.py`. Never inline-edit colors or fonts in a chart spec.
- **Tabs:** active tab = white text + 2px white bottom border (cyan reserved for recency).
- **Loading state:** `◆ INITIALIZING SIGNAL FEED…` until both data and Plotly are ready.

## Out of scope (v1)

- Mobile / responsive layouts.
- Writing back to PAPIER. (Read-only forever.)
- User auth — this runs on the user's laptop only.
- Live websocket updates — manual refresh button is fine.
