"""Symbol → sector classification.

PAPIER doesn't store sector per symbol. This module owns the mapping for the
dashboard's needs (Sector Lens, treemap grouping, mover sector tags). Unknown
symbols default to "Other". Hand-edit freely.

Sectors match the handoff design system's four buckets:
  Defense · Mining · Tech · Materials · Other
"""

SECTOR_OF: dict[str, str] = {
    # ---- Defense ----
    "LMT": "Defense", "RTX": "Defense", "NOC": "Defense", "GD": "Defense",
    "BA":  "Defense", "LHX": "Defense", "HII": "Defense", "LDOS": "Defense",
    "KTOS": "Defense", "AVAV": "Defense", "BWXT": "Defense", "TXT": "Defense",
    "CW":  "Defense", "HEI": "Defense", "TDG": "Defense", "AXON": "Defense",
    "PLTR": "Defense", "MRCY": "Defense", "CACI": "Defense", "SAIC": "Defense",
    "BAH": "Defense", "CAE": "Defense", "OSK": "Defense", "HWM": "Defense",
    "RKLB": "Defense", "ASTS": "Defense", "VSAT": "Defense", "KBR": "Defense",
    "ACHR": "Defense", "JOBY": "Defense", "ONDS": "Defense", "RCAT": "Defense",
    "UMAC": "Defense", "USAR": "Defense", "RDAC": "Defense", "OPTX": "Defense",
    "SEGG": "Defense",

    # ---- Mining ----
    "FCX": "Mining", "NEM": "Mining", "SCCO": "Mining", "RIO": "Mining",
    "BHP": "Mining", "TECK": "Mining", "HL": "Mining", "CDE": "Mining",
    "PAAS": "Mining", "WPM": "Mining", "FNV": "Mining", "AEM": "Mining",
    "KGC": "Mining", "AU": "Mining", "HMY": "Mining", "CCJ": "Mining",
    "UUUU": "Mining", "MP": "Mining", "LAC": "Mining", "SQM": "Mining",
    "RGLD": "Mining", "ARLP": "Mining", "HBM": "Mining", "IAG": "Mining",
    "IDR": "Mining", "AGI": "Mining", "AA": "Mining", "ALB": "Mining",
    "EXP": "Mining", "MLM": "Mining", "VMC": "Mining", "VLO": "Mining",
    "GLNCY": "Mining", "AAUKF": "Mining", "ANGPY": "Mining", "AIAGY": "Mining",
    "BDNNY": "Mining", "BIYA": "Mining", "CHHQY": "Mining", "CMCLY": "Mining",
    "EDVMF": "Mining", "FQVLF": "Mining", "GMBXF": "Mining", "GPHOF": "Mining",
    "GPMXY": "Mining", "IMPUY": "Mining", "IPOAF": "Mining", "IVPAF": "Mining",
    "JXAMY": "Mining", "LNDMY": "Mining", "LUGDF": "Mining", "LUNMF": "Mining",
    "LYSCF": "Mining", "LYSDY": "Mining", "MMSMY": "Mining", "NB": "Mining",
    "OCG": "Mining", "PPTA": "Mining", "REEMF": "Mining", "RYOJ": "Mining",
    "SDOT": "Mining", "SMMYY": "Mining", "SOUHY": "Mining", "TJGC": "Mining",
    "TMC": "Mining", "TMQ": "Mining", "TMRC": "Mining", "UAMY": "Mining",
    "UURAF": "Mining", "ZIJMY": "Mining", "CRML": "Mining", "ALOY": "Mining",
    "ALM": "Mining", "ASPI": "Mining", "WWR": "Mining", "POM": "Mining",
    "USLM": "Mining", "WTI": "Mining", "ICL": "Mining", "MOS": "Mining",
    "CF": "Mining",

    # ---- Tech ----
    "NVDA": "Tech", "AMD": "Tech", "INTC": "Tech", "MSFT": "Tech",
    "AAPL": "Tech", "GOOG": "Tech", "GOOGL": "Tech", "AMZN": "Tech",
    "META": "Tech", "AVGO": "Tech", "MU": "Tech", "ASML": "Tech",
    "SMCI": "Tech", "ARM": "Tech", "CSCO": "Tech", "MRVL": "Tech",
    "AMAT": "Tech", "LRCX": "Tech", "ZS": "Tech", "DDOG": "Tech",
    "NFLX": "Tech", "INTU": "Tech", "COIN": "Tech", "HOOD": "Tech",
    "MSTR": "Tech", "APLD": "Tech", "MARA": "Tech", "ENPH": "Tech",
    "SEDG": "Tech", "BRAI": "Tech", "POET": "Tech", "BRLS": "Tech",
    "HCAI": "Tech", "DGNX": "Tech", "EZGO": "Tech", "VLN": "Tech",
    "VISN": "Tech", "BAND": "Tech", "ATER": "Tech", "KFRC": "Tech",
    "LTRX": "Tech", "STEX": "Tech", "SIMO": "Tech", "PAPL": "Tech",
    "TEAM": "Tech", "RIVN": "Tech", "TSLA": "Tech", "CHTR": "Tech",
    "PYPL": "Tech", "SHFS": "Tech", "SNBR": "Tech", "TNDM": "Tech",
    "SOBR": "Tech", "PHGE": "Tech", "PBM": "Tech", "MANE": "Tech",
    "SKLZ": "Tech", "TENX": "Tech", "VSA": "Tech", "WMT": "Tech",
    "COST": "Tech",

    # ---- Materials (broadened to cover chemicals, fertilizers, building products) ----
    "B": "Materials", "AZN": "Materials", "MRNA": "Materials",
    "PBF": "Materials", "FGI": "Materials", "CMP": "Materials",
    "CREG": "Materials", "ERAS": "Materials", "ESPR": "Materials",
    "ATRA": "Materials", "AREB": "Materials", "EDSA": "Materials",
    "SNGX": "Materials", "TRDA": "Materials", "XTLB": "Materials",
    "RPGL": "Materials", "OSRH": "Materials", "CMPX": "Materials",
    "HTCO": "Materials", "CHSN": "Materials", "UBXG": "Materials",
    "YSS": "Materials", "YAAS": "Materials", "IPX": "Materials",
}


def sector_of(symbol: str) -> str:
    """Return the configured sector for a symbol, defaulting to 'Other'."""
    return SECTOR_OF.get(symbol.upper(), "Other")


def all_sectors() -> tuple[str, ...]:
    """Canonical display order — matches design-system sector identity colors."""
    return ("Defense", "Mining", "Tech", "Materials", "Other")
