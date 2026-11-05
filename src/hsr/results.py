"""Election results + rosters -> one row per seat after the 2026 election.

Seat table columns
------------------
id, office, state, district, holder, party, source ('2026' | 'holdover' | 'vacant'),
status ('called' | 'leading' | 'uncalled' | 'reported' | 'holdover'), winner_pct,
runnerup, runnerup_party, runnerup_pct, margin, prior_holder, prior_party, flipped,
source_url.

`party` is the party of the person who will hold the seat in 2027 (for uncalled
races, the current leader if one is shown, else blank). `prior_party` is the party of
the sitting member going into the election, from the roster.
"""
from __future__ import annotations

import glob
import logging
import re
from pathlib import Path

import pandas as pd
import yaml

from . import config as C
from .districts import norm_district

log = logging.getLogger(__name__)

PARTY = {
    "d": "D", "dem": "D", "democratic": "D", "democratic party": "D", "democrat": "D",
    "democratic-farmer-labor": "D", "dfl": "D",
    "r": "R", "rep": "R", "republican": "R", "republican party": "R", "gop": "R",
    "i": "I", "ind": "I", "independent": "I",
    "np": "NP", "nonpartisan": "NP",
    "l": "L", "lib": "L", "libertarian": "L", "g": "G", "green": "G",
}
CHAMBER = {"house": "state_house", "assembly": "state_house", "senate": "state_senate",
           "legislature": "state_senate"}
STATUS = {"elected": "called", "called": "called", "leading": "leading", "counting": "leading",
          "not called": "leading", "": "reported"}


def norm_party(p) -> str:
    if p is None or (isinstance(p, float) and pd.isna(p)):
        return ""
    first = str(p).split(";")[0].strip().lower()
    return PARTY.get(first, first.upper()[:3] if first else "")


def _pct(v):
    if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == "":
        return None
    m = re.search(r"[\d.]+", str(v))
    return float(m.group()) if m else None


def _first(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v).split(";")[0].strip()


# ------------------------------------------------------------------ snapshot loaders
def load_snapshot(snapshot: Path | None = None) -> pd.DataFrame:
    snap = Path(snapshot or C.ROOT / C.sources()["results"]["snapshot"])
    rows = []
    for office, fname in (("us_house", "poliwave_us_house.csv"), ("us_senate", "poliwave_us_senate.csv"),
                          ("governor", "poliwave_governor.csv")):
        df = pd.read_csv(snap / fname, dtype=str, keep_default_na=False)
        for r in df.to_dict("records"):
            rows.append({
                "office": office, "state": r["state"],
                "district": norm_district(r["district"]) if office == "us_house" else r["district"],
                "winner": r["winner"], "party": norm_party(r["party"]),
                "winner_pct": _pct(r["winner_pct"]), "runnerup": _first(r["runnerup"]),
                "runnerup_party": norm_party(r["runnerup_party"]), "runnerup_pct": _pct(r["runnerup_pct"]),
                "status": STATUS.get(r["status"].strip().lower(), r["status"].strip().lower()),
                "source_url": r["source_url"],
            })
    for f in sorted(glob.glob(str(snap / "multistate_state_leg_*.csv"))):
        st = Path(f).stem.rsplit("_", 1)[-1]
        df = pd.read_csv(f, dtype=str, keep_default_na=False)
        for r in df.to_dict("records"):
            none = r["winner"].strip().lower() in ("", "none")
            rows.append({
                "office": CHAMBER[r["chamber"].strip().lower()], "state": st,
                "district": norm_district(r["district"]),
                "winner": "" if none else r["winner"].strip(),
                "party": "" if none else norm_party(r["party"]),
                "winner_pct": None, "runnerup": _first(r["runnerup"]),
                "runnerup_party": norm_party(r["runnerup_party"]), "runnerup_pct": None,
                "status": "uncalled" if none else "called",
                "source_url": f"https://www.multistate.us/elections/results/{C.states()[st]['name'].lower()}-2026",
            })
    out = pd.DataFrame(rows)
    out["margin"] = out["winner_pct"] - out["runnerup_pct"]
    dup = out.duplicated(["office", "state", "district"], keep=False)
    if dup.any():
        raise ValueError(f"duplicate result rows:\n{out[dup]}")
    return out


