# PAPIER Analytics Dashboard — Handoff Spec

A read-only exploratory dashboard over `data/papier.db` for surfacing latent
structure in the sentiment panel (~173 symbols, defense/mining/tech-weighted,
hourly windows from 2023-08 to present).

Three tabs, each answering one analytical question:

1. **Factors** — *What latent drivers exist?*
2. **Cohorts** — *Which symbols group together?*
3. **Events** — *What event patterns travel together?*

The original conversation that produced this scope lives in
`~/.claude/projects/-home-claucodxain-Projects-PAPIER/`. The downstream consumer
is the user (manual exploration), not QARSA — QARSA continues to read from
`papier.db` via the SQL in `src/papier/qarsa_read.sql` and does not touch this
dashboard.

---

## 1. Hard constraints (inherited from `CLAUDE.md`)

These are non-negotiable and override convenience.

- **Read-only on `papier.db`.** Open the SQLite file with
  `?mode=ro&immutable=1` query params in the URI. Never write back.
- **No QARSA coupling.** Do not import, read, or call anything from the sibling
  QARSA directory. The only allowed inputs are `data/papier.db` and
  `Claude/symbols.csv`.
- **No cloud LLMs.** If any descriptive text is LLM-generated, it must go
  through local Ollama (`ollama` dep is already in `pyproject.toml`). No
  Anthropic / OpenAI / Gemini / Cohere calls.
- **No prose into `papier.db`.** If LLM-generated chart interpretations are
  cached, cache them in a JSON file under `data/cache/`, never in the
  `sentiment` table.
- **Plan before code.** This document is the plan. Anything that deviates
  materially from it (extra tabs, schema writes, new dependencies beyond the
  list in §3) requires re-approval from the user before implementation.
- **Point-in-time discipline still matters.** The dashboard reads `window_start`
  and `published_at_max` as the time anchors. `scored_at` is audit-only and
  must NEVER appear as a chart axis, filter, or aggregation key. Treat it as if
  it doesn't exist for analytical purposes.

---

## 2. Does this need new tables in `papier.db`?

**No.** Everything is derivable from the existing `sentiment` table at runtime.

| Concern | Current scale | Decision |
|---|---|---|
| Source rows | ~6,700 (will grow ~5×/yr) | In-memory pandas fine |
| Symbol pivot | 173 × ~25k hourly windows | <100 MB dense, well within memory |
| PCA / NMF / KMeans fit | ms-to-seconds | Recompute on filter change |
| Correlation matrix | 173×173 | Trivial |

**Caching strategy** (no DB writes):

- `@st.cache_data` on all derived matrices, keyed off `(db_mtime, filter_args)`.
  Streamlit invalidates automatically when `papier.db` is rewritten.
- Optional secondary cache: `data/cache/*.parquet` for the heaviest pivots,
  written by the dashboard, gitignored. Only add this if dashboard cold-start
  exceeds ~3 seconds — premature otherwise.
- LLM-generated interpretation text (see §10): cached in
  `data/cache/descriptions.json`, keyed by `(chart_id, data_hash)`.

If the dataset grows past ~10 M sentiment rows, revisit with materialized
parquet snapshots — but that's a year+ away at current ingest rate.

---

## 3. Tech stack

Add a `viz` optional-dependency group to `pyproject.toml` to keep the core
runtime (CLI / backfill) lean. The scoring pipeline must remain installable
without any of these.

```toml
[project.optional-dependencies]
viz = [
    "streamlit>=1.36",
    "plotly>=5.22",
    "scikit-learn>=1.5",
    "scipy>=1.13",
    "pandas>=2.2",
    "numpy>=1.26",
]
```

Rationale: Streamlit gives native `st.tabs(...)` matching the requested UX,
Plotly gives interactive hover/zoom (important for 173-symbol heatmaps),
scikit-learn / scipy cover every algorithm in §6, no other framework needed.

Launch: `streamlit run scripts/dashboard.py`.

---

## 4. File layout

