# Signal Terminal — Dashboard_Papier

A read-only Streamlit + Plotly dashboard over PAPIER's `papier.db`. Six tabs of
sentiment / driver / sector / pipeline structure, fixed 1920×1080 desktop
layout, terminal aesthetic.

This repo is **only the dashboard**. It never writes to PAPIER's database. To
get useful data on screen you need three things on disk:

| Piece | What it is | Where it lives |
|---|---|---|
| **PAPIER** | The producer: pulls news, scores sentiment, extracts canonical drivers, writes to `papier.db`. | Separate repo (`PAPIER/`). |
| **`papier.db`** | The shared SQLite file. PAPIER writes; Dashboard_Papier reads (`mode=ro`). | `<PAPIER>/data/papier.db` by default. |
| **Dashboard_Papier** | This repo. Streamlit views, Plotly charts, PIT-gated queries against `papier.db`. | The directory you're in. |

PAPIER does the work; this dashboard makes it readable. The two communicate
*only* through `papier.db`.

## Quick start

```bash
# 1. Clone (you've presumably already done this)
git clone https://github.com/infioramton-dxain/papier_dashboard.git Dashboard_Papier
cd Dashboard_Papier

# 2. Install deps into a local .venv (uv reads pyproject.toml + uv.lock)
uv sync

# 3. Point config.toml at your papier.db (see "Configuration" below)
$EDITOR config.toml

# 4. Launch
./start.sh
```

`start.sh` activates `.venv` and runs Streamlit on **`http://localhost:8520`**
(bound to `0.0.0.0` so WSL → Windows localhost forwarding works). Telemetry
is disabled.

If you don't have PAPIER's `papier.db` yet, the dashboard will fall back to
deterministic mock data — see `data.fallback_to_mock` below — so you can still
explore the UI.

## Configuration

Everything user-tunable lives in `config.toml`:

```toml
[paper]
db = "/absolute/path/to/PAPIER/data/papier.db"   # opened mode=ro

[data]
live = true                # false → mock data only
fallback_to_mock = true    # if live=true but DB missing/empty → use mock

[ui]
recency_hours = 1          # < this many hours = "fresh" (the only cyan use)
default_tab   = "pulse"    # pulse | symbol | sector | driver | pipeline
cache_ttl_seconds = 3600

[universe]
symbols_csv = ""           # blank → derive from sentiment table
```

The `.streamlit/config.toml` file in the repo pins the dark theme; you
shouldn't need to touch it.

## What's on each tab

1. **TODAY'S PULSE** — universe heatmap (treemap / dense grid / sector group),
   event-flag counter row, trending themes pills, |sentiment| & Δ24h movers,
   QA strip. The landing screen.
2. **SYMBOL DETAIL** — picker + 180-day window history table + drivers rollup
   over the chosen lookback. Drivers section has the same metric / min-symbols
   / range filters as Driver Correlation so the views stay consistent.
3. **SECTOR LENS** — 4 sector cards, trailing-180d series per sector, latest
   comparison bars.
4. **DRIVER DETAIL** — paginated driver picker over trending themes, treemap
   of affected symbols, paginated relevance table per symbol.
5. **DRIVER CORRELATION** — driver-by-driver matrix (φ or Jaccard), click any
   cell to inspect the pair, two-handle range slider, min-symbols + metric
   filters with plain-English captions, SYMBOLS COVERED table listing the
   stocks the surviving drivers touch.
6. **PIPELINE HEALTH** — QA cards, malformed / truncated trend lines,
   dropped-articles-by-reason stacked area, recent runs table.

Tabs 2, 4, and 5 share a `24H / 7D / 30D / 90D` lookback selector — change it
on one, the other two pick it up.

## Hard rules

These are mirrored from `CLAUDE.md` and enforced in code:

1. **Read-only on PAPIER's DB.** Every connection uses `?mode=ro`. No
   `INSERT` / `UPDATE` / `DELETE` ever runs against `papier.db` from here.
2. **Point-in-time discipline.** Rolling queries gate on `published_at_max`,
   anchored at `MAX(published_at_max)` in the DB rather than wall-clock now —
   so the dashboard reads coherently even when PAPIER is between batches.
3. **Fixed 1920×1080 desktop.** No responsive layout; density is the point.
4. **Recency cyan (`#00e5ff`) is reserved for < 1h.** Never used for
   navigation, category, or emphasis on stale rows.

## Architecture map

```
Dashboard_Papier/
├── app.py                          # Streamlit entry, tab router (6 tabs)
├── start.sh                        # launcher (.venv + Streamlit on :8520)
├── config.toml                     # paths, live/mock mode, UI knobs
├── .streamlit/config.toml          # dark theme override
└── src/signal_terminal/
    ├── config.py                   # load config.toml
    ├── db.py                       # read-only sqlite connection
    ├── queries.py                  # PIT-gated queries (one fn per panel)
    ├── mockdata.py                 # deterministic mock fallback
    ├── loader.py                   # live/mock switch sitting in front of views
    ├── style.py                    # design tokens, Plotly LAYOUT, sentiment ramp
    ├── sectors.py                  # symbol → sector classification
    ├── universe.py                 # symbol+sector loader
    ├── state.py                    # session_state keys & cross-tab helpers
    ├── components/                 # KPI tile, heatmap, movers, theme pills, ...
    └── views/
        ├── _common.py              # shared window/filter helpers
        ├── pulse.py                # Today's Pulse
        ├── symbol_detail.py        # Symbol Detail
        ├── sector_lens.py          # Sector Lens
        ├── driver_detail.py        # Driver Detail
        ├── driver_correlation.py   # Driver Correlation
        └── pipeline_health.py      # Pipeline Health
```

Design tokens (colors, type scale, spacing) are authoritative in `style.py`;
keep them in sync with `Claude/design_handoff_signal_terminal/Signal Terminal
- Design System.dc.html`.

## Distributing this (DB bundling, deferred)

The intent is to eventually let other users do:

```bash
git clone <Dashboard_Papier>
cd Dashboard_Papier
./start.sh         # works against a bundled demo papier.db, no PAPIER needed
```

That requires committing a `papier.db` (or slice) into this repo. Today
`papier.db` is small enough that a direct commit is trivially under GitHub's
limits (raw < 2 MB; gzip ≈ 0.4 MB). The decision to actually ship it is
deferred until PAPIER's full backfill lands so we measure the real size, and
until the data is confirmed safe to redistribute.

In the meantime: point `paper.db` at your live PAPIER instance, or leave
`data.fallback_to_mock = true` and explore against the deterministic mock.

## Out of scope

- Mobile / responsive layouts.
- Writes back to PAPIER. (Read-only forever.)
- User auth — the dashboard runs on your laptop only.
- Live websocket updates — refresh button is fine.
