"""Assemble one clean district layer per office, tagged with boundary vintage caveats."""
from __future__ import annotations

import logging
import re
from pathlib import Path

import geopandas as gpd
import yaml
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

    # Districts redrawn after this vintage (e.g. Ohio's 2026 congressional map).
    for ov in C.sources().get("overrides", []):
        if ov["office"] != office:
            continue
        st = ov["state"]
        new = resolve_override(ov, office, raw)
        if new is None:
            mask = out["state"] == st
            out.loc[mask, ["boundary_status", "boundary_note"]] = ["pending", ov["reason"].strip()]
            log.warning("no input for %s %s override; drawing old lines as pending", st, office)
        else:
            out = pd.concat([out[out["state"] != st], new], ignore_index=True)

    if "candidates" not in out:
        out["candidates"] = ""
    out["candidates"] = out["candidates"].fillna("")
    out["id"] = out["office"] + ":" + out["state"] + ":" + out["district"]
    out = gpd.GeoDataFrame(out, geometry="geometry", crs=C.CRS_LONLAT)
    out["geometry"] = out.geometry.make_valid()
    return out.sort_values(["state", "district"]).reset_index(drop=True)


# ---------------------------------------------------------------------- overrides
def _frame(office: str, st: str, rows: list[dict], vintage: str) -> gpd.GeoDataFrame:
    fips = C.states()[st]["fips"]
    g = gpd.GeoDataFrame(rows, geometry="geometry", crs=C.CRS_LONLAT)
    g.insert(0, "office", office)
    g.insert(1, "state", st)
    g["geoid"] = [f"{fips}{d.zfill(2)}" if d.isdigit() else "" for d in g["district"]]
    g["vintage"] = vintage
    return g


def resolve_override(ov: dict, office: str, raw: dict) -> gpd.GeoDataFrame | None:
    """Best available geometry for a redrawn plan: plan file > BAF > county composition."""
    st = ov["state"]
    if ov.get("path") and (C.ROOT / ov["path"]).exists():
        src = _read(C.ROOT / ov["path"]).to_crs(C.CRS_LONLAT)
        rows = [{"district": norm_district(d), "boundary_status": "current", "boundary_note": "",
                 "candidates": "", "geometry": geom} for d, geom in zip(src[ov["district_field"]].astype(str), src.geometry)]
        log.info("override %s %s: official plan geometry %s", st, office, ov["path"])
        return _frame(office, st, rows, "official-plan")
    if ov.get("baf_path") and (C.ROOT / ov["baf_path"]).exists():
        g = override_from_baf(ov, office)
        if g is not None:
            return g
    if ov.get("composition") and "counties" in raw:
        return override_from_composition(ov, office, raw)
    return None


def read_baf(path: Path) -> pd.DataFrame:
    """Block assignment file -> DataFrame[block (15-char GEOID20), district].

    Accepts the Commission's plan zip (which holds `... CD BAF.xlsx`), an .xlsx, or a
    .csv/.txt with the block GEOID in the first column and the district in the second.
    """
    import io
    import zipfile

    def from_bytes(name: str, data: bytes) -> pd.DataFrame:
        if name.lower().endswith(".xlsx"):
            import openpyxl  # the workbook has no dimensions; iterate rows, don't index
            ws = openpyxl.load_workbook(io.BytesIO(data), read_only=True).worksheets[0]
            rows = [r[:2] for r in ws.iter_rows(values_only=True)]
            df = pd.DataFrame(rows[1:], columns=["block", "district"])
        else:
            df = pd.read_csv(io.BytesIO(data), dtype=str, sep=None, engine="python").iloc[:, :2]
            df.columns = ["block", "district"]
        df = df.dropna()
        df["block"] = df["block"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(15)
        df["district"] = df["district"].astype(str).str.replace(r"\.0$", "", regex=True).map(norm_district)
        return df

    path = Path(path)
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.lower().endswith((".xlsx", ".csv", ".txt"))]
            names.sort(key=lambda n: ("baf" not in n.lower(), n))
            if not names:
                raise ValueError(f"{path}: no .xlsx/.csv block assignment file inside")
            return from_bytes(names[0], z.read(names[0]))
    return from_bytes(path.name, path.read_bytes())


