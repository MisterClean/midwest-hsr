"""Assemble one clean district layer per office, tagged with boundary vintage caveats."""
from __future__ import annotations

import logging
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd

from . import config as C

log = logging.getLogger(__name__)

LAYER_FOR_OFFICE = {"us_house": "congress", "state_senate": "state_senate", "state_house": "state_house"}
CODE_FIELD = {"congress": r"CD\d+FP", "state_senate": "SLDUST", "state_house": "SLDLST"}

# Wayne, Oakland and Macomb counties (approximate envelope). Michigan's court-ordered
# redraw (Agee v. Benson) changed legislative districts only in this area.
DETROIT_ENVELOPE = (-83.56, 42.02, -82.70, 42.90)


def norm_district(code: str) -> str:
    """'01' -> '1', '009A' -> '9A', 'HD-12' -> '12', 'District 3' -> '3'."""
    s = str(code).strip().upper()
    s = re.sub(r"^(HD|SD|AD|LD|DISTRICT|DIST\.?)[-\s]*", "", s)
    m = re.match(r"^0*(\d+)([A-Z]?)$", s)
    if m:
        return f"{int(m.group(1))}{m.group(2)}"
    return s


def _read(path: Path) -> gpd.GeoDataFrame:
    p = str(path)
    if p.endswith(".zip"):
        p = f"zip://{p}"
    return gpd.read_file(p)


def build_layer(office: str, raw: dict, override_dir: Path | None = None) -> gpd.GeoDataFrame:
    layer = LAYER_FOR_OFFICE[office]
    info = raw[layer]
    gdf = _read(info["path"]).to_crs(C.CRS_LONLAT)
    usps = C.fips_to_usps()
    gdf = gdf[gdf["STATEFP"].isin(usps)].copy()
    code_col = next(c for c in gdf.columns if re.fullmatch(CODE_FIELD[layer], c))
    gdf = gdf[~gdf[code_col].str.upper().str.startswith("ZZ")]
    if office == "state_house":  # Nebraska is unicameral: its seats live in the SLDU layer
        gdf = gdf[gdf["STATEFP"] != C.states()["NE"]["fips"]]
    out = gpd.GeoDataFrame({
        "office": office,
        "state": gdf["STATEFP"].map(usps),
        "district": gdf[code_col].map(norm_district),
        "geoid": gdf["GEOID"],
        "vintage": info["vintage"],
        "boundary_status": "current",
        "boundary_note": "",
    }, geometry=gdf.geometry.values, crs=gdf.crs)

    # Districts whose 2026 lines post-date this vintage.
    caveats = C.sources()["vintage_caveats"].get(info["vintage"], {}).get(office, {})
    for st, note in caveats.items():
        mask = out["state"] == st
        if st == "MI":
            cen = out.geometry.representative_point()
            x0, y0, x1, y1 = DETROIT_ENVELOPE
            mask &= cen.x.between(x0, x1) & cen.y.between(y0, y1)
        out.loc[mask, ["boundary_status", "boundary_note"]] = ["pending", note]

    # Official plan overrides (e.g. Ohio's 2026 congressional map).
    for ov in C.sources().get("overrides", []):
        if ov["office"] != office:
            continue
        path = C.ROOT / ov["path"]
        st = ov["state"]
        if path.exists():
            new = _read(path).to_crs(C.CRS_LONLAT)
            new = gpd.GeoDataFrame({
                "office": office, "state": st,
                "district": new[ov["district_field"]].astype(str).map(norm_district),
                "geoid": [f"{C.states()[st]['fips']}{norm_district(d).zfill(2)}" for d in new[ov["district_field"]]],
                "vintage": "official-2026", "boundary_status": "current", "boundary_note": "",
            }, geometry=new.geometry.values, crs=new.crs)
            out = pd.concat([out[out["state"] != st], new], ignore_index=True)
            log.info("override applied: %s %s from %s", st, office, path)
        else:
            mask = out["state"] == st
            out.loc[mask, ["boundary_status", "boundary_note"]] = ["pending", ov["reason"].strip()]
            log.warning("override missing for %s %s (%s); drawing as pending", st, office, path)

    out["id"] = out["office"] + ":" + out["state"] + ":" + out["district"]
    out = gpd.GeoDataFrame(out, geometry="geometry", crs=C.CRS_LONLAT)
    out["geometry"] = out.geometry.make_valid()
    return out.sort_values(["state", "district"]).reset_index(drop=True)


def build_states(raw: dict) -> gpd.GeoDataFrame:
    gdf = _read(raw["states"]["path"]).to_crs(C.CRS_LONLAT)
    gdf["in_scope"] = gdf["STATEFP"].isin(C.fips_to_usps())
    bbox = C.load_yaml("states.yaml")["bbox"]
    gdf = gdf.cx[bbox[0]:bbox[2], bbox[1]:bbox[3]]
    return gpd.GeoDataFrame({"state": gdf["STUSPS"], "name": gdf["NAME"], "in_scope": gdf["in_scope"]},
                            geometry=gdf.geometry.values, crs=C.CRS_LONLAT)


def build_all(raw: dict) -> dict[str, gpd.GeoDataFrame]:
    layers = {office: build_layer(office, raw) for office in C.OFFICES}
    layers["states"] = build_states(raw)
    C.INTERIM.mkdir(parents=True, exist_ok=True)
    for name, g in layers.items():
        g.to_file(C.INTERIM / f"{name}.gpkg", driver="GPKG")
    return layers
