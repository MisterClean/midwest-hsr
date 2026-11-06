"""Command-line entry point: `hsr fetch | build | analyze | export | qa | all`."""
from __future__ import annotations

import argparse
import json
import logging

import geopandas as gpd
import pandas as pd

from . import analysis, districts, export, fetch, report, results, routing
from . import config as C

log = logging.getLogger("hsr")


def _raw_paths() -> dict:
    m = json.loads((C.RAW / "MANIFEST.json").read_text())
    b = {k.split(".", 1)[1]: {"path": C.ROOT / v["path"], "vintage": v.get("vintage"), "mirror": v.get("mirror")}
         for k, v in m.items() if k.startswith("boundaries.")}
    rail = {"network": C.ROOT / m["rail.network"]["path"], "network_source": m["rail.network"].get("source"),
            "lakes": C.ROOT / m["rail.lakes"]["path"] if "rail.lakes" in m else None}
    if rail["network_source"] == "ntad" and "rail.amtrak_stations" in m:
        rail["amtrak_stations"] = C.ROOT / m["rail.amtrak_stations"]["path"]
    ros = {"congress": C.ROOT / m["rosters.congress_legislators"]["path"],
           "openstates": C.ROOT / m["rosters.openstates_people"]["path"],
           "openstates_commit": m["rosters.openstates_people"].get("commit")}
    return {"boundaries": b, "rail": rail, "rosters": ros, "manifest": m}


def cmd_fetch(a) -> None:
    fetch.fetch_all(mirror_only=a.mirror)


def cmd_build(a) -> None:
    raw = _raw_paths()
    layers = districts.build_all(raw["boundaries"])
    for o in C.OFFICES:
        g = layers[o]
        log.info("%s: %d districts (%d pending boundaries)", o, len(g), (g.boundary_status == "pending").sum())

    res = results.load_snapshot()
    os_ = results.load_openstates(raw["rosters"]["openstates"])
    cg = results.load_congress(raw["rosters"]["congress"])
    seats = results.seats(res, os_, cg)
    ctrl = results.chamber_control(seats)
    tri = results.trifectas(seats, ctrl)
    C.PROCESSED.mkdir(parents=True, exist_ok=True)
    res.to_csv(C.PROCESSED / "results_2026.csv", index=False)
    seats.to_csv(C.PROCESSED / "seats.csv", index=False)
    ctrl.to_csv(C.PROCESSED / "chamber_control.csv", index=False)
    tri.to_csv(C.PROCESSED / "trifectas.csv", index=False)

    if "amtrak_stations" in raw["rail"]:
        n = routing.apply_ntad_station_coords(raw["rail"]["amtrak_stations"])
        log.info("station coordinates from NTAD: %d", n)
    lines, stops = routing.build_corridors(raw["rail"])
    lines.drop(columns=["segments"]).to_file(C.INTERIM / "corridors.gpkg", driver="GPKG")
    stops.to_file(C.INTERIM / "stops.gpkg", driver="GPKG")
    pd.DataFrame([{"corridor": r.id, **s} for r in lines.itertuples() for s in r.segments]).to_csv(
        C.PROCESSED / "corridor_segments.csv", index=False)
    lines.drop(columns=["geometry", "segments"]).to_csv(C.PROCESSED / "corridors.csv", index=False)


def _load_built():
    layers = {o: gpd.read_file(C.INTERIM / f"{o}.gpkg") for o in (*C.OFFICES, "states")}
    lines = gpd.read_file(C.INTERIM / "corridors.gpkg")
    lines["default"] = lines["default"].astype(bool)
    stops = gpd.read_file(C.INTERIM / "stops.gpkg")
    seats = pd.read_csv(C.PROCESSED / "seats.csv", dtype={"district": str}, keep_default_na=False,
                        na_values={"margin": [""], "winner_pct": [""], "runnerup_pct": [""]})
    seats["flipped"] = seats["flipped"].astype(str).eq("True")
    ctrl = pd.read_csv(C.PROCESSED / "chamber_control.csv")
    tri = pd.read_csv(C.PROCESSED / "trifectas.csv", keep_default_na=False)
    return layers, lines, stops, seats, ctrl, tri


