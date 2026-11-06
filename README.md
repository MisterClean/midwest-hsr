# Midwest HSR: who holds the track?

A reproducible pipeline and interactive map for a report on the **political pathway to a
Midwest high-speed rail network**. It lays every seriously proposed high-speed and regional
rail corridor radiating from Chicago over the U.S. House, U.S. Senate, governor and state
legislative results of the **November 3, 2026** election, then answers, line by line:
which states it crosses, who governs each one, whether that state has a trifecta, and which
members of Congress and state legislators represent the districts it runs through.

```
config/         corridors, stations, states, data sources   ← edit these, not code
src/hsr/        pipeline (fetch → build → analyze → export → report)
data/snapshots/ 2026 results (latest: 2026-11-06), with per-row source URLs
data/processed/ seats, chamber control, trifectas, corridor×district joins (committed)
web/            the map (index.html + data/ written by `hsr export`)
docs/           report framework, methodology, data sources, generated tables
tests/          offline unit tests
```

## Quick start

```bash
pip install -e ".[dev]"        # Python ≥ 3.10
npm install -g mapshaper@0.6   # TopoJSON export
hsr all                        # fetch + build + analyze + export + report + qa
python -m http.server -d web   # open http://localhost:8000
```

`hsr all` needs internet access to Census TIGERweb, the BTS NTAD ArcGIS services and GitHub.
Without Census / NTAD, `hsr fetch --mirror` uses GitHub-hosted fallbacks (see
[Current build](#current-build)).

| Command | What it does | Main outputs |
|---|---|---|
| `hsr fetch [--mirror]` | Downloads boundaries, rosters, rail network; logs URL + SHA-256 | `data/raw/`, `data/raw/MANIFEST.json` |
| `hsr build` | Cleans district layers and tags boundary vintage; merges 2026 results with holdover seats; routes corridors | `data/interim/*.gpkg`, `data/processed/seats.csv`, `chamber_control.csv`, `trifectas.csv`, `corridors.csv` |
| `hsr analyze` | Corridor × district joins, network totals, per-state pathway | `corridor_districts.csv`, `summary.json`, `pathways.json` |
| `hsr export` | Simplified TopoJSON + JSON bundle for the map | `web/data/` |
| `hsr report` | Markdown tables for the report | `docs/generated/pathway_report.md` |
| `hsr qa` | Seat coverage per chamber, segments drawn off-rail | console |

## Current build

The committed outputs were rebuilt on 2026-11-06 with the latest Census district
geometry available for the 2026 election:

| Input | Used for this build | Authoritative source (`hsr fetch`) |
|---|---|---|
| District boundaries | Census TIGERweb **2026** full-resolution GeoJSON: 120th Congress, 2026 state upper and lower districts | Same; per-state URLs and count checks in `data/raw/MANIFEST.json` |
| Missouri congressional map | Census TIGERweb **119th** layer, which matches the 2026 election map | Replace with 120th only after Census confirms correction |
| Ohio 2026 congressional map | Census TIGERweb **120th** layer | Same |
| State/county background | Census CB **2024** | Same |
| Rail network for routing | Natural Earth 10m railroads | BTS NTAD North American Rail Network |
| Station coordinates | `config/stations.yaml` | BTS NTAD Amtrak Stations (matched by code) |
| 2026 results | `data/snapshots/2026-11-06` (unofficial) | same, until certified returns are loaded |
| Sitting members | unitedstates/congress-legislators, openstates/people @ `bcdda40` | same |

Consequences you will see in the map and tables:

- All **95 U.S. House**, **491 state senate**, and **1,148 state house** districts in scope
  have 2026 election geometry. The Missouri congressional exception is explicitly sourced
  from the 119th layer, which has the map used in 2022, 2024, and 2026. Census warns that
  its current 120th Missouri product still contains the superseded 2025 map.
- The full-resolution GeoJSON is simplified only for the browser's compact TopoJSON files;
  corridor intersections use the original geometry.
- On rail-following corridors, 35 of 123 station-to-station segments (about 2,050 of
  7,030 km, across 13 corridors) fell back to straight lines where Natural Earth has no track
  or the routed path was a long detour. `hsr qa` lists them. The NTAD response was incomplete
  (10,000 of 81,866 lines in the map area), so the fetcher rejected it and used Natural Earth.

## Updating

- **Certified results.** States certify from mid-November to mid-December. Load MEDSL or
  OpenElections returns with `results.from_medsl_house` / `results.from_openelections`, or
  replace the CSVs in a new `data/snapshots/<date>/` and point `config/sources.yaml →
  results.snapshot` at it. Rows keep their source URL.
- **New corridor or option.** Add stations to `config/stations.yaml` and an entry to
  `config/corridors.yaml` (waypoints, `follow: rail|direct`, sources). `~ID` marks a
  pass-through point that is not a stop. `make test` checks the config.
- **Boundary changes.** Remove the cached `data/raw/boundaries/*_2026.geojson` files and
  re-run `hsr all` to refresh Census TIGERweb. The Missouri 119th
  exception is configured as `missouri_congress_layer` in `config/sources.yaml`. For local
  plans or the older mirror fallback, add an entry under `overrides`. Each override
  takes, in order of preference, an official plan shapefile (`path`), a block assignment file
  (`baf_url` / `baf_path`, dissolved on 2020 blocks or, offline, block groups), or an official
  county list (`composition`).

## The map

`web/index.html` is a single page (D3 + topojson-client from cdnjs/jsDelivr) that loads
`web/data/*.json`. It is published as a Claude artifact; any static host works. Deep links
use the corridor id as the hash, e.g. `#chi-stl-3`.

## Caveats

Results are unofficial and include uncalled races (shown with the current leader where
one exists). Corridor geometry is conceptual: stops come from each plan, and lines are
routed on existing track or drawn between named cities. "Touched" means ≥ 0.5 km of line
inside the district or a named stop in it. See `docs/methodology.md`.
