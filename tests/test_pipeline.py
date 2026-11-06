"""Unit tests that run offline (no downloads)."""
import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString

from hsr import config as C
from hsr import results, routing
from hsr.districts import norm_district


@pytest.mark.parametrize("raw,expected", [
    ("01", "1"), ("009A", "9A"), ("HD-12", "12"), ("SD-3", "3"), ("District 7", "7"), ("67B", "67B"),
    ("Indiana 4", "INDIANA 4"),
])
def test_norm_district(raw, expected):
    assert norm_district(raw) == expected


def test_norm_party():
    assert results.norm_party("Democratic Party") == "D"
    assert results.norm_party("REP") == "R"
    assert results.norm_party("NP") == "NP"
    assert results.norm_party("R; D") == "R"
    assert results.norm_party("") == ""


def test_parse_waypoints():
    assert routing.parse_waypoints(["CHI", "~DWT", "SPI"]) == [("CHI", True), ("DWT", False), ("SPI", True)]


def test_config_integrity():
    st = C.stations()
    ids = set()
    for c in C.corridors():
        assert c["id"] not in ids, c["id"]
        ids.add(c["id"])
        assert c["follow"] in ("rail", "direct")
        for w, _ in routing.parse_waypoints(c["waypoints"]):
            assert w in st, f"{c['id']}: unknown station {w}"
        for s in c.get("sources", []):
            assert s in C.corridor_sources(), f"{c['id']}: unknown source {s}"
    groups = {}
    for c in C.corridors():
        if c.get("option_group"):
            groups.setdefault(c["option_group"], []).append(bool(c.get("default")))
    for g, flags in groups.items():
        assert sum(flags) == 1, f"option group {g} needs exactly one default"


def test_snapshot_loads_and_is_complete():
    df = results.load_snapshot()
    assert not df.duplicated(["office", "state", "district"]).any()
    house = df[df.office == "us_house"]
    assert len(house) == 95
    called = df[df.status == "called"]
    assert called.party.isin(["D", "R", "I", "NP", "L", "G"]).all()
    # Every 2026 state-legislative winner sits in a chamber we model.
    leg = df[df.office.isin(["state_senate", "state_house"])]
    sizes = C.chamber_sizes()
    for (st, off), g in leg.groupby(["state", "office"]):
        assert off in sizes[st]
        assert len(g) <= sizes[st][off]


def test_route_on_synthetic_graph():
    # A dog-leg track from (0,0) to (10km,0) to (10km,10km); route must follow it.
    lines = gpd.GeoDataFrame(geometry=[LineString([(0, 0), (10000, 0), (10000, 10000)])], crs=C.CRS_METERS)
    G, xy, nodes = routing.build_graph(lines)
    from scipy.spatial import cKDTree
    tree = cKDTree(xy)
    corridor = {"id": "t", "follow": "rail", "waypoints": ["A", "B"]}
    geom, segs = routing.route_corridor(corridor, {"A": (0, 0), "B": (10000, 10000)}, G, tree, nodes)
    # 20 km of track vs 14.1 km straight: ratio 1.41 < DETOUR_MAX, so it routes on rail
    assert segs[0]["method"] == "rail"
    assert abs(geom.length - 20000) < 200


def test_route_falls_back_to_direct_when_far():
    lines = gpd.GeoDataFrame(geometry=[LineString([(0, 0), (1000, 0)])], crs=C.CRS_METERS)
    G, xy, nodes = routing.build_graph(lines)
    from scipy.spatial import cKDTree
    corridor = {"id": "t", "follow": "rail", "waypoints": ["A", "B"]}
    _, segs = routing.route_corridor(corridor, {"A": (0, 0), "B": (0, 50000)}, G, cKDTree(xy), nodes)
    assert segs[0]["method"] == "direct"


def test_chamber_control_majority():
    seats = pd.DataFrame(
        [{"office": "state_senate", "state": "WI", "party": "D", "status": "called"}] * 18
        + [{"office": "state_senate", "state": "WI", "party": "R", "status": "holdover"}] * 15
        + [{"office": "state_house", "state": "WI", "party": "D", "status": "called"}] * 53
        + [{"office": "state_house", "state": "WI", "party": "R", "status": "called"}] * 46)
    ctrl = results.chamber_control(seats)
    wi = ctrl[ctrl.state == "WI"].set_index("office")
    assert wi.loc["state_senate", "control"] == "D"
    assert wi.loc["state_house", "control"] == "D"
    assert wi.loc["state_senate", "D"] == 18


# ------------------------------------------------------------------ Ohio 2026 map
OHIO_COUNTIES = 88


def test_ohio_composition_is_complete():
    import yaml
    comp = yaml.safe_load(open(C.ROOT / "config" / "ohio_cd_2026_counties.yaml"))
    whole = [c for cs in comp["whole"].values() for c in (cs or [])]
    split = comp["split"]
    listed = whole + list(split)
    assert len(listed) == len(set(listed)) == OHIO_COUNTIES
    assert all(len(ds) == 2 and ds[0] != ds[1] for ds in split.values())
    present = {int(d) for d, cs in comp["whole"].items() if cs} | {d for ds in split.values() for d in ds}
    assert present == set(range(1, comp["districts"] + 1)), "every district needs territory"
    # District 4 per the Commission's BAF (via allen-county-ohio): 11 whole + Clark, Delaware, Richland.
    assert len(comp["whole"][4]) == 11
    assert {c for c, ds in split.items() if 4 in ds} == {"Clark", "Delaware", "Richland"}


def test_read_baf_csv_and_zip(tmp_path):
    import zipfile
    from hsr.districts import read_baf
    csv = tmp_path / "baf.csv"
    csv.write_text("Block,DistrictID:1\n390010001001000,2\n390010001001001,2\n")
    df = read_baf(csv)
    assert df.to_dict("records") == [{"block": "390010001001000", "district": "2"},
                                     {"block": "390010001001001", "district": "2"}]
    z = tmp_path / "plan.zip"
    with zipfile.ZipFile(z, "w") as zz:
        zz.writestr("stats.pdf", b"%PDF")
        zz.writestr("October 31 2025 CD BAF.csv", csv.read_text())
    assert len(read_baf(z)) == 2


def test_baf_to_block_groups_majority_and_ties():
    from hsr.districts import baf_to_block_groups
    baf = pd.DataFrame({
        "block": ["390010001001000", "390010001001001", "390010001001002",   # bg ...0011: 2,2,3
                  "390010001002000", "390010001002001"],                    # bg ...0012: 3,4 (tie)
        "district": ["2", "2", "3", "4", "3"]})
    best, split = baf_to_block_groups(baf)
    got = dict(zip(best.bg, best.district))
    assert got == {"390010001001": "2", "390010001002": "3"}
    assert split == 2
