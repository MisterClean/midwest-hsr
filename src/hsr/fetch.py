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
from concurrent.futures import ThreadPoolExecutor
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
            fh.writelines(r.iter_content(1 << 20))
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
def fetch_tigerweb_layer(layer: str, src: dict) -> tuple[Path, dict]:
    """Fetch complete 2026 district GeoJSON, one state at a time."""
    cfg = src["tigerweb"]
    vintage = cfg["vintage"]
    source = f"tigerweb-{vintage}"
    dest = C.RAW / "boundaries" / f"{layer}_{vintage}.geojson"
    key = f"boundaries.{layer}"
    cached = _manifest().get(key, {})
    if (dest.exists() and cached.get("path") == str(dest.relative_to(C.ROOT))
            and cached.get("source") == source and cached.get("sha256") == sha256(dest)):
        log.info("cached %s -> %s", key, dest)
        return dest, cached

    def get_state(item: tuple[str, dict]) -> tuple[str, list[dict], str]:
        st, state = item
        fips = state["fips"]
        layer_id = cfg["missouri_congress_layer"] if layer == "congress" and st == "MO" else cfg["layers"][layer]
        field = "CD119" if layer == "congress" and st == "MO" else {
            "congress": "CD120", "state_senate": "SLDU", "state_house": "SLDL"}[layer]
        url = f"{cfg['base']}/{layer_id}/query"
        params = {"where": f"STATE='{fips}'", "outFields": "*", "returnGeometry": "true",
                  "outSR": 4326, "f": "geojson"}
        response = requests.get(url, params=params, headers=UA, timeout=180)
        response.raise_for_status()
        data = response.json()
        features = data.get("features")
        if isinstance(features, list):
            features = [f for f in features if not str(f.get("properties", {}).get(field, "")).upper().startswith("ZZ")]
        expected = (state["house_seats"] if layer == "congress" else
                    C.chamber_sizes()[st]["state_senate" if layer == "state_senate" else "state_house"])
        if data.get("type") != "FeatureCollection" or not isinstance(features, list) or len(features) != expected:
            raise ValueError(f"{layer} {st}: expected {expected} features, got {len(features) if isinstance(features, list) else data}")
        codes = set()
        for feature in features:
            p = feature["properties"]
            if p.get("STATE") != fips or not p.get(field) or not feature.get("geometry"):
                raise ValueError(f"{layer} {st}: invalid state, district or geometry")
            codes.add(p[field])
            p["STATEFP"] = p["STATE"]
            p[{"congress": "CD120FP", "state_senate": "SLDUST", "state_house": "SLDLST"}[layer]] = p[field]
        if len(codes) != expected:
            raise ValueError(f"{layer} {st}: duplicate district codes")
        return st, features, response.url

    items = [(st, state) for st, state in C.states().items() if layer != "state_house" or st != "NE"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        parts = list(pool.map(get_state, items))
    collection = {"type": "FeatureCollection", "features": [f for _, features, _ in parts for f in features]}
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".geojson.part")
    tmp.write_text(json.dumps(collection, separators=(",", ":")), encoding="utf-8")
    tmp.replace(dest)
    entry = {"path": str(dest.relative_to(C.ROOT)), "bytes": dest.stat().st_size,
             "sha256": sha256(dest), "vintage": vintage, "mirror": False, "source": source,
             "states": {st: {"url": url, "features": len(features)} for st, features, url in parts}}
    _record(key, **entry)
    log.info("fetched %s: %d districts across %d states", layer, len(collection["features"]), len(parts))
    return dest, entry


def fetch_boundaries(year: int | None = None, mirror_only: bool = False) -> dict:
    """2026 TIGERweb districts plus cartographic state and county backgrounds."""
    src = C.sources()["boundaries"]
    year = year or src["vintage"]
    mirror = src["mirror"]
    out = {}
    for layer in ("congress", "state_senate", "state_house", "states", "counties"):
        if layer in ("congress", "state_senate", "state_house") and not mirror_only:
            path, entry = fetch_tigerweb_layer(layer, src)
            out[layer] = {"path": path, "vintage": entry["vintage"], "mirror": False}
            continue
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


