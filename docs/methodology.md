# Methodology

## Scope

Eleven states that a Chicago-hub network would reach: IL, IN, IA, KS, KY, MI, MN, MO, NE,
OH, WI. Offices: U.S. House, U.S. Senate, governor, state senate, state house (Nebraska's
unicameral, nonpartisan Legislature is modeled as its state senate).

## Seats after the election

`results.seats()` builds one row per seat:

1. **On the 2026 ballot** → the winner from the results snapshot. Uncalled races keep the
   current leader where the source shows one (`status = leading`) and are blank otherwise
   (`status = uncalled`).
2. **Not on the ballot** (staggered senates, Kansas Senate, U.S. senators not up, governors
   of IN / KY / MO) → the sitting member from OpenStates or `congress-legislators`
   (`source = holdover`).
3. **Flip** = the 2026 winner's party differs from the sitting member's party going into the
   election. For Ohio's redrawn congressional districts, "sitting member" means the
   incumbent of the same district number, which is approximate.
4. The Ohio special U.S. Senate election replaces the appointee (most recent term start); the
   regular class-2 elections replace the senator whose term ends 2027-01-03.

Chamber control counts called seats plus holdovers; a party controls a chamber when it holds
a majority of all seats. Trifecta = governor and both chambers held by the same party.

## Boundaries

Census cartographic boundary files (1:500k). Each district carries `boundary_status`:

- `current` — the file reflects the lines used in Nov 2026.
- `pending` — the 2026 lines are newer than the file (see `config/sources.yaml →
  vintage_caveats` and `overrides`). Pending districts are hatched on the map, still show
  their 2026 winner by district number in tooltips, and are **excluded** from district counts.
  Michigan's court-ordered Detroit-area redraw is approximated by flagging legislative
  districts whose interior point falls in Wayne/Oakland/Macomb counties' envelope.

### Ohio's 2026 congressional map

The plan adopted by the Ohio Redistricting Commission on 2025-10-31 (plan 430) is not in any
Census release, and the Commission published it only as a block assignment file. The pipeline
resolves it in this order (`districts.resolve_override`):

1. an official plan shapefile, if supplied;
2. the block assignment file dissolved on 2020 census blocks (exact), or on 2020 block groups
   when blocks are unavailable (approximate only where a line cuts a block group);
3. the official county composition (`config/ohio_cd_2026_counties.yaml`, from the Secretary
   of State's county list). Of 88 counties, 73 lie wholly in one district and are drawn
   exactly. The 15 split counties are drawn as separate "split" pieces carrying both possible
   districts; they are hatched, left out of district counts, and listed with both members in
   corridor pathways. This is the mode used for the committed build.

District-level flips in Ohio compare the 2026 winner with the incumbent of the same district
number, which is approximate because the lines changed.

## Corridors

Each corridor in `config/corridors.yaml` is an ordered list of stations from its source
documents.

- `follow: rail` — route on the rail network: lines are densified to 250 m, vertices snapped
  to a 25 m grid, dangling ends within 600 m joined, then Dijkstra between consecutive
  waypoints. A segment falls back to a straight line if a waypoint is > 6 km from the network
  or the route is > 1.45× the straight-line distance. Each segment's method is recorded in
  `corridor_segments.csv`.
- `follow: direct` — conceptual alignment through the named cities and shaping points. Used
  for the Illinois HSR study's options, which are defined by city sequence and right-of-way
  type (interstate, greenfield) but not yet published as GIS.

Positional accuracy: NTAD ≈ tens of meters; Natural Earth ≈ 1–2 km; direct segments can be
several km from any eventual alignment. District counts are most reliable for congressional
districts and least reliable for small urban state house districts.

## Corridor × district

A district is **touched** by a corridor when ≥ 0.5 km of the line lies inside it (in
EPSG:5070) or a named stop is inside it. Network totals de-duplicate districts touched by
several corridors and use each option group's default option.

## Margins

Winner's share minus runner-up's share, in percentage points, where the source published
percentages (federal races and governors). State legislative margins are blank in the
current snapshot.

## Known limitations

- Results are unofficial (latest capture 2026-11-06; previous 2026-11-05 kept for diffing).
- State legislative results were transcribed from MultiState's results pages by an automated
  extractor and spot-checked; verify individual rows against the state before quoting them.
- Nebraska senators are nonpartisan; the map does not assign party affiliation.