def cmd_analyze(a) -> None:
    layers, lines, stops, seats, ctrl, tri = _load_built()
    cd = analysis.corridor_districts(lines, stops, layers, seats)
    cd.to_csv(C.PROCESSED / "corridor_districts.csv", index=False)
    summ = analysis.summarize(cd, lines)
    C.write_json(C.PROCESSED / "summary.json", summ)
    paths = analysis.pathways(lines, layers, seats, ctrl, tri, cd)
    C.write_json(C.PROCESSED / "pathways.json", paths)
    core = summ["network"]["hsr_core"]
    log.info("HSR core: %s km; U.S. House districts %s", core["km"], core["us_house"])


def cmd_export(a) -> None:
    raw = _raw_paths()
    layers, lines, stops, seats, ctrl, tri = _load_built()
    cd = pd.read_csv(C.PROCESSED / "corridor_districts.csv", keep_default_na=False, dtype={"district": str})
    summ = json.loads((C.PROCESSED / "summary.json").read_text())
    paths = json.loads((C.PROCESSED / "pathways.json").read_text())
    vint = {k: v["vintage"] for k, v in raw["boundaries"].items()}
    meta = {
        "election": "2026-11-03",
        "results_snapshot": C.sources()["results"]["snapshot"].rsplit("/", 1)[-1],
        "boundary_vintage": vint,
        "boundary_mirror": any(v["mirror"] for v in raw["boundaries"].values()),
        "rail_network": raw["rail"]["network_source"],
        "openstates_commit": raw["rosters"]["openstates_commit"],
        "pending_note": "Hatched districts have boundaries newer than the available source file.",
        "ohio_cd_method": str(layers["us_house"].loc[layers["us_house"].state == "OH", "vintage"].iloc[0]),
    }
    lines["segments"] = [[]] * len(lines)
    export.export(layers, raw["rail"].get("lakes"), lines, stops, seats, ctrl, tri, cd, summ, paths, meta)


def cmd_qa(a) -> None:
    raw = _raw_paths()
    seats = pd.read_csv(C.PROCESSED / "seats.csv", dtype={"district": str}, keep_default_na=False)
    print("\n== seat coverage by chamber")
    for (st, off), g in seats.groupby(["state", "office"]):
        print(f"{st} {off:13s} seats={len(g):4d} 2026={int((g.source == '2026').sum()):4d} "
              f"holdover={int((g.source == 'holdover').sum()):3d} vacant={int((g.source == 'vacant').sum())} "
              f"uncalled={int(g.status.isin(['uncalled', 'leading']).sum())}")
    if a.places:
        print("\n== stations farthest from a Natural Earth populated place")
        print(routing.qa_stations(a.places).head(15).to_string(index=False))
    seg = pd.read_csv(C.PROCESSED / "corridor_segments.csv")
    print("\n== corridor segments drawn direct (not on rail)")
    cfg = {c["id"]: c["follow"] for c in C.corridors()}
    bad = seg[(seg.method == "direct") & seg.corridor.map(cfg).eq("rail")]
    print(bad.to_string(index=False) if len(bad) else "none")
    print("\nrail network:", raw["rail"]["network_source"])


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="hsr", description=__doc__)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="download boundaries, rosters, rail network")
    f.add_argument("--mirror", action="store_true", help="skip census.gov / NTAD and use GitHub mirrors")
    sub.add_parser("build", help="clean districts, results -> seats, route corridors")
    sub.add_parser("analyze", help="corridor x district joins, summaries, pathways")
    sub.add_parser("export", help="write web/data for the map")
    q = sub.add_parser("qa", help="coverage and geometry checks")
    q.add_argument("--places", help="Natural Earth populated places GeoJSON for station checks")
    sub.add_parser("report", help="write docs/generated/pathway_report.md")
    al = sub.add_parser("all", help="fetch + build + analyze + export + report")
    al.add_argument("--mirror", action="store_true")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(levelname)s %(message)s")
    C.ensure_dirs()
    if a.cmd == "all":
        cmd_fetch(a); cmd_build(a); cmd_analyze(a); cmd_export(a); report.write()
    else:
        {"fetch": cmd_fetch, "build": cmd_build, "analyze": cmd_analyze, "export": cmd_export, "qa": cmd_qa,
         "report": lambda _a: report.write()}[a.cmd](a)


if __name__ == "__main__":
    main()
