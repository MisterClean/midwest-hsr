"""Download every external input, authoritative source first, mirror second.

Each successful download is recorded in data/raw/MANIFEST.json with its URL, size,
SHA-256 and timestamp, so a run can be audited and repeated.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import shutil
import subprocess
from pathlib import Path

import requests

from . import config as C

log = logging.getLogger(__name__)
MANIFEST = C.RAW / "MANIFEST.json"
UA = {"User-Agent": "midwest-hsr-pipeline/0.1 (+https://github.com/MisterClean/midwest-hsr)"}


# --------------------------------------------------------------------------- utils
def _manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text())
    return {}


def _record(key: str, **entry) -> None:
    m = _manifest()
    m[key] = entry | {"fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    C.write_json(MANIFEST, m)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path, *, timeout: int = 300) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=timeout, headers=UA) as r:
        r.raise_for_status()
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
    tmp.replace(dest)
    return dest


def first_working(key: str, candidates: list[tuple[str, Path, dict]]) -> tuple[Path, dict]:
    """Try (url, dest, meta) candidates in order; return the first that downloads."""
    errors = []
    for url, dest, meta in candidates:
        if dest.exists() and dest.stat().st_size > 0:
            log.info("cached %s -> %s", key, dest)
            m = _manifest().get(key, {})
            if m.get("path") == str(dest.relative_to(C.ROOT)):
                return dest, m
        try:
            log.info("fetch %s <- %s", key, url)
            download(url, dest)
            entry = {"url": url, "path": str(dest.relative_to(C.ROOT)), "bytes": dest.stat().st_size,
                     "sha256": sha256(dest)} | meta
            _record(key, **entry)
            return dest, entry
        except Exception as exc:  # noqa: BLE001 - we want to fall through to the mirror
            errors.append(f"{url}: {exc}")
            log.warning("failed %s: %s", url, exc)
    raise RuntimeError(f"all sources failed for {key}:\n  " + "\n  ".join(errors))


# --------------------------------------------------------------------- boundaries
def fetch_boundaries(year: int | None = None, mirror_only: bool = False) -> dict:
    """Census cartographic boundary files for districts and states."""
    src = C.sources()["boundaries"]
    year = year or src["vintage"]
    mirror = src["mirror"]
    out = {}
    for layer in ("congress", "state_senate", "state_house", "states"):
        cands = []
        if not mirror_only:
            for tmpl in src[layer]["urls"]:
                url = tmpl.format(year=year)
                cands.append((url, C.RAW / "boundaries" / Path(url).name, {"vintage": year, "mirror": False}))
        fname = mirror["files"][layer]
        cands.append((f"{mirror['base']}/{fname}", C.RAW / "boundaries" / fname,
                      {"vintage": mirror["vintage"], "mirror": True}))
        path, entry = first_working(f"boundaries.{layer}", cands)
        out[layer] = {"path": path, "vintage": entry.get("vintage"), "mirror": entry.get("mirror")}
    return out


# ------------------------------------------------------------------------ rosters
def fetch_rosters(openstates_ref: str = "main", congress_ref: str = "main") -> dict:
    """Sitting members before the election (U.S. Congress + state legislatures + governors)."""
    ro = C.sources()["rosters"]
    cl_url = (ro["congress_legislators"]["repo"].replace("github.com", "raw.githubusercontent.com")
              + f"/{congress_ref}/{ro['congress_legislators']['file']}")
    cl_path, _ = first_working("rosters.congress_legislators",
                               [(cl_url, C.RAW / "rosters" / "legislators-current.yaml", {"ref": congress_ref})])

    dest = C.RAW / "rosters" / "openstates-people"
    st = [s.lower() for s in C.states()]
    paths = [f"data/{s}/legislature" for s in st] + [f"data/{s}/executive" for s in st]
    if not (dest / ".git").exists():
        if dest.exists():
            shutil.rmtree(dest)
        subprocess.run(["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", "--branch",
                        openstates_ref, ro["openstates_people"]["repo"], str(dest)], check=True)
    subprocess.run(["git", "-C", str(dest), "sparse-checkout", "set", *paths], check=True)
    sha = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"], check=True,
                         capture_output=True, text=True).stdout.strip()
    date = subprocess.run(["git", "-C", str(dest), "log", "-1", "--format=%cI"], check=True,
                          capture_output=True, text=True).stdout.strip()
    _record("rosters.openstates_people", url=ro["openstates_people"]["repo"], path=str(dest.relative_to(C.ROOT)),
            commit=sha, commit_date=date)
    return {"congress": cl_path, "openstates": dest, "openstates_commit": sha}


# --------------------------------------------------------------------------- rail
def _arcgis_geojson(url: str, bbox: list[float], where: str = "1=1", page: int = 2000) -> dict:
    feats, offset = [], 0
    while True:
        params = {
            "where": where, "outFields": "*", "f": "geojson", "outSR": 4326,
            "geometry": ",".join(map(str, bbox)), "geometryType": "esriGeometryEnvelope",
            "inSR": 4326, "spatialRel": "esriSpatialRelIntersects",
            "resultOffset": offset, "resultRecordCount": page,
        }
        r = requests.get(url.rstrip("/") + "/query", params=params, timeout=300, headers=UA)
        r.raise_for_status()
        js = r.json()
        batch = js.get("features", [])
        feats.extend(batch)
        if len(batch) < page and not js.get("exceededTransferLimit"):
            break
        offset += len(batch)
    return {"type": "FeatureCollection", "features": feats}


def fetch_rail(mirror_only: bool = False) -> dict:
    """Rail network for routing: BTS NTAD North American Rail Network, else Natural Earth."""
    rs = C.sources()["rail"]
    bbox = C.load_yaml("states.yaml")["bbox"]
    out: dict = {}
    if not mirror_only:
        try:
            dest = C.RAW / "rail" / "ntad_narn_lines.geojson"
            if not dest.exists():
                # Pull everything in the bbox; routing.py drops yards/abandoned track.
                fc = _arcgis_geojson(rs["narn_lines"]["url"], bbox)
                if not fc["features"]:
                    raise RuntimeError("NARN query returned no features")
                C.write_json(dest, fc, compact=True)
                _record("rail.network", url=rs["narn_lines"]["url"], path=str(dest.relative_to(C.ROOT)),
                        features=len(fc["features"]), sha256=sha256(dest), source="ntad")
            out["network"], out["network_source"] = dest, "ntad"
        except Exception as exc:  # noqa: BLE001
            log.warning("NTAD rail network unavailable (%s); falling back to Natural Earth", exc)
    if "network" not in out:
        path, _ = first_working("rail.network", [(rs["natural_earth_railroads"]["url"],
                                                  C.RAW / "rail" / "ne_10m_railroads.geojson",
                                                  {"source": "natural_earth"})])
        out["network"], out["network_source"] = path, "natural_earth"
    path, _ = first_working("rail.lakes", [(rs["natural_earth_lakes"]["url"],
                                            C.RAW / "rail" / "ne_10m_lakes.geojson", {})])
    out["lakes"] = path
    if not mirror_only:
        try:
            dest = C.RAW / "rail" / "ntad_amtrak_stations.geojson"
            if not dest.exists():
                fc = _arcgis_geojson(rs["amtrak_stations"]["url"], bbox)
                C.write_json(dest, fc, compact=True)
                _record("rail.amtrak_stations", url=rs["amtrak_stations"]["url"],
                        path=str(dest.relative_to(C.ROOT)), features=len(fc["features"]))
            out["amtrak_stations"] = dest
        except Exception as exc:  # noqa: BLE001
            log.warning("NTAD Amtrak stations unavailable (%s); using config/stations.yaml coordinates", exc)
    return out


def fetch_all(mirror_only: bool = False) -> dict:
    C.ensure_dirs()
    return {
        "boundaries": fetch_boundaries(mirror_only=mirror_only),
        "rosters": fetch_rosters(),
        "rail": fetch_rail(mirror_only=mirror_only),
    }