```
scripts/
  dashboard.py                    # Streamlit entry point; tab routing only
src/papier/analytics/             # NEW package — analytics is separate from
  __init__.py                     # the scoring pipeline; no cross-imports
  data.py                         # load_sentiment(), pivots, feature aggregates
  factors.py                      # run_pca(), run_nmf()
  cohorts.py                      # hierarchical_cluster(), kmeans_cluster()
  events.py                       # flag_cooccurrence(), firing_rates()
  descriptions.py                 # static description text per chart
  llm_interpret.py                # OPTIONAL: Ollama-driven dynamic takeaways
data/
  cache/                          # gitignored; parquet + descriptions.json
tests/
  test_analytics_data.py
  test_analytics_factors.py
  test_analytics_cohorts.py
  test_analytics_events.py
```

`scripts/dashboard.py` is intentionally thin — it does layout and wires callbacks
to functions in `src/papier/analytics/`. All numerical work lives in
`analytics/` so it's importable from notebooks and unit-testable without
spinning up Streamlit.

Add to `.gitignore`: `data/cache/`.

---

## 5. Data sources

### 5.1 `papier.db` — `sentiment` table

Authoritative schema (do not duplicate; read from `src/papier/store/schema.sql`):

```
symbol               TEXT     PK part 1
window_start         TEXT     PK part 2 (ISO 8601 UTC, hourly aligned)
window_end           TEXT     (ISO 8601 UTC)
published_at_max     TEXT     QARSA-facing "known by" time
scored_at            TEXT     AUDIT ONLY — never used as a feature
score_source         TEXT     e.g. "ollama:llama3.1:8b-instruct-q4_K_M"
article_count        INTEGER
source_count         INTEGER
truncated            INTEGER  0/1
status               TEXT     'ok' | 'flagged' | etc.
sentiment            REAL     [-1, 1], nullable if status != 'ok'
sentiment_confidence REAL     [0, 1], derived
materiality          REAL     [0, 1]
geo_risk             REAL     [0, 1]
contract_award       INTEGER  0/1
guidance             INTEGER  0/1
mna                  INTEGER  0/1
regulatory_export    INTEGER  0/1
litigation           INTEGER  0/1
analyst_action       INTEGER  0/1
commodity_move       INTEGER  0/1
```

**Filter `WHERE status = 'ok' AND sentiment IS NOT NULL`** for all analytical
loads. Flagged rows are kept in the DB for audit but must not enter any
clustering / factor model.

**Group by `score_source`** when surfacing temporal coverage; if multiple
model ids are present, warn the user prominently in the sidebar — prior rows
are not comparable across model changes (see CLAUDE.md).

### 5.2 `Claude/symbols.csv`

Joinable on `symbol`. Use for sector / industry annotations on plots (color by
sector in biplots, etc.). Inspect columns before relying on a specific name —
the file is user-maintained.

### 5.3 No other inputs.

Do not call Alpaca, Finnhub, or any other live data source from the dashboard.

---

## 6. Tabs, charts, data tables, descriptions

Common page chrome:

- Page title: `PAPIER — Sentiment Analytics`
- Subtitle / model warning banner if multiple `score_source` values present
- Sidebar (sticky, applies to all tabs) — see §7
- Three `st.tabs(["Factors", "Cohorts", "Events"])`

Each tab opens with a large `st.header` containing the **question verbatim**,
followed by a one-sentence framing paragraph.

Every chart is wrapped in `st.container(border=True)` with:

1. Chart title (`st.subheader`)
2. The chart itself
3. A description block (italic, smaller) — two parts:
   - **Static "how to read"** — definition of the visualization (from
     `descriptions.py`)
   - **Dynamic takeaway** (optional, §10) — interpretation of the specific
     numbers in front of the user, generated by local Ollama

Cluster-bearing charts ALWAYS include a `st.dataframe` of cluster membership
immediately beneath them — the user must not need to hover, click, or zoom to
see which symbols are in which cluster.

### Tab 1 — Factors

> **What latent drivers exist in symbol sentiment?**

