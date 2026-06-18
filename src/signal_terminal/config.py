import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    db_path: Path
    live: bool
    fallback_to_mock: bool
    recency_hours: int
    default_tab: str
    cache_ttl_seconds: int
    symbols_csv: Path | None


def load(path: str | Path = "config.toml") -> Config:
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    with p.open("rb") as f:
        raw = tomllib.load(f)
    symbols_csv_str = raw.get("universe", {}).get("symbols_csv", "")
    return Config(
        db_path=Path(raw["paper"]["db"]).expanduser(),
        live=bool(raw["data"]["live"]),
        fallback_to_mock=bool(raw["data"]["fallback_to_mock"]),
        recency_hours=int(raw["ui"]["recency_hours"]),
        default_tab=raw["ui"]["default_tab"],
        cache_ttl_seconds=int(raw["ui"]["cache_ttl_seconds"]),
        symbols_csv=Path(symbols_csv_str).expanduser() if symbols_csv_str else None,
    )
