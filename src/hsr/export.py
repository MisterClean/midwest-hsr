"""Write the compact files the web map loads (TopoJSON + JSON) into web/data/."""
from __future__ import annotations

import datetime as dt
import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

import geopandas as gpd
import pandas as pd

from . import config as C

log = logging.getLogger(__name__)

SIMPLIFY = {"us_house": "6%", "state_senate": "5%", "state_house": "4%", "states": "4%", "lakes": "5%"}


def _mapshaper() -> list[str]:
    exe = shutil.which("mapshaper")
    if exe:
        return [exe]
    if shutil.which("npx"):
        return ["npx", "--yes", "mapshaper@0.6"]
    raise RuntimeError("mapshaper not found: `npm install -g mapshaper`")


def to_topojson(gdf: gpd.GeoDataFrame, name: str, out: Path, simplify: str) -> Path:
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / f"{name}.geojson"
        gdf.to_crs(C.CRS_LONLAT).to_file(src, driver="GeoJSON")
        cmd = [*_mapshaper(), "-i", str(src), f"name={name}", "-simplify", simplify, "keep-shapes",
               "-clean", "-o", "format=topojson", "quantization=100000", str(out)]
        subprocess.run(cmd, check=True, capture_output=True)
    log.info("wrote %s (%.0f KB)", out, out.stat().st_size / 1024)
    return out


def _seat_json(seats: pd.DataFrame) -> dict:
    out = {}
    for r in seats.itertuples():
        out[r.id] = {k: v for k, v in {
            "h": r.holder, "p": r.party, "s": r.status, "src": r.source,
            "m": None if pd.isna(r.margin) else round(float(r.margin), 1),
            "w": None if pd.isna(r.winner_pct) else round(float(r.winner_pct), 1),
            "ru": r.runnerup or None, "rp": r.runnerup_party or None,
            "f": bool(r.flipped) or None, "pp": r.prior_party or None, "ph": r.prior_holder or None,
        }.items() if v not in (None, "")}
    return out


def export(layers: dict, lakes_path: Path | None, lines: gpd.GeoDataFrame, stops: gpd.GeoDataFrame,
           seats: pd.DataFrame, control: pd.DataFrame, trif: pd.DataFrame, cd: pd.DataFrame,
           summary: dict, paths: dict, meta: dict) -> None:
    W = C.WEB_DATA
    W.mkdir(parents=True, exist_ok=True)
    for office in C.OFFICES:
        lay = layers[office]
        if "candidates" not in lay:
            lay = lay.assign(candidates="")
        g = lay[["id", "state", "district", "boundary_status", "boundary_note", "candidates", "geometry"]].rename(
            columns={"boundary_status": "bs", "boundary_note": "note", "candidates": "alt"})
        g["bs"] = g["bs"].map({"pending": "p"}).fillna("")
        g["alt"] = g["alt"].fillna("")
        # Keep notes only where they say something the map shows (split pieces, partial districts).
        g["note"] = [n if (a or str(n).startswith("Also includes")) else "" for n, a in zip(g["note"].fillna(""), g["alt"])]
        to_topojson(g, office, W / f"{office}.topo.json", SIMPLIFY[office])
    to_topojson(layers["states"], "states", W / "states.topo.json", SIMPLIFY["states"])
    if lakes_path:
        bbox = C.load_yaml("states.yaml")["bbox"]
        lk = gpd.read_file(lakes_path).cx[bbox[0]:bbox[2], bbox[1]:bbox[3]]
        lk = lk[lk["scalerank"] <= 2][["name", "geometry"]] if "scalerank" in lk else lk[["geometry"]]
        to_topojson(lk, "lakes", W / "lakes.topo.json", SIMPLIFY["lakes"])

    ln = lines.to_crs(C.CRS_LONLAT).copy()
    ln["geometry"] = ln.geometry.simplify(0.0008)
    ln = ln.drop(columns=["segments"])
    fc = json.loads(ln.to_json(drop_id=True))
    for f in fc["features"]:
        f["geometry"]["coordinates"] = [[round(x, 4), round(y, 4)] for x, y in f["geometry"]["coordinates"]]
    C.write_json(W / "corridors.json", fc, compact=True)

    sp = stops.to_crs(C.CRS_LONLAT)
    C.write_json(W / "stops.json", [{"c": r.corridor, "o": r.order, "id": r.station, "n": r.name, "st": r.state,
                                     "k": r.kind, "x": round(r.geometry.x, 4), "y": round(r.geometry.y, 4)}
                                    for r in sp.itertuples()], compact=True)

    srcs = C.corridor_sources()
    bundle = {
        "meta": meta | {"exported_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")},
        "seats": _seat_json(seats),
        "control": control.to_dict("records"),
        "trifectas": trif.to_dict("records"),
        "summary": summary,
        "pathways": paths,
        "corridor_districts": [
            {"c": r.corridor, "id": r.id, "km": r.km, "stops": r.stops or None}
            for r in cd.itertuples()],
        "sources": srcs,
    }
    C.write_json(W / "analysis.json", bundle, compact=True)
    log.info("web bundle: %s", ", ".join(f"{p.name} {p.stat().st_size // 1024}KB" for p in sorted(W.iterdir())))