| # | Chart | Description (what the user is reading) | Cluster table? |
|---|---|---|---|
| 1.1 | **PCA scree plot** — bar of explained variance ratio for PC1–PC10 | "Each bar is the share of cross-sectional sentiment variance captured by that principal component. A tall first bar means one dominant driver (likely market-wide sentiment); a flat tail means symbol-idiosyncratic noise dominates. Use this to decide how many components are worth interpreting." | No |
| 1.2 | **PCA loadings heatmap** — symbols × PC1–PC5 | "Each cell is symbol *s*'s loading on principal component *k*. Red = positive exposure to that factor, blue = negative. Read down a column to see what kind of symbols define each factor; read across a row to see a symbol's factor fingerprint." | No |
| 1.3 | **PCA biplot** — PC1 × PC2 scatter of symbols, colored by sector | "Each dot is a symbol placed by its loading on the first two factors. Symbols near each other share latent drivers. Sector coloring lets you see whether factors align with industry groupings or cut across them." | No |
| 1.4 | **Factor score time series** — PC1, PC2, PC3 over time | "These are the latent factors themselves moving through time. Spikes in PC1 typically correspond to market-wide sentiment events; PC2/PC3 spikes are usually sector or theme events. Cross-reference dates with known news to label what each factor 'is.'" | No |
| 1.5 | **NMF component heatmap** — components × features | "Non-negative matrix factorization finds additive 'themes' in symbol behavior. Each column is a theme (e.g., 'high materiality + regulatory + analyst action'); cell intensity shows how strongly that feature defines the theme. Easier to read than PCA loadings because there are no canceling signs." | No |
| 1.6 | **NMF symbol weights** — symbols × themes table | "Each symbol's mix of themes. Sortable by any theme column. A symbol can load on multiple themes simultaneously — unlike clustering, this is a soft assignment." | YES — sortable table, no chart needed |

**Algorithm details:**

- **PCA inputs**: pivot `sentiment` by `(window_start, symbol)`, daily-resampled
  (mean of hourly), z-scored per symbol column, missing values imputed to 0
  (post-standardization), symbols with fewer than `min_observations` (default
  30 daily observations) dropped.
- **PCA**: `sklearn.decomposition.PCA(n_components=10)`, full SVD.
- **NMF inputs**: per-symbol non-negative feature vector — `|mean(sentiment)|`,
  `mean(materiality)`, `mean(geo_risk)`, firing rate of each event flag. Scaled
  to [0, 1] per feature.
- **NMF**: `sklearn.decomposition.NMF(n_components=4, init='nndsvd',
  random_state=42)`. `n_components` exposed in sidebar.

### Tab 2 — Cohorts

> **Which symbols group together by sentiment co-movement and behavior?**

| # | Chart | Description | Cluster table? |
|---|---|---|---|
| 2.1 | **Raw correlation heatmap** — Spearman, symbols × symbols, alphabetically ordered | "Spearman correlation of daily-resampled sentiment between every pair of symbols, over the selected date range. Pairs with fewer than N joint observations are masked. This is your baseline — no clustering applied yet." | No |
| 2.2 | **Dendrogram-reordered correlation heatmap** | "Same correlations as 2.1, with rows and columns reordered by the dendrogram in 2.3. Block-diagonal structure reveals cohorts: dense red blocks = tightly co-moving groups; lighter off-block regions = cross-cohort independence." | YES — see 2.2.t |
| 2.2.t | **Cohort membership table** | Columns: `cluster_id`, `n_members`, `symbols` (comma-separated), `mean_intra_corr`, `mean_sector` (if symbols.csv has it). Sortable. | — |
| 2.3 | **Dendrogram** with adjustable cut-height slider | "Hierarchical clustering tree using Mantegna distance √(2(1−ρ)) and average linkage. The horizontal slider sets the cut height — lower cuts produce more, tighter clusters. The number of clusters in 2.2.t updates live with the slider." | No (table is 2.2.t) |
| 2.4 | **K-means tuning** — elbow (inertia) + silhouette overlaid on dual y-axis | "Inertia (left axis, decreasing) and silhouette score (right axis) for k = 2 to 10. Choose k where the elbow bends AND silhouette peaks. Defaults to argmax silhouette." | No |
| 2.5 | **K-means 2-D projection** — symbols projected via PCA, colored by cluster | "Each symbol projected onto the first two principal components, colored by its k-means cluster assignment. Use this to sanity-check that clusters are geometrically separable, not just label artifacts." | YES — see 2.5.t |
| 2.5.t | **K-means cluster membership table** | Columns: `cluster_id`, `n_members`, `symbols`, plus all centroid feature values. Sortable. | — |
| 2.6 | **Centroid feature heatmap** — clusters × features | "Each row is a cluster; each column a feature. Cell color shows the cluster centroid's value. This is the interpretable part — read across a row to name the cluster (e.g., 'high materiality + low confidence' = 'noisy hype-driven names')." | No |

