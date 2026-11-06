# Results snapshot — 2026-11-06

Unofficial results for the Nov 3, 2026 general election in the 11 in-scope states,
re-checked three days after the election. **Nothing here is certified.** States certify
between mid-November and mid-December; replace these files with certified returns (see
`src/hsr/results.py`) before publishing final numbers. The previous capture is kept in
`../2026-11-05/` so changes can be diffed.

| File | Offices | Source |
|---|---|---|
| `poliwave_us_house.csv` | U.S. House, all 95 districts | Poliwave state delegation pages (AP feed), re-read 2026-11-06 |
| `poliwave_us_senate.csv` | U.S. Senate (8 races incl. Ohio special) | Poliwave Senate index |
| `poliwave_governor.csv` | Governor (8 races) | Poliwave governors index; Kansas from JCPost/AP; Wisconsin from WPR |
| `multistate_state_leg_{ST}.csv` | Every state legislative race on the 2026 ballot | MultiState results pages (`https://www.multistate.us/elections/results/{state}-2026`), plus a `status` column |

`status` in the legislative files: `called` (winner shown), `leading` (no winner yet;
`winner` holds the candidate the page's highlights say is ahead), `uncalled` (no winner,
no stated leader). The loader keeps leading candidates out of seat totals and reports
them as "leaning".

## Changes since 2026-11-05

U.S. House
- **MI-4** (Sean McCann, D) and **MI-7** (William Lawrence, D) now called.
- **NE-1** called for Mike Flood (R); Chris Backemeyer conceded (KLKN-TV). Poliwave still
  shows "Counting".
- **MN-1** still not called: Jake Johnson (D) leads Brad Finstad (R) 50.0–49.9 and Finstad
  has requested a recount (MPR News, Nov 5).
- Kentucky, Missouri, Iowa, Kansas, Indiana: all races now labeled called.
- Small percentage updates in IL (all 17), MI-2/5/12, MN-8, OH-7/9.

Statewide
- **Nebraska governor** now called for Jim Pillen (R).
- **Kansas governor** still not called: Cindy Holscher (D) leads Ty Masterson (R) by
  7,045 votes with ~99% counted; AP has not called it (JCPost, Nov 5, 7 pm). Poliwave
  labels it "Elected"; we keep it as leading.
- Illinois Senate and governor percentages updated.

State legislatures (newly called)
- IL HD-65 Ricky Rivard (D), HD-104 Mary Catherine Roberson (D)
- IA HD-21 Brooke Boden (R), HD-46 Mandy Newton Rosenow (D), HD-83 Cindy Golding (R), HD-94 Mike Vondran (R)
- KS HD-30 Amelia Wiederaenders (D), HD-39 Zach Maier (D), HD-60 Mark Schreiber (R), HD-78 Tim Lundberg (D)
- MI HD-28 Sherry A. Berecz (D), HD-57 Thomas Turner (D), HD-60 Joe Aragona (R), SD-32 Rebecca Amidon (D)
- MN SD-24 Simon Glaser (D), SD-54 Rick Olson (D)
- NE LD-14 Bill Bowes, LD-18 Jess Goldoni, LD-36 Rick Holdcroft

Still open, with leader where reported: IL HD-48 (D), HD-70 (R), HD-114 (D), HD-118 (R),
SD-35; IA HD-19 (R), SD-47 (D); MN HD-32A (R, recount likely), SD-4 (R by 4 votes, recount),
SD-33 (R), HD-2A; NE LD-4 (Maxwell-Ostdiek); IN HD-5, HD-7, HD-78, SD-45; KS HD-8, 26, 27,
40, 43, 117, 123; KY HD-36; MI HD-31 (page shows Perry ahead but also reports a concession;
left uncalled); MO HD-69, HD-107, SD-34; OH HD-29, 37, 44, 72, 75, SD-13.

Not changed: Minnesota SD-66 and SD-67 came back blank only because the page was truncated
for the extractor; the Nov 5 calls (Verbeten, Hawj) are kept.

## Cross-checks
- Ohio House 52 R / 42 D with 5 uncalled and Senate 21 R / 11 D with 1 uncalled match the
  totals in MultiState's Ohio highlights.
- Wisconsin: 3 Senate and 8 Assembly flips match WPR; Senate 18–15 D, Assembly 53–46 D.
