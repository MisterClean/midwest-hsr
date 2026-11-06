# Boundary overrides

These overrides apply only when using the older `hsr fetch --mirror` district
boundaries. Normal builds use Census TIGERweb's 2026 GeoJSON, including Ohio's
adopted congressional map. `config/sources.yaml` → `overrides` lists the fallback
inputs. The pipeline uses the best input present:

1. **Plan geometry** at `path` (zip/shp/geojson, one polygon per district, `district_field`).
2. **Block assignment file** at `baf_path`. `hsr fetch` downloads it from `baf_url`; you can
   also drop the file here by hand. It is dissolved on 2020 census blocks (`blocks_url`,
   exact) or, if census.gov is unreachable, on 2020 block groups from the GitHub mirror
   (block groups cut by a district line go to the district holding most of their blocks).
3. **County composition** at `composition`: whole counties are exact; split counties are
   drawn as "split between X and Y" and left out of counts.

## Ohio congressional plan (adopted 2025-10-31)

| File | What | Where to get it |
|---|---|---|
| `oh_cong_2025_plan430.zip` | The Commission's adopted plan (id 430): a zip holding `October 31 2025 CD BAF.xlsx` (276,428 blocks, columns `Block`, `DistrictID:1`), a statistics PDF and a map PDF. ~7.8 MB. | `https://redistricting.ohio.gov/api/public/districtmaps/430/download` (open in a browser; the site's pages are a JavaScript app, but this URL returns the zip directly) |
| `oh_congress_2026.zip` | Optional: an official or Redistricting Data Hub shapefile of the same plan (`oh_cong_adopted_2025`), with the district number in a `DISTRICT` field | redistrictingdatahub.org (free account) |

For a mirror build, run `hsr build && hsr analyze && hsr export && hsr report`.
Ohio's hatched split counties are then replaced by exact lines.
