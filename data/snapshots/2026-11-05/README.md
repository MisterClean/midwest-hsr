# Results snapshot — 2026-11-05

Unofficial results for the Nov 3, 2026 general election in the 11 in-scope states,
captured two days after the election. **Nothing here is certified.** States certify
between mid-November and mid-December; replace these files with certified returns
(see `src/hsr/results.py`) before publishing final numbers.

| File | Offices | Source | Notes |
|---|---|---|---|
| `poliwave_us_house.csv` | U.S. House, all 95 districts | Poliwave state delegation pages (AP feed) | `status` is the page's own label; blank = page showed counts but no label. `leading` = not yet called. |
| `poliwave_us_senate.csv` | U.S. Senate (8 races incl. Ohio special) | Poliwave Senate index | Nebraska runner-up % omitted: page combined all non-R candidates. |
| `poliwave_governor.csv` | Governor (8 races) | Poliwave governors index; WPR for Wisconsin; WIBW for Kansas | Nebraska still `Counting`. Kansas set to `Leading`: Poliwave showed it as elected, but WIBW (Nov 4) and other Kansas outlets reported it too close to call with Holscher ahead 50.3–49.7. Wisconsin % not published on the page used. |
| `multistate_state_leg_{ST}.csv` | Every state legislative race on the 2026 ballot | MultiState election results pages (`https://www.multistate.us/elections/results/{state}-2026`) | `winner = none` means the page showed no winner yet (uncalled). `runnerup` lists other candidates when there is no winner. Nebraska is nonpartisan (`NP`). |

How these were captured: each page was read on 2026-11-05 and its results table
transcribed to CSV with an automated extractor, then spot-checked against a second
outlet (WPR for the Wisconsin Legislature flips and seat counts; CBS News for the
House flips; Poliwave for Illinois Senate districts). Seats that were not on the
2026 ballot are filled from the OpenStates roster by the pipeline, not from here.

Spot checks that passed:
- Wisconsin: 3 Senate and 8 Assembly flips match WPR (Nov 4, 2026); resulting
  Senate 18-15 D and Assembly 53-46 D match WPR's AP-based totals.
- U.S. House flips in scope match CBS News' flip list (Nov 4, 2026, 11:32 pm ET).
  Poliwave adds two later Ohio flips (OH-10, OH-15) that the CBS list predates;
  confirm both against the Ohio Secretary of State before citing them. Ohio Capital
  Journal (Nov 4) reported an 8–7 Democratic delegation, consistent with these rows;
  OH-10 had a Decision Desk HQ projection before AP called it.