# --------------------------------------------------------------------------- rosters
def load_openstates(root: Path) -> pd.DataFrame:
    """Current state legislators and governors from an openstates/people checkout."""
    rows = []
    for st in C.states():
        for kind in ("legislature", "executive"):
            for f in glob.glob(str(root / "data" / st.lower() / kind / "*.yml")):
                with open(f, encoding="utf-8") as fh:
                    p = yaml.safe_load(fh)
                party = norm_party((p.get("party") or [{}])[-1].get("name"))
                for role in p.get("roles", []):
                    if role.get("end_date"):
                        # executive roles carry their scheduled end; keep governors whose term is current
                        if not (role.get("type") == "governor"):
                            continue
                    t = role.get("type")
                    if t in ("upper", "legislature"):
                        office = "state_senate"
                    elif t == "lower":
                        office = "state_house"
                    elif t == "governor":
                        office = "governor"
                    else:
                        continue
                    rows.append({"office": office, "state": st,
                                 "district": norm_district(role.get("district", "")) if office != "governor" else "",
                                 "holder": p["name"], "party": party, "start": str(role.get("start_date", "")),
                                 "end": str(role.get("end_date", "") or ""), "ocd_id": p["id"]})
    df = pd.DataFrame(rows)
    gov = df[df.office == "governor"].sort_values("start").groupby("state").tail(1)
    leg = df[df.office != "governor"].sort_values("start").groupby(["office", "state", "district"]).tail(1)
    return pd.concat([leg, gov], ignore_index=True)


def load_congress(path: Path) -> pd.DataFrame:
    with open(path, encoding="utf-8") as fh:
        people = yaml.safe_load(fh)
    rows = []
    for p in people:
        term = p["terms"][-1]
        if term["state"] not in C.states():
            continue
        name = p["name"].get("official_full") or f"{p['name']['first']} {p['name']['last']}"
        office = "us_house" if term["type"] == "rep" else "us_senate"
        rows.append({"office": office, "state": term["state"],
                     "district": str(term.get("district", "")) if office == "us_house" else f"class{term.get('class')}",
                     "holder": name, "party": norm_party(term.get("party")), "start": term["start"], "end": term["end"],
                     "bioguide": p["id"]["bioguide"]})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------ seat table