**Algorithm details:**

- **Correlation**: Spearman on daily-resampled sentiment pivot, pairwise
  observations only, masked where N_joint < 20 (configurable).
- **Hierarchical**: `scipy.cluster.hierarchy.linkage(dist, method='average')`
  where `dist = squareform(sqrt(2 * (1 - corr_matrix.fillna(0))))`.
  Membership at slider's cut height via `fcluster`.
- **K-means inputs**: per-symbol feature vector (same shape as NMF input but
  z-scored, not [0,1]-scaled). Includes `std(sentiment)` in addition to mean.
- **K-means**: `KMeans(n_clusters=k, n_init=20, random_state=42)`. Silhouette
  via `sklearn.metrics.silhouette_score` on the same feature matrix.

### Tab 3 — Events

> **What event patterns travel together, and where do they fire?**

| # | Chart | Description | Cluster table? |
|---|---|---|---|
| 3.1 | **Flag co-occurrence heatmap** — 7×7 | "How often each pair of event flags fires in the same window. Diagonal shows raw firing counts; off-diagonal shows co-occurrence normalized by min(count_i, count_j) — a Jaccard-style score. High values reveal regime structure (e.g., `mna` + `regulatory_export` together signals deal-block risk)." | No |
| 3.2 | **Flag firing rate over time** — stacked area, monthly bins | "Share of windows in each month where each flag fires. Tells you which event types dominate which periods — `analyst_action` may dominate earnings season, `regulatory_export` may spike around policy events." | No |
| 3.3 | **Per-symbol flag firing rates** — symbols × flags heatmap | "For each symbol, the share of its windows where each flag fires. Reveals which symbols are 'M&A-prone', 'regulatory-exposed', etc. Sort the underlying table by any flag column." | YES — see 3.3.t |
| 3.3.t | **Per-symbol firing-rate table** | Columns: `symbol`, `n_windows`, and a column per flag with firing rate. Sortable. | — |

**No clustering on this tab** — the goal is descriptive surfacing of event
structure, not finding cohorts. Cohort discovery happens on Tab 2.

---

## 7. UX / UI conventions

### Sidebar (global filters, applies to all tabs)

- **Date range** — defaults to full coverage; date pickers labelled in UTC
- **Symbols** — multiselect; default ALL. Searchable.
- **Sector filter** — if `Claude/symbols.csv` exposes sectors, multiselect
- **Minimum article count per window** — slider 1–10, default 1
- **Aggregation grain** — radio: hourly | daily | weekly (default daily)
- **Status** — multiselect, default `['ok']` only
- **Score-source warning banner** — auto-shown if filtered data spans multiple
  `score_source` values, with a button to filter to just the latest

### Layout

- Wide layout (`st.set_page_config(layout='wide')`)
- Each chart in `st.container(border=True)` with vertical spacing
- Two-column grid where it improves density (e.g., 2.4 + 2.6 side-by-side);
  full-width for heatmaps and time series
- Use `st.spinner` for any computation > 1 s
- Use `st.progress` only for true long-running operations (none expected at
  current scale)

### Visual style

- Diverging color scale (red → white → green) for signed values (sentiment, PC
  loadings, correlation). Anchored at 0.
- Sequential color scale (white → dark blue) for [0,1] non-negative values
  (materiality, geo_risk, NMF weights, firing rates).
- Cluster colors: Plotly qualitative palette, **fixed mapping by cluster_id**
  so cluster 1 is the same color in every chart on a tab.
- No emojis anywhere in UI text.
- Font: Streamlit default. Don't ship custom CSS unless something is
  unreadable.

### Tables (the hard requirement)

Every clustering chart has its membership table immediately beneath it. Tables:

- Use `st.dataframe(hide_index=True, use_container_width=True)`
- Default-sort by `cluster_id` ascending
- Include a `n_members` column so the user can eyeball balance
- For the `symbols` column, render as a single comma-separated string (not a
  list / pill / chip) so the table is searchable and copyable
