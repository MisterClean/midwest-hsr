"""Turn the corridor catalog into line geometry.

`follow: rail` corridors are routed on the rail network between consecutive
waypoints (shortest path on a graph built from the network's vertices). Segments
that cannot be routed, or whose route is implausibly circuitous, fall back to a
straight segment and are flagged in the output. `follow: direct` corridors are
conceptual alignments drawn through their waypoints.
"""
from __future__ import annotations

import logging
import math

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import linemerge

from . import config as C

log = logging.getLogger(__name__)

GRID_M = 25          # vertices closer than this are merged
DENSIFY_M = 250      # max spacing along lines so T-junctions find a nearby vertex
CONNECT_M = 600      # dangling ends within this distance are joined
SNAP_MAX_M = 6000    # waypoint must be this close to the network
DETOUR_MAX = 1.45    # routed length / straight length above this -> fall back to direct
DROP_NET = {"A", "X", "Y", "O"}  # NTAD NARN: abandoned, removed, yard, out-of-service


def _load_network(path, source: str) -> gpd.GeoDataFrame:
    g = gpd.read_file(path)
    if source == "ntad" and "NET" in g.columns:
        g = g[~g["NET"].astype(str).str.upper().isin(DROP_NET)]
    bbox = C.load_yaml("states.yaml")["bbox"]
    g = g.cx[bbox[0] - 1:bbox[2] + 1, bbox[1] - 1:bbox[3] + 1]
    g = g.to_crs(C.CRS_METERS).explode(index_parts=False)
    g = g[g.geometry.type == "LineString"]
    return g


def build_graph(lines: gpd.GeoDataFrame) -> tuple[nx.Graph, np.ndarray, list]:
    G = nx.Graph()
    key = lambda x, y: (round(x / GRID_M) * GRID_M, round(y / GRID_M) * GRID_M)  # noqa: E731
    for geom in lines.geometry:
        if geom.length < 1:
            continue
        n = max(2, int(math.ceil(geom.length / DENSIFY_M)) + 1)
        pts = [geom.interpolate(t, normalized=True) for t in np.linspace(0, 1, n)]
        # keep original bends: merge original vertices with the densified ones
        coords = list(geom.coords)
        dens = [(p.x, p.y) for p in pts]
        merged = sorted(set(coords + dens), key=lambda c: geom.project(Point(c)))
        prev = None
        for x, y in merged:
            k = key(x, y)
            if prev is not None and k != prev:
                w = math.dist(prev, k)
                if not G.has_edge(prev, k) or G[prev][k]["weight"] > w:
                    G.add_edge(prev, k, weight=w)
            prev = k
    nodes = list(G.nodes)
    xy = np.array(nodes, dtype=float)
    tree = cKDTree(xy)
    # Join dangling ends to nearby vertices that are not already close along the graph
    # (Natural Earth and NARN lines are not always noded at junctions).
    added = 0
    for i, n in enumerate(nodes):
        if G.degree(n) != 1:
            continue
        near = tree.query_ball_point(xy[i], CONNECT_M)
        if len(near) <= 1:
            continue
        local = nx.single_source_dijkstra_path_length(G, n, cutoff=CONNECT_M * 3, weight="weight")
        for j in near:
            m = nodes[j]
            if m == n or m in local:
                continue
            G.add_edge(n, m, weight=math.dist(n, m) * 1.2, connector=True)
            added += 1
    log.info("rail graph: %d nodes, %d edges, %d connectors", G.number_of_nodes(), G.number_of_edges(), added)
    return G, xy, nodes


def _project_points(stations: dict) -> dict[str, tuple[float, float]]:
    s = gpd.GeoSeries([Point(v.lon, v.lat) for v in stations.values()], crs=C.CRS_LONLAT).to_crs(C.CRS_METERS)
    return {k: (p.x, p.y) for k, p in zip(stations, s)}


def parse_waypoints(wps: list[str]) -> list[tuple[str, bool]]:
    """['CHI', '~DWT'] -> [('CHI', True), ('DWT', False)]  (id, is_stop)."""
    return [(w[1:], False) if w.startswith("~") else (w, True) for w in wps]


