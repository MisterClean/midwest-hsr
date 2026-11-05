# Data sources

## Election results (Nov 3, 2026, unofficial)

| Office | Source | Captured |
|---|---|---|
| U.S. House (95 districts) | Poliwave state delegation pages, AP feed — `https://www.poliwave.com/us/live/midterms-2026/{state}/house` | 2026-11-05 |
| U.S. Senate (8 races) | Poliwave — `https://www.poliwave.com/us/live/midterms-2026/senate` | 2026-11-05 |
| Governor (8 races) | Poliwave — `https://www.poliwave.com/us/live/midterms-2026/governors`; Wisconsin from WPR | 2026-11-05 |
| State legislatures | MultiState — `https://www.multistate.us/elections/results/{state}-2026` | 2026-11-05 |
| Cross-checks | CBS News House flip list (Nov 4); WPR Wisconsin Legislature (Nov 4); CBS News Senate projections | 2026-11-05 |

Certified replacements: state election offices (mid-Nov to mid-Dec 2026), MIT Election Data
+ Science Lab, OpenElections.

## Redistricting status used for 2026

- **Ohio**: new congressional map adopted by the Ohio Redistricting Commission on
  2025-10-31; used in 2026 (Ballotpedia, "Redistricting ahead of the 2026 elections").
- **Missouri**: 2025 map blocked; the Missouri Supreme Court (2026-09-03) held it had not
  taken effect pending a referendum, and the U.S. Supreme Court stayed a contrary federal
  order (2026-09-10). Nov 2026 used the 2022 map (SCOTUSblog).
- **Indiana**: House passed a new map 2025-12-05; Senate rejected it 2025-12-11.
- **Kansas, Illinois, Iowa, Kentucky, Michigan, Minnesota, Nebraska, Wisconsin**: no
  congressional change for 2026.

## Boundaries

- Census cartographic boundary files, `https://www2.census.gov/geo/tiger/GENZ{year}/shp/`.
- Fallback mirror: `github.com/lint/CartoBoundaryGeoFiles` @ `c8331b6` (CB 2023, GeoJSON).

## Rosters

- U.S. Congress: `github.com/unitedstates/congress-legislators` (`legislators-current.yaml`).
- State legislators and governors: `github.com/openstates/people` (commit recorded in
  `data/raw/MANIFEST.json`).

## Rail

- BTS NTAD North American Rail Network Lines and Amtrak Stations (ArcGIS FeatureServer).
- Fallback: Natural Earth 10m railroads and lakes (`github.com/nvkelso/natural-earth-vector`).

## Corridor plans

See `sources:` in `config/corridors.yaml` — Illinois High-Speed Rail Commission 2025 annual
report; High Speed Rail Alliance Midwest pages; FRA/MIPRC Midwest Regional Rail Plan (2021);
FRA Corridor ID selections (2023-12-08) and MIPRC's summary; All Aboard Ohio on the Dec 2025
Corridor ID changes; City of Fort Wayne on Midwest Connect.