# ---------------------------------------------------------------------- overrides
def fetch_overrides(mirror_only: bool = False) -> None:
    """Download each override's block assignment file and the block geometry it needs.

    Failures are logged, not raised: districts.py falls back to the next input
    (BAF on block groups, then the county composition) and flags the result.
    """
    if not mirror_only:
        return  # TIGERweb's 120th layer already contains the Ohio 2026 plan.
    mirror = C.sources()["boundaries"]["mirror"]
    for ov in C.sources().get("overrides", []):
        key = f"overrides.{ov['state']}.{ov['office']}"
        if (C.ROOT / ov.get("path", "_none_")).exists():
            continue
        baf = C.ROOT / ov["baf_path"] if ov.get("baf_path") else None
        if baf and not baf.exists() and ov.get("baf_url") and not mirror_only:
            try:
                download(ov["baf_url"], baf)
                if baf.stat().st_size < 10_000:  # the Commission's SPA answers 200 with a 2.4 KB shell
                    baf.unlink()
                    raise RuntimeError("response was the web app shell, not the plan zip")
                _record(f"{key}.baf", url=ov["baf_url"], path=str(baf.relative_to(C.ROOT)),
                        bytes=baf.stat().st_size, sha256=sha256(baf))
            except Exception as exc:  # noqa: BLE001
                log.warning("%s: block assignment file unavailable (%s)", key, exc)
        if not (baf and baf.exists()):
            continue
        cands = []
        if ov.get("blocks_url") and not mirror_only:
            cands.append((ov["blocks_url"], C.RAW / "boundaries" / Path(ov["blocks_url"]).name,
                          {"unit": "block"}))
        fname = mirror["files"]["block_groups"]
        cands.append((f"{mirror['base']}/{fname}", C.RAW / "boundaries" / fname, {"unit": "block_group"}))
        try:
            first_working(f"{key}.units", cands)
        except RuntimeError as exc:
            log.warning("%s: no block geometry (%s)", key, exc)


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
def _arcgis_count(url: str, bbox: list[float], where: str = "1=1") -> int:
    base_params = {"where": where, "geometry": ",".join(map(str, bbox)),
                   "geometryType": "esriGeometryEnvelope", "inSR": 4326,
                   "spatialRel": "esriSpatialRelIntersects"}
    count_response = requests.get(url.rstrip("/") + "/query", params=base_params | {"returnCountOnly": "true", "f": "json"},
                                  timeout=60, headers=UA)
    count_response.raise_for_status()
    return int(count_response.json()["count"])


def _arcgis_geojson(url: str, bbox: list[float], where: str = "1=1", page: int = 2000) -> dict:
    base_params = {"where": where, "geometry": ",".join(map(str, bbox)),
                   "geometryType": "esriGeometryEnvelope", "inSR": 4326,
                   "spatialRel": "esriSpatialRelIntersects"}
    expected = _arcgis_count(url, bbox, where)
    feats, offset = [], 0
    while True:
        params = base_params | {
            "outFields": "*", "f": "geojson", "outSR": 4326,
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
    if len(feats) != expected:
        raise ValueError(f"ArcGIS query returned {len(feats)} of {expected} features")
    return {"type": "FeatureCollection", "features": feats}


def fetch_rail(mirror_only: bool = False) -> dict:
    """Rail network for routing: BTS NTAD North American Rail Network, else Natural Earth."""
    rs = C.sources()["rail"]
    bbox = C.load_yaml("states.yaml")["bbox"]
    out: dict = {}
    if not mirror_only:
        try:
            dest = C.RAW / "rail" / "ntad_narn_lines.geojson"
            if dest.exists():
                expected = _arcgis_count(rs["narn_lines"]["url"], bbox)
                actual = len(json.loads(dest.read_text())["features"])
                if actual != expected:
                    raise ValueError(f"cached NTAD rail response has {actual} of {expected} features")
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
        "overrides": fetch_overrides(mirror_only=mirror_only),
        "rosters": fetch_rosters(),
        "rail": fetch_rail(mirror_only=mirror_only),
    }
