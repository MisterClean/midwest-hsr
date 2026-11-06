# Report framework: the political pathway to Midwest high-speed rail

Working outline for the report. Each section names the question it answers, the pipeline
output that feeds it, and what still has to be gathered by hand. Numbers in brackets are
filled from `docs/generated/pathway_report.md` (`hsr report`) so the text never drifts from
the data.

---

## 0. Lede and map

**Question:** Who now holds power along the lines a Midwest high-speed network would run?

- Open on the map (`web/`), default view: the 220-mph backbone over U.S. House districts.
- Headline facts: backbone length [§1], states crossed, trifecta count, House districts
  touched and their split, seats that flipped on Nov. 3 along the lines.
- One sentence on what is unofficial (results) and conceptual (alignments).

## 1. The network on the table

**Question:** What exactly is proposed, by whom, and how far along is each piece?

| Layer | Source | Pipeline |
|---|---|---|
| 220-mph backbone vision | High Speed Rail Alliance; 2009 SNCF study | `config/corridors.yaml` tier `hsr` |
| 40-year federal framework | FRA + MIPRC Midwest Regional Rail Plan (2021) | same |
| Funded planning pipeline | FRA Corridor ID selections (Dec 2023) and the Dec 2025 Core / Near-Term SDP changes | tier `regional` + status fields |
| State study | Illinois High-Speed Rail Commission, Chicago–St. Louis feasibility study (8 route options, report due mid-2026) | `option_group: chi-stl` |

To add by hand: current Corridor ID step for each corridor (Step 1 done / SDP underway /
project development), dollars obligated, and any 2025–26 federal grant cancellations.

## 2. What the Nov. 3, 2026 election changed

**Question:** Where did power shift, and does the shift sit on the rail lines?

- Governors: [table §2]. Flips: Iowa (R→D), Ohio (R→D).
- Legislatures: Wisconsin flipped to Democratic control of both chambers; Michigan and
  Minnesota moved from split to Democratic control. [table §2]
- Trifectas after inauguration: D in IL, MI, MN, WI; R in IN, MO; divided in IA, KY, OH.
  Kansas is divided if Cindy Holscher's ~7,000-vote lead holds (AP had not called it as of
  Nov 5); Nebraska has a Republican governor (Pillen) and a nonpartisan legislature.
- U.S. Senate seats that changed hands in the region (IA, KS, OH) and the open seats
  (IL, KY, MI, MN). Note: Minnesota's Amy Klobuchar won the governorship, so her Senate seat
  will be filled by appointment.
- U.S. House flips in scope [§1 flips, plus `seats.csv` where `flipped == True`].

Pipeline: `data/processed/seats.csv`, `chamber_control.csv`, `trifectas.csv`.

## 3. Corridor by corridor

**Question:** For each line, what is the sequence of yeses it needs?

For every corridor, in travel order (`pathways.json`):

1. **States crossed** and kilometers in each.
2. **Executive**: governor and party; new or returning.
3. **Legislature**: control of each chamber, seat counts, uncalled seats; trifecta status.
4. **Delegation**: both U.S. senators; the House members whose districts the line touches,
   with margins and flips.
5. **Legislators on the line**: count of state senators and representatives by party whose
   districts the line touches.
6. **Swing exposure**: seats on the line decided by < 5 points.

Corridors to treat as case studies:

- **Chicago–St. Louis (five options).** Compare how the district coalition changes by route:
  the I-55 options run through central-Illinois Republican districts; the Champaign options
  pick up different seats. Table: `optcmp` in the map's detail panel / `summary.json`.
- **Chicago–Milwaukee–Madison–Twin Cities.** Runs through three states that are all
  Democratic trifectas after Nov. 3.
- **Chicago–Indianapolis–Cincinnati** and **Chicago–Fort Wayne–Toledo–Cleveland.** Cross a
  Republican trifecta (Indiana) and a divided state (Ohio).
- **Ohio 3C+D.** Democratic governor-elect, Republican legislature; Corridor ID's Core SDP path.

## 4. Federal pathway

**Question:** Who in Washington controls the money and the rules?

- Senators and House members along the network (`pathways.json`).
- To add: committee seats for the 120th Congress once assigned (January 2027) — House
  Transportation & Infrastructure, Senate Commerce, both Appropriations THUD subcommittees.
  `unitedstates/congress-legislators` publishes `committee-membership-current.yaml`;
  extend `results.load_congress` to join it.
- To add: the federal program landscape (Corridor ID, Federal-State Partnership, CRISI) and
  2026–27 appropriations status.

## 5. State pathway

**Question:** Which states can act on their own, and which need a bipartisan deal?

- Trifecta states on the backbone vs. divided states vs. Republican trifectas.
- To add per state: state rail funding sources, recent budget votes on passenger rail,
  MIPRC membership, and any HSR-enabling statutes (Illinois' 2021 High-Speed Railway
  Commission Act).

## 6. Risks and swing seats

- Seats on the lines decided by < 5 points (§3 lists them per corridor).
- Uncalled races (status `leading` / `uncalled` in `seats.csv`).
- Boundary caveat: Missouri uses the 119th congressional layer because Census's 120th
  Missouri product still contains a superseded map. All 2026 legislative boundaries
  are loaded. Older `--mirror` builds have additional Ohio, Wisconsin, and Michigan
  caveats.

## 7. Methods and sources

Point to `docs/methodology.md` and `docs/data_sources.md`. State the snapshot date and that
results are unofficial until certification.

## Appendix tables

- A1. Every corridor × district (`corridor_districts.csv`).
- A2. Chamber control and trifectas (`chamber_control.csv`, `trifectas.csv`).
- A3. Corridor catalog with sources and status (`corridors.csv`).