- Add a `Download CSV` button (`st.download_button`) for each table

---

## 8. Data processing pipeline

Centralize in `src/papier/analytics/data.py`. All loaders take the same
`Filters` dataclass so caching keys are uniform.

```python
@dataclass(frozen=True)
class Filters:
    date_start: date | None
    date_end: date | None
    symbols: tuple[str, ...] | None  # None = all
    sectors: tuple[str, ...] | None
    min_article_count: int = 1
    grain: Literal["hourly", "daily", "weekly"] = "daily"
    status: tuple[str, ...] = ("ok",)
```

Functions (all `@st.cache_data`-wrapped at the dashboard layer):

- `load_sentiment(filters) -> pd.DataFrame` — long format
- `pivot_sentiment(filters) -> pd.DataFrame` — index=time, columns=symbol
- `per_symbol_features(filters) -> pd.DataFrame` — one row per symbol with
  mean/std sentiment, materiality mean, geo_risk mean, per-flag firing rates,
  total article count, distinct source count
- `correlation_matrix(filters) -> pd.DataFrame` — Spearman, joint-N masked

**Daily resampling rule**: per symbol, the daily sentiment for day D is the
article-count-weighted mean of all hourly windows whose `window_start` falls
on D (UTC). Days with zero articles for a symbol are NaN, not 0.

---

## 9. Analytical modules

### `factors.py`

```python
def run_pca(pivot: pd.DataFrame, *, min_obs: int = 30, n_components: int = 10) -> PCAResult:
    """Returns explained_variance_, loadings (symbols × PC), scores (time × PC),
    and the dropped-symbols list."""

def run_nmf(features: pd.DataFrame, *, n_components: int = 4) -> NMFResult:
    """Returns components (components × features) and symbol_weights
    (symbols × components)."""
```

### `cohorts.py`

```python
def hierarchical_cluster(corr: pd.DataFrame, *, cut_height: float) -> HierarchicalResult:
    """Returns linkage matrix, cluster labels at cut_height, reordered symbol
    order, and a membership DataFrame."""

def kmeans_cluster(features: pd.DataFrame, *, k_range: range = range(2, 11),
                   k: int | None = None) -> KMeansResult:
    """Returns inertia and silhouette per k, chosen k (argmax silhouette if
    k=None), cluster labels, centroids, 2-D PCA projection, and a membership
    DataFrame."""
```

### `events.py`

```python
def flag_cooccurrence(df: pd.DataFrame) -> pd.DataFrame:
    """Returns a 7×7 DataFrame, diagonal = counts, off-diagonal = Jaccard."""

def firing_rates_over_time(df: pd.DataFrame, *, freq: str = "M") -> pd.DataFrame:
    """Returns DataFrame with one column per flag, index=period."""

def firing_rates_per_symbol(df: pd.DataFrame) -> pd.DataFrame:
    """Returns DataFrame with one row per symbol, one column per flag."""
```

All of these are pure functions of the inputs — no globals, no DB access. The
DB access lives in `data.py` only.

---

## 10. Chart descriptions — static vs LLM-generated

The user explicitly allowed LLM-generated text *"if relevant and helpful."*
Recommended two-layer approach:

**Layer 1 — Static "how to read this" text.** Hand-written, lives in
`descriptions.py` as a dict keyed by `chart_id`. Always shown. Never changes.

```python
DESCRIPTIONS = {
    "pca_scree": "Each bar is the share of cross-sectional sentiment...",
    ...
}
```

**Layer 2 — Dynamic "what this particular chart is saying" takeaway.**
Optional. Generated by local Ollama from a structured summary of the chart's
numerics (NOT from the raw data — keep prompts small and cheap). Cached in
`data/cache/descriptions.json` keyed by `(chart_id, data_hash)` so the user
isn't waiting on Ollama on every page render.

Example for PCA scree:
```
Input to LLM: {"chart": "pca_scree", "evr": [0.42, 0.13, 0.08, 0.05, ...],
               "n_symbols": 173, "date_range": "2024-01..2026-06"}
Output (cached): "The first component explains 42% of variance — a single
dominant sentiment factor, likely market-wide tone. Components 2-3 add
another 21%, consistent with sector cohorts (defense vs mining/tech). The
flat tail past PC4 suggests further components are idiosyncratic noise."
```

