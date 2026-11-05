"""Corridor x district analysis and the per-corridor political pathway."""
from __future__ import annotations

import geopandas as gpd
import pandas as pd

from . import config as C

MIN_KM = 0.5        # ignore slivers where a line grazes a district edge
CLOSE_MARGIN = 5.0  # percentage points


def corridor_districts(lines: gpd.GeoDataFrame, stops: gpd.GeoDataFrame,
                       layers: dict[str, gpd.GeoDataFrame], seats: pd.DataFrame) -> pd.DataFrame:
    rows = []
    seat_idx = seats.set_index("id")
    for office in C.OFFICES:
        d = layers[office].to_crs(C.CRS_METERS)
        hits = gpd.sjoin(lines[["id", "geometry"]].rename(columns={"id": "corridor"}), d, predicate="intersects")
        for _, h in hits.iterrows():
            poly = d.loc[h["index_right"], "geometry"]
            line = lines.loc[lines.id == h["corridor"], "geometry"].iloc[0]
            km = line.intersection(poly).length / 1000
            rows.append({"corridor": h["corridor"], "office": office, "id": h["id"], "state": h["state"],
                         "district": h["district"], "km": round(km, 2),
                         "boundary_status": h["boundary_status"]})
        st_hits = gpd.sjoin(stops, d[["id", "geometry"]], predicate="within")
        for (cor, did), g in st_hits.groupby(["corridor", "id"]):
            rows.append({"corridor": cor, "office": office, "id": did, "stops": ",".join(g["station"]),
                         "km": 0.0, "_stop": True})
    df = pd.DataFrame(rows)
    df["_stop"] = df["_stop"].fillna(False).astype(bool) if "_stop" in df else False
    stops_by = df[df["_stop"]].groupby(["corridor", "id"])["stops"].first()
    stop_only = df[df["_stop"]].drop(columns=["state", "district", "boundary_status"], errors="ignore")
    stop_only = stop_only.merge(layer_meta(layers), on="id", how="left")
    df = pd.concat([df[~df["_stop"]], stop_only], ignore_index=True)
    df = df.groupby(["corridor", "office", "id", "state", "district", "boundary_status"], as_index=False)["km"].sum()
    df["stops"] = [stops_by.get((c, i), "") for c, i in zip(df.corridor, df.id)]
    df = df[(df.km >= MIN_KM) | (df.stops != "")]
    cols = ["holder", "party", "status", "margin", "flipped", "prior_party", "source"]
    df = df.join(seat_idx[cols], on="id")
    return df.sort_values(["corridor", "office", "state", "district"]).reset_index(drop=True)


def layer_meta(layers: dict) -> pd.DataFrame:
    return pd.concat([layers[o][["id", "state", "district", "boundary_status"]] for o in C.OFFICES],
                     ignore_index=True)


def _counts(g: pd.DataFrame) -> dict:
    ok = g[g.boundary_status != "pending"]
    return {
        "districts": int(len(g)),
        "counted": int(len(ok)),
        "pending_boundaries": int((g.boundary_status == "pending").sum()),
        "D": int((ok.party == "D").sum()), "R": int((ok.party == "R").sum()),
        "other": int((~ok.party.isin(["D", "R", ""])).sum()),
        "undecided": int((ok.party == "").sum()),
        "uncalled": int(ok.status.isin(["uncalled", "leading"]).sum()),
        "flipped_to_D": int((ok.flipped & (ok.party == "D")).sum()),
        "flipped_to_R": int((ok.flipped & (ok.party == "R")).sum()),
        "close": int((ok.margin.abs() < CLOSE_MARGIN).sum()),
        "km_D": round(float(ok.loc[ok.party == "D", "km"].sum()), 1),
        "km_R": round(float(ok.loc[ok.party == "R", "km"].sum()), 1),
        "with_stop": int((g.stops != "").sum()),
    }


def summarize(cd: pd.DataFrame, lines: gpd.GeoDataFrame) -> dict:
    out = {"corridors": {}, "network": {}}
    for cid, g in cd.groupby("corridor"):
        out["corridors"][cid] = {office: _counts(g[g.office == office]) for office in C.OFFICES}
    core = lines[(lines.tier == "hsr") & lines["default"]].id
    allc = lines[lines["default"]].id
    for name, ids in (("hsr_core", core), ("all_default", allc)):
        sub = cd[cd.corridor.isin(ids)]
        uniq = sub.sort_values("km", ascending=False).drop_duplicates("id")
        out["network"][name] = {
            "corridors": list(ids),
            "km": round(float(lines[lines.id.isin(ids)].length_km.sum()), 0),
            **{office: _counts(uniq[uniq.office == office]) for office in C.OFFICES},
        }
    return out


def pathways(lines: gpd.GeoDataFrame, layers: dict, seats: pd.DataFrame, control: pd.DataFrame,
             trif: pd.DataFrame, cd: pd.DataFrame) -> dict:
    """For each corridor: the states it crosses, in order, and who holds power in each."""
    states = layers["states"].to_crs(C.CRS_METERS)
    states = states[states.in_scope]
    out = {}
    for _, c in lines.iterrows():
        line = c.geometry
        crossed = []
        for _, s in states.iterrows():
            inter = line.intersection(s.geometry)
            if inter.is_empty or inter.length < 500:
                continue
            first = min(line.project(pt) for pt in _endpoints(inter))
            crossed.append((first, s["state"], round(inter.length / 1000, 1)))
        crossed.sort()
        steps = []
        for _, st, km in crossed:
            sd = seats[seats.state == st]
            gov = sd[sd.office == "governor"].iloc[0] if (sd.office == "governor").any() else None
            sens = sd[sd.office == "us_senate"]
            ctrl = control[control.state == st].set_index("office")
            tri = trif[trif.state == st].iloc[0]
            along = cd[(cd.corridor == c["id"]) & (cd.state == st)]
            steps.append({
                "state": st, "km": km,
                "governor": None if gov is None else {"name": gov.holder, "party": gov.party, "source": gov.source,
                                                      "flipped": bool(gov.flipped)},
                "us_senators": [{"name": r.holder, "party": r.party, "new": r.source == "2026"} for r in sens.itertuples()],
                "chambers": {o: ctrl.loc[o].to_dict() for o in ctrl.index},
                "trifecta": tri["trifecta"],
                "us_house_along": [{"district": r.district, "name": r.holder, "party": r.party,
                                    "margin": None if pd.isna(r.margin) else round(float(r.margin), 1),
                                    "flipped": bool(r.flipped), "status": r.status,
                                    "boundary_status": r.boundary_status}
                                   for r in along[along.office == "us_house"].assign(
                                       _n=lambda x: x.district.str.extract(r"(\d+)", expand=False).astype(int)
                                   ).sort_values("_n").itertuples()],
                "state_senate_along": _counts(along[along.office == "state_senate"]),
                "state_house_along": _counts(along[along.office == "state_house"]),
            })
        out[c["id"]] = steps
    return out


def _endpoints(geom):
    if geom.geom_type == "LineString":
        return [gpd.points_from_xy([geom.coords[0][0]], [geom.coords[0][1]])[0]]
    if hasattr(geom, "geoms"):
        return [p for g in geom.geoms for p in _endpoints(g)]
    return [geom.representative_point()]
