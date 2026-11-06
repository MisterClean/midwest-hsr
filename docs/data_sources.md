# Data sources

## Election results (Nov 3, 2026, unofficial; latest snapshot 2026-11-06)

| Office | Source | Captured |
|---|---|---|
| U.S. House (95 districts) | Poliwave state delegation pages, AP feed — `https://www.poliwave.com/us/live/midterms-2026/{state}/house` | 2026-11-06 |
| U.S. Senate (8 races) | Poliwave — `https://www.poliwave.com/us/live/midterms-2026/senate` | 2026-11-06 |
| Governor (8 races) | Poliwave — `https://www.poliwave.com/us/live/midterms-2026/governors`; Wisconsin from WPR; Kansas from JCPost | 2026-11-06 |
| State legislatures | MultiState — `https://www.multistate.us/elections/results/{state}-2026` (uncalled races re-checked) | 2026-11-06 |
| Cross-checks | CBS News House flip list (Nov 4); WPR Wisconsin Legislature (Nov 4); CBS News Senate projections | 2026-11-05 |
| Late calls | MPR News (MN-1 recount, Nov 5); KLKN-TV (NE-1 concession); JCPost (Kansas governor not called, Nov 5) | 2026-11-06 |

Certified replacements: state election offices (mid-Nov to mid-Dec 2026), MIT Election Data
+ Science Lab, OpenElections.

## Ohio 2026 congressional plan

- Adopted plan (id 430) and block assignment file: Ohio Redistricting Commission,
  `https://redistricting.ohio.gov/api/public/districtmaps/430/download` (route documented in
  github.com/goedelsoup/allen-county-ohio, `.yidam/catalog/ohio-redistricting-commission.md`).
- County composition: Ohio Secretary of State "U.S. Congressional Districts 2026-2032"
  county list, via the Lorain County Board of Elections copy; Putnam County placement from
  The Crescent-News; District 4 cross-checked against the BAF aggregation in
  allen-county-ohio.
- Census 2020 blocks for exact geometry: `tl_2020_39_tabblock20.zip` (TIGER2020).

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

- [Census TIGERweb Legislative service](https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Legislative/MapServer): layer 0 is the 120th Congressional Districts; layers 1 and 2 are the 2026 upper and lower state legislative districts. The fetcher queries each of the 11 states separately as full-resolution EPSG:4326 GeoJSON, checks the feature count against the number of seats, and records source URLs and a SHA-256 in `data/raw/MANIFEST.json`.
- Missouri's 2026 congressional geometry comes from [TIGERweb layer 4](https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Legislative/MapServer/4), the 119th Congress. [Census warns](https://www.census.gov/programs-surveys/decennial-census/about/rdo/congressional-districts.html) that its 120th products still include the superseded 2025 map; the 2022/2024 lines were used in 2026. Switch Missouri only after Census confirms regeneration.
- States and counties for context come from Census 2024 cartographic boundary files. The old [2023 GeoJSON mirror](https://github.com/lint/CartoBoundaryGeoFiles/tree/c8331b6ddad3b2762c2c3c89433b7067c53ab383/data/cb_2023_us_all_500k) remains available with `hsr fetch --mirror` for offline fallback; those legislative boundaries are flagged where outdated.
- [TIGER/Line 2026 shapefiles](https://www2.census.gov/geo/tiger/TIGER2026/) are an alternate high-resolution source by state (`CD`, `SLDU`, `SLDL`), but TIGERweb is the direct GeoJSON source used here. The map export simplifies these full-resolution inputs to compact TopoJSON.

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
