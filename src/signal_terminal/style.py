"""Design tokens, Plotly layout, sentiment ramp helpers.

Authoritative for tokens — every color, font, and spacing reference in the app
goes through this module. If the design system file ever moves, this file moves
in lockstep.
"""
import math

# --- surfaces & structure ---
BG          = "#0d1117"
BG_CHROME   = "#0b0f14"
SURFACE     = "#0a0e13"
SURFACE_2   = "#11161d"
INPUT       = "#161b22"
BORDER      = "#1f2630"
BORDER_HI   = "#2b333d"
GRIDCOLOR   = "#181e27"

# --- text ---
TEXT_HI     = "#e6edf3"
TEXT        = "#c9d1d9"
DIM         = "#8b949e"
FAINT       = "#6e7681"
FAINTER     = "#4d5560"

# --- semantic ---
POSITIVE    = "#30a46c"
NEGATIVE    = "#e5484d"
NEUTRAL     = "#2b323c"
WARN        = "#d29922"
FRESH       = "#00e5ff"   # < 1h only — reserved for "just happened"

# --- sector identity (categorical) ---
SECTOR_COLOR = {
    "Defense":   "#6ea8fe",
    "Mining":    "#e0a458",
    "Tech":      "#bb9af7",
    "Materials": "#7ec9c9",
    "Other":     "#4d5560",
}

# --- drop-reason colors ---
DROP_REASON_COLOR = {
    "parse_error":   "#e5484d",
    "rate_limit":    "#d29922",
    "dedup":         "#6ea8fe",
    "dup_title":     "#6ea8fe",  # PAPIER's actual reason name
    "fetch_timeout": "#bb9af7",
    "paywall":       "#7ec9c9",
    "over_cap":      "#7ec9c9",
    "late":          "#bb9af7",
}

# --- sentiment ramp ---
# Plotly colorscale: normalize sentiment [-1, 1] → [0, 1].
SENTIMENT_COLORSCALE = [
    [0.0, NEGATIVE],
    [0.5, NEUTRAL],
    [1.0, POSITIVE],
]


def _mix(c1: str, c2: str, t: float) -> str:
    """Linear RGB mix of two #rrggbb colors at fraction t∈[0,1]."""
    a = (int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16))
    b = (int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16))
    out = tuple(int(round(a[i] * (1 - t) + b[i] * t)) for i in range(3))
    return f"#{out[0]:02x}{out[1]:02x}{out[2]:02x}"


def sentiment_color(v: float | None) -> str:
    """Tile fill from sentiment value with sqrt easing (keeps small signals visible).

    None -> '#171c24' (per design system § sentiment ramp null case).
    """
    if v is None:
        return "#171c24"
    v = max(-1.0, min(1.0, float(v)))
    if v >= 0:
        return _mix(NEUTRAL, POSITIVE, math.sqrt(v))
    return _mix(NEUTRAL, NEGATIVE, math.sqrt(-v))


# --- Plotly shared layout ---
# Every chart starts from this dict; copy and customize axis labels only.
LAYOUT = dict(
    paper_bgcolor=SURFACE,
    plot_bgcolor=SURFACE,
    font=dict(family="JetBrains Mono, monospace", color=DIM, size=11),
    margin=dict(l=46, r=16, t=12, b=30),
    xaxis=dict(gridcolor=GRIDCOLOR, zerolinecolor=BORDER_HI, linecolor=BORDER_HI),
    yaxis=dict(gridcolor=GRIDCOLOR, zerolinecolor=BORDER_HI, linecolor=BORDER_HI),
    hoverlabel=dict(bgcolor=INPUT, bordercolor=BORDER_HI, font=dict(family="JetBrains Mono")),
    showlegend=False,
)

PLOTLY_CONFIG = {"displayModeBar": False}


def layout(**overrides) -> dict:
    """Build a Plotly layout dict starting from LAYOUT, applying overrides.

    Use this everywhere instead of `**LAYOUT, foo=bar` to avoid duplicate-kwarg
    TypeErrors when an override key (margin, xaxis, yaxis, ...) is already in LAYOUT.
    Nested keys (xaxis/yaxis) replace, not merge — pass the full dict you want.
    """
    return {**LAYOUT, **overrides}


# --- type scale (px / weight) ---
class Type:
    HERO = (30, 700)              # symbol ticker, hero value
    PIPELINE_METRIC = (27, 700)
    FLAG_COUNTER = (25, 700)
    QA_VALUE = (23, 700)
    SECTOR_METRIC = (20, 700)
    BRAND = (16, 700)
    DETAIL_VALUE = (15, 600)
    BODY_EM = (13, 600)
    BODY = (11, 400)
    SECTION_LABEL = (10, 600)     # uppercase, +1.5px tracking
    MICRO = (9, 600)


# --- spacing tokens ---
GUTTER = 11
INNER_GAP = 8
PANEL_PAD = 12
TILE_GRID = (58, 30)
TILE_SECTOR = (52, 28)


# --- event flag display labels ---
EVENT_LABEL = {
    "contract_award":    "CONTRACT",
    "guidance":          "GUIDANCE",
    "mna":               "M&A",
    "regulatory_export": "REG/EXPORT",
    "litigation":        "LITIGATION",
    "analyst_action":    "ANALYST",
    "commodity_move":    "COMMODITY",
}

EVENT_FLAGS = tuple(EVENT_LABEL.keys())