def route_corridor(c: dict, xy_st: dict, G=None, tree=None, nodes=None) -> tuple[LineString, list[dict]]:
    wps = parse_waypoints(c["waypoints"])
    pieces, segs = [], []
    for (a, _), (b, _) in zip(wps, wps[1:]):
        pa, pb = xy_st[a], xy_st[b]
        straight = LineString([pa, pb])
        method, geom = "direct", straight
        if c["follow"] == "rail" and G is not None:
            da, ia = tree.query(pa)
            db, ib = tree.query(pb)
            if da <= SNAP_MAX_M and db <= SNAP_MAX_M:
                try:
                    path = nx.shortest_path(G, nodes[ia], nodes[ib], weight="weight")
                    line = LineString([pa, *path, pb]) if len(path) > 1 else straight
                    ratio = line.length / max(straight.length, 1)
                    if ratio <= DETOUR_MAX:
                        method, geom = "rail", line
                    else:
                        log.warning("%s %s-%s: detour ratio %.2f, using direct", c["id"], a, b, ratio)
                except nx.NetworkXNoPath:
                    log.warning("%s %s-%s: no rail path, using direct", c["id"], a, b)
            else:
                log.warning("%s %s-%s: waypoint %.1f/%.1f km from network, using direct",
                            c["id"], a, b, da / 1000, db / 1000)
        segs.append({"from": a, "to": b, "method": method, "km": round(geom.length / 1000, 1)})
        pieces.append(geom)
    merged = linemerge(MultiLineString(pieces))
    if merged.geom_type != "LineString":
        merged = LineString([pt for g in pieces for pt in g.coords])
    return merged.simplify(30), segs


def build_corridors(network: dict | None) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    st = C.stations()
    xy_st = _project_points(st)
    G = tree = nodes = None
    if network:
        lines = _load_network(network["network"], network["network_source"])
        G, xy, nodes = build_graph(lines)
        tree = cKDTree(xy)
    rows, stop_rows = [], []
    for c in C.corridors():
        geom, segs = route_corridor(c, xy_st, G, tree, nodes)
        rail_km = sum(s["km"] for s in segs if s["method"] == "rail")
        total = sum(s["km"] for s in segs)
        rows.append({
            "id": c["id"], "name": c["name"], "short": c.get("short", c["name"]), "tier": c["tier"],
            "option_group": c.get("option_group", ""), "option": c.get("option", ""),
            "default": bool(c.get("default", not c.get("option_group"))),
            "speed": c.get("speed", ""), "speed_label": c.get("speed_label", ""), "status": c.get("status", ""), "follow": c["follow"],
            "sources": ",".join(c.get("sources", [])), "length_km": round(geom.length / 1000, 1),
            "rail_share": round(rail_km / total, 3) if total else 0.0,
            "network": network["network_source"] if network else "none",
            "segments": segs, "geometry": geom,
        })
        for order, (sid, is_stop) in enumerate(parse_waypoints(c["waypoints"])):
            if is_stop and st[sid].kind != "via":
                s = st[sid]
                stop_rows.append({"corridor": c["id"], "order": order, "station": sid, "name": s.name,
                                  "state": s.state, "kind": s.kind, "amtrak": s.amtrak or "",
                                  "geometry": Point(xy_st[sid])})
    lines = gpd.GeoDataFrame(rows, geometry="geometry", crs=C.CRS_METERS)
    stops = gpd.GeoDataFrame(stop_rows, geometry="geometry", crs=C.CRS_METERS)
    return lines, stops


def apply_ntad_station_coords(path) -> int:
    """Overwrite station coordinates with BTS NTAD Amtrak Stations where codes match (in memory)."""
    try:
        g = gpd.read_file(path)
    except Exception:  # noqa: BLE001
        return 0
    code_col = next((c for c in g.columns if c.upper() in ("CODE", "STNCODE", "STATION_CODE")), None)
    if not code_col:
        return 0
    lut = {r[code_col]: r.geometry for _, r in g.iterrows() if r.geometry is not None}
    n = 0
    for s in C.stations().values():
        if s.amtrak and s.amtrak in lut:
            p = lut[s.amtrak]
            object.__setattr__(s, "lat", p.y)
            object.__setattr__(s, "lon", p.x)
            n += 1
    return n


def qa_stations(places_path) -> pd.DataFrame:
    """Distance from each station to the nearest Natural Earth populated place (sanity check)."""
    pl = gpd.read_file(places_path).to_crs(C.CRS_METERS)
    st = C.stations()
    xy = _project_points(st)
    tree = cKDTree(np.c_[pl.geometry.x, pl.geometry.y])
    rows = []
    for k, (x, y) in xy.items():
        d, i = tree.query((x, y))
        rows.append({"station": k, "name": st[k].name, "nearest_place": pl.iloc[i]["name"],
                     "km": round(d / 1000, 1)})
    return pd.DataFrame(rows).sort_values("km", ascending=False)