def seats(results: pd.DataFrame, openstates: pd.DataFrame, congress: pd.DataFrame) -> pd.DataFrame:
    """Combine 2026 results with holdovers into one row per seat."""
    sizes = C.chamber_sizes()
    out = []
    res = results.set_index(["office", "state", "district"])

    # State legislatures: every seat 1..N (MN House uses A/B suffixes).
    for st, chambers in sizes.items():
        for office, n in chambers.items():
            roster = openstates[(openstates.office == office) & (openstates.state == st)].set_index("district")
            districts = sorted(set(roster.index) | set(results.query("office==@office and state==@st").district),
                               key=lambda d: (int(re.match(r"\d+", d).group()), d))
            if len(districts) != n:
                log.warning("%s %s: %d districts known vs %d seats", st, office, len(districts), n)
            for d in districts:
                prior = roster.loc[d] if d in roster.index else None
                prior_holder = prior["holder"] if prior is not None else ""
                prior_party = prior["party"] if prior is not None else ""
                if (office, st, d) in res.index:
                    r = res.loc[(office, st, d)]
                    party = r["party"] or (r["runnerup_party"] if r["status"] == "leading" else "")
                    out.append(_row(office, st, d, r["winner"], party, "2026", r, prior_holder, prior_party))
                elif prior is not None:
                    out.append(_row(office, st, d, prior_holder, prior_party, "holdover", None, prior_holder,
                                    prior_party))
                else:
                    out.append(_row(office, st, d, "", "", "vacant", None, "", ""))

    # U.S. House: all seats were on the ballot.
    house_prior = congress[congress.office == "us_house"].set_index(["state", "district"])
    for (office, st, d), r in res.loc[["us_house"]].iterrows() if "us_house" in res.index.get_level_values(0) else []:
        pr = house_prior.loc[(st, d)] if (st, d) in house_prior.index else None
        out.append(_row(office, st, d, r["winner"], r["party"], "2026", r,
                        pr["holder"] if pr is not None else "", pr["party"] if pr is not None else ""))

    # U.S. Senate: replace the seat that was up; keep the other.
    sen = congress[congress.office == "us_senate"]
    for st in C.states():
        cur = sen[sen.state == st].sort_values("end")
        up = None
        if ("us_senate", st, "special") in res.index:
            up_row, key = res.loc[("us_senate", st, "special")], "special"
        elif ("us_senate", st, "") in res.index:
            up_row, key = res.loc[("us_senate", st, "")], ""
        else:
            up_row, key = None, None
        if up_row is not None and key == "special":
            # Special election: the appointee (most recent term start) holds the seat that was up.
            up = cur.sort_values("start").iloc[-1]
        elif up_row is not None:
            # Regular election: the seat whose current term ends Jan 3, 2027.
            up = cur[cur["end"].astype(str).str.startswith("2027")]
            up = up.iloc[0] if len(up) else None
        for _, s in cur.iterrows():
            if up is not None and s["bioguide"] == up["bioguide"]:
                out.append(_row("us_senate", st, s["district"], up_row["winner"], up_row["party"], "2026",
                                up_row, s["holder"], s["party"]))
            else:
                out.append(_row("us_senate", st, s["district"], s["holder"], s["party"], "holdover", None,
                                s["holder"], s["party"]))

    # Governors.
    gov_prior = openstates[openstates.office == "governor"].set_index("state")
    for st in C.states():
        pr = gov_prior.loc[st] if st in gov_prior.index else None
        if ("governor", st, "") in res.index:
            r = res.loc[("governor", st, "")]
            out.append(_row("governor", st, "", r["winner"], r["party"], "2026", r,
                            pr["holder"] if pr is not None else "", pr["party"] if pr is not None else ""))
        elif pr is not None:
            out.append(_row("governor", st, "", pr["holder"], pr["party"], "holdover", None, pr["holder"], pr["party"]))

    df = pd.DataFrame(out)
    df["id"] = df["office"] + ":" + df["state"] + ":" + df["district"].astype(str)
    df["flipped"] = (df["source"] == "2026") & df["party"].ne("") & df["prior_party"].ne("") \
        & df["party"].ne(df["prior_party"]) & ~df["party"].eq("NP")
    return df


def _row(office, st, d, holder, party, source, r, prior_holder, prior_party) -> dict:
    get = (lambda k: r[k]) if r is not None else (lambda k: None)
    status = get("status") if r is not None else ("holdover" if source == "holdover" else "vacant")
    return {
        "office": office, "state": st, "district": d, "holder": holder or "", "party": party or "",
        "source": source, "status": status, "winner_pct": get("winner_pct"), "runnerup": get("runnerup") or "",
        "runnerup_party": get("runnerup_party") or "", "runnerup_pct": get("runnerup_pct"),
        "margin": get("margin"), "prior_holder": prior_holder or "", "prior_party": prior_party or "",
        "source_url": get("source_url") or "",
    }


def chamber_control(seat_df: pd.DataFrame) -> pd.DataFrame:
    """Post-election seat counts and majority per chamber (uncalled seats counted separately)."""
    sizes = C.chamber_sizes()
    rows = []
    for st, chambers in sizes.items():
        for office, n in chambers.items():
            s = seat_df[(seat_df.office == office) & (seat_df.state == st)]
            called = s[s.status.isin(["called", "holdover", "reported"])]
            d, r = (called.party == "D").sum(), (called.party == "R").sum()
            lead_d = ((s.status == "leading") & (s.party == "D")).sum()
            lead_r = ((s.status == "leading") & (s.party == "R")).sum()
            unc = (s.status.isin(["uncalled", "leading", "vacant"])).sum()
            need = n // 2 + 1
            if st == "NE":
                control = "nonpartisan"
            elif d >= need:
                control = "D"
            elif r >= need:
                control = "R"
            elif d == r == n / 2:
                control = "tie"
            else:
                control = "undecided"
            rows.append({"state": st, "office": office, "seats": n, "D": int(d), "R": int(r),
                         "other": int(len(called) - d - r), "uncalled": int(unc), "leaning_D": int(lead_d),
                         "leaning_R": int(lead_r), "majority": need, "control": control})
    return pd.DataFrame(rows)


