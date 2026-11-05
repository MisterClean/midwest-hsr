"""Paths and configuration loading for the Midwest HSR pipeline."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("HSR_ROOT", Path(__file__).resolve().parents[2]))
CONFIG = ROOT / "config"
DATA = ROOT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"
WEB = ROOT / "web"
WEB_DATA = WEB / "data"

# Equal-area projection for lengths, areas and buffers (meters).
CRS_METERS = "EPSG:5070"
CRS_LONLAT = "EPSG:4326"

OFFICES = ("us_house", "state_senate", "state_house")
STATEWIDE = ("us_senate", "governor")


def ensure_dirs() -> None:
    for d in (RAW, INTERIM, PROCESSED, WEB_DATA):
        d.mkdir(parents=True, exist_ok=True)


@lru_cache
def load_yaml(name: str) -> dict:
    with open(CONFIG / name, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def states() -> dict:
    return load_yaml("states.yaml")["states"]


def fips_to_usps() -> dict[str, str]:
    return {v["fips"]: k for k, v in states().items()}


def chamber_sizes() -> dict:
    return load_yaml("states.yaml")["chamber_sizes"]


def sources() -> dict:
    return load_yaml("sources.yaml")


@dataclass(frozen=True)
class Station:
    id: str
    name: str
    state: str
    lat: float
    lon: float
    kind: str
    amtrak: str | None = None


def stations() -> dict[str, Station]:
    raw = load_yaml("stations.yaml")["stations"]
    return {k: Station(id=k, **v) for k, v in raw.items()}


def corridors() -> list[dict]:
    return load_yaml("corridors.yaml")["corridors"]


def corridor_sources() -> dict:
    return load_yaml("corridors.yaml")["sources"]


def write_json(path: Path, obj, *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        if compact:
            json.dump(obj, fh, separators=(",", ":"), ensure_ascii=False)
        else:
            json.dump(obj, fh, indent=2, ensure_ascii=False)
