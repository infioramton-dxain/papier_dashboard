"""Latent-structure analytics over PAPIER's sentiment table.

Pure-function modules — no Streamlit, no caching, no DB access except through
data.py's loaders. Importable from notebooks and unit tests. Wrapped in
`@st.cache_data` at the view layer in src/signal_terminal/views/.

Three analytical questions, one module each:

- data.py     — Filters dataclass + DB → DataFrame loaders
- factors.py  — PCA + NMF        (what latent drivers exist?)
- cohorts.py  — hierarchical + k-means (which symbols group together?)
- events.py   — flag co-occurrence + firing rates (what event patterns travel together?)
"""

from signal_terminal.analytics.data import Filters

__all__ = ["Filters"]