def trifectas(seat_df: pd.DataFrame, control: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for st in C.states():
        g = seat_df[(seat_df.office == "governor") & (seat_df.state == st)]
        gov = g.party.iloc[0] if len(g) else ""
        ch = control[control.state == st].set_index("office")["control"].to_dict()
        legs = set(ch.values())
        if "nonpartisan" in legs:
            status = f"{gov} governor; nonpartisan legislature"
        elif len(legs) == 1 and gov in legs:
            status = f"{gov} trifecta"
        elif "undecided" in legs or "tie" in legs:
            status = "undecided"
        else:
            status = "divided"
        rows.append({"state": st, "governor_party": gov, **{f"{k}_control": v for k, v in ch.items()},
                     "trifecta": status})
    return pd.DataFrame(rows)


# ------------------------------------------------------- certified-results adapters
def from_medsl_house(path: Path, year: int = 2026) -> pd.DataFrame:
    """MIT Election Data + Science Lab U.S. House returns (1976-...) -> results rows.

    Columns used: year, state_po, district, candidate, party, candidatevotes,
    totalvotes, stage, special. Released a few months after certification.
    """
    df = pd.read_csv(path, dtype={"district": str})
    df = df[(df.year == year) & (df.stage.str.upper() == "GEN") & (~df.special.astype(bool))]
    df = df[df.state_po.isin(C.states())]
    df["pct"] = 100 * df.candidatevotes / df.totalvotes
    rows = []
    for (st, d), g in df.groupby(["state_po", "district"]):
        g = g.sort_values("candidatevotes", ascending=False)
        w, ru = g.iloc[0], (g.iloc[1] if len(g) > 1 else None)
        rows.append({"office": "us_house", "state": st, "district": norm_district(d), "winner": w.candidate.title(),
                     "party": norm_party(w.party), "winner_pct": round(w.pct, 2),
                     "runnerup": ru.candidate.title() if ru is not None else "",
                     "runnerup_party": norm_party(ru.party) if ru is not None else "",
                     "runnerup_pct": round(ru.pct, 2) if ru is not None else None,
                     "status": "certified", "source_url": "https://electionlab.mit.edu/data"})
    out = pd.DataFrame(rows)
    out["margin"] = out.winner_pct - out.runnerup_pct
    return out


def from_openelections(path: Path, office_map: dict[str, str] | None = None) -> pd.DataFrame:
    """OpenElections county/precinct CSV (county,precinct,office,district,party,candidate,votes)."""
    office_map = office_map or {"U.S. House": "us_house", "State Senate": "state_senate",
                                "State House": "state_house", "State Assembly": "state_house"}
    df = pd.read_csv(path, dtype={"district": str})
    df = df[df.office.isin(office_map)]
    st = Path(path).name.split("__")[1].upper()
    agg = df.groupby(["office", "district", "candidate", "party"], as_index=False).votes.sum()
    rows = []
    for (off, d), g in agg.groupby(["office", "district"]):
        g = g.sort_values("votes", ascending=False)
        tot = g.votes.sum()
        w, ru = g.iloc[0], (g.iloc[1] if len(g) > 1 else None)
        rows.append({"office": office_map[off], "state": st, "district": norm_district(d), "winner": w.candidate,
                     "party": norm_party(w.party), "winner_pct": round(100 * w.votes / tot, 2),
                     "runnerup": ru.candidate if ru is not None else "",
                     "runnerup_party": norm_party(ru.party) if ru is not None else "",
                     "runnerup_pct": round(100 * ru.votes / tot, 2) if ru is not None else None,
                     "status": "certified", "source_url": "https://openelections.net"})
    out = pd.DataFrame(rows)
    out["margin"] = out.winner_pct - out.runnerup_pct
    return out