def baf_to_block_groups(baf: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Assign each 2020 block group to the district holding most of its blocks.

    Returns (DataFrame[bg, district], number of block groups cut by a district line).
    Ties go to the lower district number so the result is deterministic.
    """
    b = baf.assign(bg=baf["block"].str[:12])
    tally = b.groupby(["bg", "district"]).size().rename("n").reset_index()
    tally["share"] = tally["n"] / tally.groupby("bg")["n"].transform("sum")
    tally["_d"] = tally["district"].str.extract(r"(\d+)", expand=False).astype(int)
    best = tally.sort_values(["bg", "n", "_d"], ascending=[True, False, True]).drop_duplicates("bg")
    return best[["bg", "district"]].reset_index(drop=True), int((best["share"] < 1).sum())


def override_from_baf(ov: dict, office: str) -> gpd.GeoDataFrame | None:
    st = ov["state"]
    fips = C.states()[st]["fips"]
    baf = read_baf(C.ROOT / ov["baf_path"])
    if not baf["block"].str.startswith(fips).all():
        raise ValueError(f"{ov['baf_path']}: blocks outside state {fips}")
    blocks = C.RAW / "boundaries" / Path(ov.get("blocks_url", "none")).name
    bg_file = C.RAW / "boundaries" / C.sources()["boundaries"]["mirror"]["files"]["block_groups"]
    if blocks.exists():
        units = _read(blocks).to_crs(C.CRS_LONLAT)
        key = next(c for c in units.columns if c.upper().startswith("GEOID"))
        units = units.merge(baf, left_on=key, right_on="block", how="inner")
        method, note = "block", ""
    elif bg_file.exists():
        units = gpd.read_file(bg_file, where=f"STATEFP='{fips}'").to_crs(C.CRS_LONLAT)
        best, split = baf_to_block_groups(baf)
        units = units.merge(best, left_on="GEOID", right_on="bg", how="inner")
        method = "block_group"
        note = (f"Built from the plan's block assignment file on 2020 block groups; {split} block groups "
                f"cut by a district line were assigned to the district holding most of their blocks.")
    else:
        log.warning("%s %s: BAF present but no block geometry; falling back", st, office)
        return None
    units["geometry"] = units.geometry.make_valid().buffer(0)  # simplified BGs can self-intersect
    diss = units[["district", "geometry"]].dissolve(by="district").reset_index()
    rows = [{"district": d, "boundary_status": "current", "boundary_note": note, "candidates": "",
             "geometry": geom} for d, geom in zip(diss["district"], diss.geometry)]
    log.info("override %s %s: BAF on %s (%d districts)", st, office, method, len(rows))
    return _frame(office, st, rows, f"baf-{method}")


def override_from_composition(ov: dict, office: str, raw: dict) -> gpd.GeoDataFrame:
    """Official county composition: exact whole counties, split counties marked pending."""
    st = ov["state"]
    fips = C.states()[st]["fips"]
    comp = yaml.safe_load(open(C.ROOT / ov["composition"], encoding="utf-8"))
    counties = _read(raw["counties"]["path"]).to_crs(C.CRS_LONLAT)
    counties = counties[counties["STATEFP"] == fips].set_index("NAME")
    whole = {c: str(d) for d, cs in comp["whole"].items() for c in (cs or [])}
    split = {c: [str(x) for x in ds] for c, ds in comp["split"].items()}
    listed = list(whole) + list(split)
    dupes = {c for c in listed if listed.count(c) > 1}
    missing = set(counties.index) - set(listed)
    unknown = set(listed) - set(counties.index)
    if dupes or missing or unknown:
        raise ValueError(f"{ov['composition']}: duplicates={sorted(dupes)} missing={sorted(missing)} "
                         f"unknown={sorted(unknown)}")
    rows = []
    for d in map(str, range(1, comp["districts"] + 1)):
        parts = [c for c, dd in whole.items() if dd == d]
        shares = sorted(c for c, ds in split.items() if d in ds)
        if parts:
            note = ("Also includes part of " + ", ".join(f"{c} County" for c in shares)
                    + " (line pending)." if shares else "")
            rows.append({"district": d, "boundary_status": "current", "boundary_note": note, "candidates": "",
                         "geometry": counties.loc[parts].geometry.union_all()})
    for c, ds in split.items():
        rows.append({"district": "/".join(ds), "boundary_status": "pending",
                     "boundary_note": (f"{c} County is split between {st}-{ds[0]} and {st}-{ds[1]}. The exact line "
                                       "needs the plan's block assignment file."),
                     "candidates": ",".join(f"{office}:{st}:{x}" for x in ds),
                     "county": c, "geometry": counties.loc[c].geometry})
    log.info("override %s %s: county composition (%d whole counties, %d split)", st, office, len(whole), len(split))
    return _frame(office, st, rows, "county-composition")


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
