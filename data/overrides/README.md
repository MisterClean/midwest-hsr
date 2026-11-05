# Boundary overrides

Drop official plan files here when a state's 2026 lines are newer than the Census
vintage the pipeline downloads. `config/sources.yaml` → `overrides` lists what is
expected. Currently:

| File | What | Where to get it |
|---|---|---|
| `oh_congress_2026.zip` | Ohio congressional plan adopted by the Ohio Redistricting Commission on 2025-10-31 (used Nov 2026) | Ohio Redistricting Commission or Ohio Secretary of State "adopted plan" shapefile; one polygon per district with a `DISTRICT` field |

Then run `make build analyze export report`. Districts covered by an override stop
being drawn hatched and start counting toward corridor totals.
