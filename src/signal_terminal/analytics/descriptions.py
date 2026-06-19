"""Static 'how to read this chart' text per chart_id.

Layer 1 of the two-layer description scheme (see spec §10). Hand-written, never
changes at runtime. Layer 2 dynamic takeaways live in llm_interpret.py.

Keep these accurate to the *visualization*, not the data — they should hold
even when the dataset grows.
"""

DESCRIPTIONS: dict[str, str] = {
    # ---------- Factors ----------
    "pca_scree": (
        "Each bar is the share of cross-sectional sentiment variance captured "
        "by that principal component. A tall first bar means one dominant "
        "driver (likely market-wide sentiment); a flat tail means symbol-"
        "idiosyncratic noise dominates. Use this to decide how many components "
        "are worth interpreting."
    ),
    "pca_loadings": (
        "Each cell is symbol s's loading on principal component k. Green = "
        "positive exposure to that factor, red = negative. Read down a column "
        "to see what kind of symbols define each factor; read across a row to "
        "see a symbol's factor fingerprint."
    ),
    "pca_biplot": (
        "Each dot is a symbol placed by its loading on the first two factors. "
        "Symbols near each other share latent drivers. Sector coloring lets "
        "you see whether factors align with industry groupings or cut across "
        "them."
    ),
    "pca_scores": (
        "The latent factors themselves moving through time. Spikes in PC1 "
        "typically correspond to market-wide sentiment events; PC2/PC3 spikes "
        "are usually sector or theme events. Cross-reference dates with known "
        "news to label what each factor 'is.'"
    ),
    "nmf_components": (
        "Non-negative matrix factorization finds additive 'themes' in symbol "
        "behavior. Each row is a theme (e.g., 'high materiality + regulatory + "
        "analyst action'); cell intensity shows how strongly that feature "
        "defines the theme. Easier to read than PCA loadings because there are "
        "no canceling signs."
    ),
    "nmf_weights": (
        "Each symbol's mix of themes. Sortable by any theme column. A symbol "
        "can load on multiple themes simultaneously — unlike clustering, this "
        "is a soft assignment."
    ),

    # ---------- Cohorts ----------
    "corr_raw": (
        "Spearman correlation of resampled sentiment between every pair of "
        "symbols, over the selected date range. Pairs with fewer than 20 "
        "joint observations are masked. This is your baseline — no clustering "
        "applied yet."
    ),
    "corr_reordered": (
        "Same correlations as the raw heatmap, with rows and columns reordered "
        "by the dendrogram below. Block-diagonal structure reveals cohorts: "
        "dense green blocks = tightly co-moving groups; lighter off-block "
        "regions = cross-cohort independence."
    ),
    "dendrogram": (
        "Hierarchical clustering tree using Mantegna distance √(2(1−ρ)) and "
        "average linkage. The slider above sets the cut height — lower cuts "
        "produce more, tighter clusters. The cohort table updates live with "
        "the slider."
    ),
    "kmeans_tuning": (
        "Inertia (left axis, decreasing) and silhouette score (right axis) "
        "for k = 2 to 10. Choose k where the elbow bends AND silhouette "
        "peaks. Defaults to argmax silhouette."
    ),
    "kmeans_projection": (
        "Each symbol projected onto the first two principal components of the "
        "feature matrix, colored by its k-means cluster assignment. Use this "
        "to sanity-check that clusters are geometrically separable, not just "
        "label artifacts."
    ),
    "kmeans_centroids": (
        "Each row is a cluster; each column a feature. Cell color shows the "
        "cluster centroid's value. This is the interpretable part — read "
        "across a row to name the cluster (e.g., 'high materiality + low "
        "confidence' = 'noisy hype-driven names')."
    ),

    # ---------- Events ----------
    "flag_cooccurrence": (
        "How often each pair of event flags fires in the same window. The "
        "diagonal shows raw firing counts; off-diagonal cells show co-occurrence "
        "normalized by min(count_i, count_j) — a min-Jaccard score. High values "
        "reveal regime structure (e.g., M&A + regulatory/export together "
        "signals deal-block risk)."
    ),
    "flag_over_time": (
        "Share of windows in each month where each flag fires. Tells you which "
        "event types dominate which periods — analyst actions may dominate "
        "earnings season, regulatory/export may spike around policy events."
    ),
    "flag_per_symbol": (
        "For each symbol, the share of its windows where each flag fires. "
        "Reveals which symbols are 'M&A-prone', 'regulatory-exposed', etc. "
        "Sort the underlying table by any flag column."
    ),
}


def get(chart_id: str) -> str:
    """Look up the static description for `chart_id`; empty string if missing."""
    return DESCRIPTIONS.get(chart_id, "")