Implementation rules:

- Wrap in a feature flag (`st.toggle("Show AI takeaways", value=True)` in the
  sidebar). Defaults on, but the dashboard must render correctly with it off.
- Strict JSON-out from Ollama (matches the rest of the codebase's contract).
- Single retry on malformed output; fallback to "AI takeaway unavailable" text.
- Never write LLM output to `papier.db`. Only to `data/cache/descriptions.json`.
- Use the same Ollama model id that produced the scored data (read from
  distinct `score_source` values) so descriptions are framed in terms the
  scoring model would recognize.

If implementing Layer 2 adds material complexity in v1, ship without it —
Layer 1 alone meets the user's stated requirement of "description under each
chart." Layer 2 is a polish step.

---

## 11. Testing plan

- `tests/test_analytics_data.py` — fixture DB with 10 symbols / 100 windows;
  assert pivot shape, NaN behavior, daily resampling correctness, status
  filter, score-source warning trigger.
- `tests/test_analytics_factors.py` — PCA on a synthetic pivot with one
  injected factor; assert PC1 explains > 70% of variance and loadings align
  with the injected pattern. Same for NMF with synthetic themes.
- `tests/test_analytics_cohorts.py` — synthetic correlation matrix with two
  obvious blocks; assert hierarchical and k-means both recover them.
- `tests/test_analytics_events.py` — synthetic flag matrix with known
  co-firings; assert Jaccard values match by hand.
- **Smoke test**: `streamlit run scripts/dashboard.py --server.headless true`
  loads against real `data/papier.db` without error; cycle through all three
  tabs; verify no console exceptions.

No visual regression testing in v1 — Streamlit's screenshot test utilities are
new and brittle.

---

## 12. Performance budget

| Operation | Target | Mitigation if exceeded |
|---|---|---|
| Cold load (full universe, full range) | < 3 s | Parquet cache pivots under `data/cache/` |
| Filter change | < 1 s | Ensure `@st.cache_data` is keyed correctly |
| PCA / NMF / KMeans fit | < 500 ms | Already trivial at 173 symbols |
| Correlation matrix | < 500 ms | pandas Spearman is fast at this scale |
| Ollama description (per chart, uncached) | < 5 s | Cache aggressively; show spinner |

Current scale (~6,700 rows) is far below any concern. Re-evaluate at 10× data.

---

## 13. Out of scope for v1

- Auto-refresh on DB changes (Streamlit's file watcher is acceptable; cron
  not).
- Article-level drill-down (PAPIER does not store article text — out of scope
  by design).
- Cross-symbol pair-trade suggestions (QARSA's domain — hard rule against
  coupling).
- Exporting charts as static images for reports (Plotly's built-in export
  button is sufficient).
- Multi-user state, auth, deployment. Local-only.

---

## 14. Handoff checklist for the next session

Before that session starts, the user should confirm:

- [ ] Streamlit is acceptable as the framework (vs notebook / static HTML)
- [ ] LLM-generated Layer 2 takeaways are in or out for v1
- [ ] `data/cache/` is the right place for caches (vs e.g. `Claude/cache/`)
- [ ] Sector annotations come from `Claude/symbols.csv` — column name confirmed

In the next session, build in this order (each step is testable in isolation):

1. Scaffold `src/papier/analytics/` package + skeleton functions returning
   stubs. Add tests.
2. Implement `data.py`. Verify against `data/papier.db` in a REPL.
3. Implement `events.py` (simplest analytics). Build Tab 3 first — smallest
   surface area, validates the chrome / description pattern.
4. Implement `cohorts.py`. Build Tab 2. This is the most chart-dense tab; once
   it works the rest is mechanical.
5. Implement `factors.py`. Build Tab 1.
6. (Optional) Implement `llm_interpret.py` and wire Layer 2 descriptions.
7. Add `[viz]` to `pyproject.toml`, add `data/cache/` to `.gitignore`, update
   `README.md` with launch instructions.
8. Run the smoke test and manually walk all three tabs.
