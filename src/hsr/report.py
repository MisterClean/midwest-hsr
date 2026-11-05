"""Generate the data sections of the political-pathway report as Markdown.

Writes docs/generated/pathway_report.md from data/processed/*. The narrative
skeleton lives in docs/report_framework.md; this file supplies its tables.
"""
from __future__ import annotations

import json

import pandas as pd

from . import config as C

PARTY = {"D": "D", "R": "R", "NP": "NP", "I": "I", "": "–"}


def _fmt_margin(m) -> str:
    return "" if m is None or pd.isna(m) else f"{m:+.1f}"


def build() -> str:
    P = C.PROCESSED
    summ = json.loads((P / "summary.json").read_text())
    paths = json.loads((P / "pathways.json").read_text())
    cors = pd.read_csv(P / "corridors.csv", keep_default_na=False)
    ctrl = pd.read_csv(P / "chamber_control.csv")
    tri = pd.read_csv(P / "trifectas.csv", keep_default_na=False)
    seats = pd.read_csv(P / "seats.csv", dtype={"district": str}, keep_default_na=False)
    cd = pd.read_csv(P / "corridor_districts.csv", dtype={"district": str}, keep_default_na=False)
    meta = json.loads((C.WEB_DATA / "analysis.json").read_text())["meta"] if (C.WEB_DATA / "analysis.json").exists() else {}

    out = ["# Midwest HSR political pathway: data tables", "",
           f"_Generated from the pipeline. Results snapshot: {meta.get('results_snapshot', 'n/a')} (unofficial). "
           f"Boundary vintage: {meta.get('boundary_vintage', 'n/a')}. Rail network: {meta.get('rail_network', 'n/a')}._", ""]

    core = summ["network"]["hsr_core"]
    out += ["## 1. Network at a glance", "",
            f"- High-speed backbone (default options): **{core['km']:,.0f} km** across "
            f"{len(core['corridors'])} corridors.",
            ]
    for office, label in (("us_house", "U.S. House"), ("state_senate", "state senate"),
                          ("state_house", "state house")):
        c = core[office]
        out.append(f"- {label} districts touched: **{c['districts']}** ({c['D']} D, {c['R']} R, "
                   f"{c['other']} other, {c['pending_boundaries']} on boundaries pending update; "
                   f"{c['flipped_to_D']} flipped to D, {c['flipped_to_R']} flipped to R, {c['close']} decided by <5 pts).")
    out.append("")

    out += ["## 2. Who governs each state after Nov. 3, 2026", "",
            "| State | Governor | State senate (D–R) | State house (D–R) | Status |", "|---|---|---|---|---|"]
    for t in tri.itertuples():
        g = seats[(seats.office == "governor") & (seats.state == t.state)].iloc[0]
        cells = []
        for off in ("state_senate", "state_house"):
            r = ctrl[(ctrl.state == t.state) & (ctrl.office == off)]
            cells.append("—" if r.empty else
                         ("nonpartisan" if r.iloc[0].control == "nonpartisan"
                          else f"{r.iloc[0].control} {r.iloc[0].D}–{r.iloc[0].R}"
                               + (f" ({r.iloc[0].uncalled} uncalled)" if r.iloc[0].uncalled else "")))
        flip = " (flip)" if str(g.flipped) == "True" else ""
        out.append(f"| {t.state} | {g.holder} ({g.party}){flip} | {cells[0]} | {cells[1]} | {t.trifecta} |")
    out.append("")

    out += ["## 3. Corridor pathways", ""]
    for c in cors.itertuples():
        s = summ["corridors"].get(c.id, {})
        out += [f"### {c.name}", "",
                f"`{c.id}` · tier **{c.tier}** · {c.length_km:,.0f} km · {c.speed}",
                "", f"Status: {c.status}", ""]
        if s:
            h = s["us_house"]
            out.append(f"U.S. House districts: {h['D']} D / {h['R']} R"
                       + (f" / {h['pending_boundaries']} pending" if h["pending_boundaries"] else "")
                       + f"; state legislative: {s['state_senate']['D'] + s['state_house']['D']} D / "
                         f"{s['state_senate']['R'] + s['state_house']['R']} R.")
            out.append("")
        out += ["| State | km | Governor | Trifecta | U.S. senators | U.S. House along line (margin) |",
                "|---|---|---|---|---|---|"]
        for st in paths.get(c.id, []):
            gov = st["governor"]
            sens = ", ".join(f"{x['name']} ({x['party']})" for x in st["us_senators"])
            reps = "; ".join(f"{st['state']}-{r['district']} {r['name']} ({r['party']}{', ' + _fmt_margin(r['margin']) if r['margin'] is not None else ''})"
                             + (" *flip*" if r["flipped"] else "") for r in st["us_house_along"])
            out.append(f"| {st['state']} | {st['km']:.0f} | {gov['name']} ({gov['party']}) | {st['trifecta']} | {sens} | {reps} |")
        swing = cd[(cd.corridor == c.id) & (cd.margin != "")]
        swing = swing[pd.to_numeric(swing.margin, errors="coerce").abs() < 5]
        if len(swing):
            out += ["", "Seats along this line decided by under 5 points: "
                    + ", ".join(f"{r.id.split(':', 1)[1]} {r.holder} ({r.party}, {float(r.margin):+.1f})" for r in swing.itertuples())]
        out.append("")
    return "\n".join(out)


def write() -> None:
    dest = C.ROOT / "docs" / "generated" / "pathway_report.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(build(), encoding="utf-8")
    print(f"wrote {dest.relative_to(C.ROOT)}")
